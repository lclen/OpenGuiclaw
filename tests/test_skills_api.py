import json
import pytest
import httpx
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI

from core.automation_context import reset_automation_source_context, set_automation_source_context
from core.routes import skills as skills_router
from core.routes import chat as chat_router
from core.session import Session
from core.skill_runtime import InstalledSkill
from core.skills import SkillManager
from core.state import _ctx_event_queue, app_state
from core.tool_path_repair import resolve_tool_path
from plugins import file_manager, filesystem
from plugins import python_bridge
from plugins import system_tools


class DummyAgent:
    def __init__(self, tmp_path: Path):
        self.base_dir = tmp_path
        self.skills = SkillManager(config_path=str(tmp_path / "skills.json"))
        self.sessions = SimpleNamespace(current=Session("session_test"))
        self._local_skill_state_path = tmp_path / "local_skill_state.json"
        self._local_skills_catalog = {}
        self._catalog_dirty = False

    def ensure_session_skills_current(self, session=None):
        session = session or self.sessions.current
        version = self.skills.get_version()
        session.metadata["skills_version"] = version
        return version

    def refresh_skill_runtime(self, reason="manual"):
        skills_root = self.base_dir / "skills"
        skills_root.mkdir(parents=True, exist_ok=True)
        if self._local_skill_state_path.exists():
            state_map = json.loads(self._local_skill_state_path.read_text(encoding="utf-8"))
        else:
            state_map = {}
        catalog = {}
        for skill_md in skills_root.glob("*/SKILL.md"):
            name = skill_md.parent.name
            catalog[name] = {
                "description": f"{name} description",
                "path": str(skill_md),
                "scripts": [],
                "enabled": state_map.get(name, True),
            }
        self._local_skills_catalog = catalog
        self._catalog_dirty = False
        return self.skills.bump_version(reason)

    def set_local_skill_enabled(self, name: str, enabled: bool):
        if self._local_skill_state_path.exists():
            state = json.loads(self._local_skill_state_path.read_text(encoding="utf-8"))
        else:
            state = {}
        state[name] = enabled
        self._local_skill_state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        if name in self._local_skills_catalog:
            self._local_skills_catalog[name]["enabled"] = enabled
        return self.skills.bump_version(f"catalog_toggle:{name}")


def _drain_skill_events():
    events = []
    while True:
        try:
            events.append(_ctx_event_queue.get_nowait())
        except Exception:
            break
    return events


def _make_client(tmp_path: Path):
    app = FastAPI()
    app.include_router(skills_router.router)
    agent = DummyAgent(tmp_path)
    app_state["agent"] = agent
    app_state.pop("plugin_manager", None)
    _drain_skill_events()
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    return client, agent


class DummyChatAgent(DummyAgent):
    def __init__(self, tmp_path: Path):
        super().__init__(tmp_path)
        self.model = "test-model"
        self.max_tokens = 256
        self.temperature = 0
        self._qwen_search_enabled = False
        self.context = None
        self.skills = SimpleNamespace(
            get_tool_definitions=lambda **kwargs: [],
            execute=lambda name, params: "ok",
            get_version=lambda: 3,
        )
        self.client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content="workspace ok", tool_calls=None))],
                        usage=None,
                    )
                )
            )
        )

    def _build_system_prompt(self, *args, **kwargs):
        return "system prompt"

    def _record_usage(self, *args, **kwargs):
        return None


@pytest.mark.asyncio
async def test_install_skill_returns_immediate_fields(monkeypatch, tmp_path):
    client, agent = _make_client(tmp_path)
    monkeypatch.setattr(skills_router, "_APP_BASE", tmp_path)

    def fake_install(url: str, app_base: Path, requested_name: str = ""):
        dest_dir = app_base / "skills" / "frontend-skill"
        dest_dir.mkdir(parents=True, exist_ok=True)
        skill_md = dest_dir / "SKILL.md"
        skill_md.write_text("---\nname: frontend-skill\ndescription: test skill\n---\n", encoding="utf-8")
        return InstalledSkill(
            name="frontend-skill",
            description="test skill",
            dest_dir=dest_dir,
            skill_md_path=skill_md,
            source_url=url,
        )

    monkeypatch.setattr(skills_router, "install_skill_from_source", fake_install)

    try:
        response = await client.post("/api/skills/install", json={"url": "https://example.com/skill"})
        data = response.json()

        assert response.status_code == 200
        assert data["applied_immediately"] is True
        assert data["requires_restart"] is False
        assert data["installed_skill_names"] == ["frontend-skill"]
        assert data["skills_version"] == agent.skills.get_version()
        events = _drain_skill_events()
        assert any(evt.get("type") == "skills_version" and evt.get("action") == "install" for evt in events)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_list_skills_returns_type_locked_and_source(monkeypatch, tmp_path):
    client, agent = _make_client(tmp_path)
    monkeypatch.setattr(skills_router, "_APP_BASE", tmp_path)

    agent.skills.set_registration_context(
        source_type="system_plugin",
        source_path=str(tmp_path / "plugins" / "mcp_gateway.py"),
        system_locked=True,
        plugin_name="mcp_gateway",
    )
    try:
        @agent.skills.skill(
            name="mcp_list_servers",
            description="List MCP servers",
            parameters={"properties": {}, "required": []},
            category="system",
        )
        def _mcp_list_servers():
            return "ok"
    finally:
        agent.skills.clear_registration_context()

    app_state["plugin_manager"] = SimpleNamespace(
        list_plugins=lambda: [
            SimpleNamespace(
                name="mcp_gateway",
                display_name="MCP Gateway",
                description="System MCP plugin",
                path=tmp_path / "plugins" / "mcp_gateway.py",
                skills=["mcp_list_servers"],
            )
        ]
    )

    skill_dir = tmp_path / "skills" / "frontend-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: frontend-skill\ndescription: ui skill\n---\n", encoding="utf-8")
    agent.refresh_skill_runtime("test_refresh")

    try:
        response = await client.get("/api/skills/list")
        data = response.json()

        assert response.status_code == 200
        by_name = {item["name"]: item for item in data["skills"]}
        assert by_name["MCP Gateway"]["type"] == "system_plugin"
        assert by_name["MCP Gateway"]["locked"] is True
        assert "mcp_gateway.py" in by_name["MCP Gateway"]["source"]
        assert by_name["frontend-skill"]["type"] == "user_skill"
        assert by_name["frontend-skill"]["registry_category"] == "frontend-skill"
        assert by_name["frontend-skill"]["locked"] is False
        assert by_name["frontend-skill"]["source"].endswith("SKILL.md")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_toggle_locked_system_skill_rejected(monkeypatch, tmp_path):
    client, agent = _make_client(tmp_path)
    monkeypatch.setattr(skills_router, "_APP_BASE", tmp_path)

    agent.skills.set_registration_context(
        source_type="system_plugin",
        source_path=str(tmp_path / "plugins" / "sandbox_repl.py"),
        system_locked=True,
        plugin_name="sandbox_repl",
    )
    try:
        @agent.skills.skill(
            name="run_in_sandbox",
            description="sandbox",
            parameters={"properties": {}, "required": []},
            category="system",
        )
        def _run_in_sandbox():
            return "ok"
    finally:
        agent.skills.clear_registration_context()

    try:
        response = await client.post("/api/skills/toggle", json={"name": "run_in_sandbox", "enabled": False})
        assert response.status_code == 403
        assert "不可关闭" in response.json()["detail"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_toggle_catalog_skill_updates_enabled_state(monkeypatch, tmp_path):
    client, agent = _make_client(tmp_path)
    monkeypatch.setattr(skills_router, "_APP_BASE", tmp_path)

    skill_dir = tmp_path / "skills" / "frontend-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: frontend-skill\ndescription: ui skill\n---\n", encoding="utf-8")
    agent.refresh_skill_runtime("before_toggle")

    try:
        response = await client.post("/api/skills/toggle", json={"name": "frontend-skill", "enabled": False, "tools": []})
        assert response.status_code == 200
        assert response.json()["enabled"] is False
        assert agent._local_skills_catalog["frontend-skill"]["enabled"] is False
        events = _drain_skill_events()
        assert any(evt.get("type") == "skills_version" and evt.get("action") == "toggle" for evt in events)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_reload_skills_broadcasts_version_event(monkeypatch, tmp_path):
    client, agent = _make_client(tmp_path)
    monkeypatch.setattr(skills_router, "_APP_BASE", tmp_path)

    skill_dir = tmp_path / "skills" / "frontend-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: frontend-skill\ndescription: ui skill\n---\n", encoding="utf-8")
    agent.refresh_skill_runtime("seed")
    _drain_skill_events()

    try:
        response = await client.post("/api/skills/reload")
        data = response.json()

        assert response.status_code == 200
        assert data["requires_restart"] is False
        assert data["skills_version"] == agent.skills.get_version()
        events = _drain_skill_events()
        assert any(evt.get("type") == "skills_version" and evt.get("action") == "reload" for evt in events)
    finally:
        await client.aclose()


def test_ensure_session_skills_current_updates_stale_version(tmp_path):
    agent = DummyAgent(tmp_path)
    session = Session("stale_session")
    session.metadata["skills_version"] = 1

    current = agent.ensure_session_skills_current(session)

    assert current == agent.skills.get_version()
    assert session.metadata["skills_version"] == agent.skills.get_version()


@pytest.mark.asyncio
async def test_workspace_stream_persists_session_skills_version(monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(chat_router.router)
    agent = DummyChatAgent(tmp_path)
    app_state["agent"] = agent

    session_data = {
        "session_id": "sess_workspace",
        "created_at": "2025-01-01 00:00:00",
        "updated_at": "2025-01-01 00:00:00",
        "summary": "",
        "metadata": {"skills_version": 1},
        "messages": [],
    }
    saved: dict = {}

    monkeypatch.setattr(chat_router, "_load_ws_session_data", lambda workspace_id, session_id, **kwargs: dict(session_data))
    monkeypatch.setattr(chat_router, "_merge_save_ws_session_data", lambda workspace_id, data: saved.update(data))
    monkeypatch.setattr(
        chat_router,
        "_get_workspace_context",
        lambda workspace_id: {
            "workspace_id": workspace_id,
            "workspace_name": "Test Workspace",
            "workspace_path": str(tmp_path.resolve()),
        },
    )
    monkeypatch.setattr(chat_router, "get_profile_store", lambda: SimpleNamespace(get=lambda _: None))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=5) as client:
        async with client.stream(
            "POST",
            "/api/workspaces/ws_1/sessions/sess_workspace/stream",
            json={"workspace_id": "ws_1", "session_id": "sess_workspace", "message": "hello"},
        ) as response:
            body = ""
            async for chunk in response.aiter_text():
                body += chunk
                if "[DONE]" in body:
                    break

    assert response.status_code == 200
    assert saved["metadata"]["skills_version"] == 3


@pytest.mark.asyncio
async def test_execute_command_uses_workspace_request_scope_cwd(tmp_path):
    manager = SkillManager(config_path=str(tmp_path / "skills.json"))
    system_tools.register(manager)

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    command = f'"{sys.executable}" -c "import os; print(os.getcwd())"'
    token = set_automation_source_context(
        source_kind="desktop",
        source_session_id="sess_workspace",
        workspace_id="ws_test",
        workspace_name="Test Workspace",
        workspace_path=str(workspace_dir.resolve()),
    )
    try:
        result = await manager.execute("execute_command", {"command": command})
    finally:
        reset_automation_source_context(token)

    assert str(workspace_dir.resolve()) in result


@pytest.mark.asyncio
async def test_execute_command_explicit_cwd_overrides_workspace_scope(tmp_path):
    manager = SkillManager(config_path=str(tmp_path / "skills.json"))
    system_tools.register(manager)

    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    override_dir = tmp_path / "override"
    override_dir.mkdir()
    command = f'"{sys.executable}" -c "import os; print(os.getcwd())"'
    token = set_automation_source_context(
        source_kind="desktop",
        source_session_id="sess_workspace",
        workspace_id="ws_test",
        workspace_name="Test Workspace",
        workspace_path=str(workspace_dir.resolve()),
    )
    try:
        result = await manager.execute(
            "execute_command",
            {"command": command, "cwd": str(override_dir.resolve())},
        )
    finally:
        reset_automation_source_context(token)

    assert str(override_dir.resolve()) in result


@pytest.mark.asyncio
async def test_filesystem_plugin_uses_workspace_default_path(tmp_path):
    manager = SkillManager(config_path=str(tmp_path / "skills.json"))
    filesystem.register(manager)

    workspace_dir = tmp_path / "workspace_async"
    workspace_dir.mkdir()
    token = set_automation_source_context(
        source_kind="desktop",
        source_session_id="sess_workspace",
        workspace_id="ws_test",
        workspace_name="Test Workspace",
        workspace_path=str(workspace_dir.resolve()),
    )
    try:
        write_result = await manager.execute("write_file", {"path": "notes.txt", "content": "hello workspace"})
        read_result = await manager.execute("read_file", {"path": "notes.txt"})
        list_result = await manager.execute("list_directory", {})
    finally:
        reset_automation_source_context(token)

    assert "成功写入文件" in write_result
    assert (workspace_dir / "notes.txt").read_text(encoding="utf-8") == "hello workspace"
    assert "hello workspace" in read_result
    assert "notes.txt" in list_result


@pytest.mark.asyncio
async def test_file_manager_plugin_uses_workspace_default_path(tmp_path):
    manager = SkillManager(config_path=str(tmp_path / "skills.json"))
    file_manager.register(manager)

    workspace_dir = tmp_path / "workspace_sync"
    workspace_dir.mkdir()
    token = set_automation_source_context(
        source_kind="desktop",
        source_session_id="sess_workspace",
        workspace_id="ws_test",
        workspace_name="Test Workspace",
        workspace_path=str(workspace_dir.resolve()),
    )
    try:
        write_result = await manager.execute("write_file", {"path": "summary.txt", "content": "workspace scoped"})
        read_result = await manager.execute("read_file", {"path": "summary.txt"})
        list_result = await manager.execute("list_dir", {})
    finally:
        reset_automation_source_context(token)

    assert "成功写入" in write_result
    assert (workspace_dir / "summary.txt").read_text(encoding="utf-8") == "workspace scoped"
    assert "workspace scoped" in read_result
    assert "summary.txt" in list_result


@pytest.mark.asyncio
async def test_filesystem_plugin_repairs_hyphen_spacing_in_absolute_path(tmp_path):
    manager = SkillManager(config_path=str(tmp_path / "skills.json"))
    filesystem.register(manager)

    workspace_dir = tmp_path / "项目-报文"
    workspace_dir.mkdir()
    target = workspace_dir / "notes.txt"
    target.write_text("fixed path", encoding="utf-8")
    broken_path = str(target).replace("项目-报文", "项目 - 报文")

    token = set_automation_source_context(
        source_kind="desktop",
        source_session_id="sess_workspace",
        workspace_id="ws_test",
        workspace_name="项目-报文",
        workspace_path=str(workspace_dir.resolve()),
    )
    try:
        read_result = await manager.execute("read_file", {"path": broken_path})
        list_result = await manager.execute("list_directory", {"path": str(workspace_dir).replace("项目-报文", "项目 - 报文")})
    finally:
        reset_automation_source_context(token)

    assert "已自动修正路径" in read_result
    assert "fixed path" in read_result
    assert "已自动修正路径" in list_result
    assert "notes.txt" in list_result


@pytest.mark.asyncio
async def test_file_manager_plugin_repairs_hyphen_spacing_in_absolute_path(tmp_path):
    manager = SkillManager(config_path=str(tmp_path / "skills.json"))
    file_manager.register(manager)

    workspace_dir = tmp_path / "项目-报文"
    workspace_dir.mkdir()
    target = workspace_dir / "summary.txt"
    target.write_text("manager fixed path", encoding="utf-8")
    broken_path = str(target).replace("项目-报文", "项目 - 报文")

    token = set_automation_source_context(
        source_kind="desktop",
        source_session_id="sess_workspace",
        workspace_id="ws_test",
        workspace_name="项目-报文",
        workspace_path=str(workspace_dir.resolve()),
    )
    try:
        read_result = await manager.execute("read_file", {"path": broken_path})
        list_result = await manager.execute("list_dir", {"path": str(workspace_dir).replace("项目-报文", "项目 - 报文")})
    finally:
        reset_automation_source_context(token)

    assert "已自动修正路径" in read_result
    assert "manager fixed path" in read_result
    assert "已自动修正路径" in list_result
    assert "summary.txt" in list_result


@pytest.mark.asyncio
async def test_execute_command_repairs_workspace_cwd_path(tmp_path):
    manager = SkillManager(config_path=str(tmp_path / "skills.json"))
    system_tools.register(manager)

    workspace_dir = tmp_path / "项目-报文"
    workspace_dir.mkdir()
    broken_cwd = str(workspace_dir.resolve()).replace("项目-报文", "项目 - 报文")
    command = f'"{sys.executable}" -c "import os; print(os.getcwd())"'

    result = await manager.execute("execute_command", {"command": command, "cwd": broken_cwd})

    assert "已自动修正路径" in result
    assert str(workspace_dir.resolve()) in result


@pytest.mark.asyncio
async def test_execute_python_script_repairs_absolute_path_literals(tmp_path):
    manager = SkillManager(config_path=str(tmp_path / "skills.json"))
    python_bridge.register(manager)

    workspace_dir = tmp_path / "项目-报文"
    workspace_dir.mkdir()
    target = workspace_dir / "README.md"
    target.write_text("bridge fixed path", encoding="utf-8")
    broken_path = str(target.resolve()).replace("项目-报文", "项目 - 报文")

    token = set_automation_source_context(
        source_kind="desktop",
        source_session_id="sess_workspace",
        workspace_id="ws_test",
        workspace_name="项目-报文",
        workspace_path=str(workspace_dir.resolve()),
    )
    try:
        result = await manager.execute(
            "execute_python_script",
            {"script": f"from pathlib import Path\nprint(Path({broken_path!r}).read_text(encoding='utf-8'))"},
        )
    finally:
        reset_automation_source_context(token)

    assert "已自动修正路径" in result
    assert "bridge fixed path" in result


def test_resolve_tool_path_returns_candidates_without_auto_repair_when_ambiguous(tmp_path):
    cwd_root = tmp_path / "cwd_root"
    ws_root = tmp_path / "ws_root"
    cwd_root.mkdir()
    ws_root.mkdir()
    (cwd_root / "项目-报文").mkdir()
    (ws_root / "项目-报文").mkdir()

    result = resolve_tool_path(
        "项目 - 报文",
        cwd=cwd_root,
        workspace_path=str(ws_root),
        expect="dir",
    )

    assert result.was_repaired is False
    assert len(result.candidates) == 2
