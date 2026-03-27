import json
import pytest
import httpx
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI

from core.routes import skills as skills_router
from core.routes import chat as chat_router
from core.session import Session
from core.skill_runtime import InstalledSkill
from core.skills import SkillManager
from core.state import _ctx_event_queue, app_state


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

    monkeypatch.setattr(chat_router, "_load_ws_session_data", lambda workspace_id, session_id: dict(session_data))
    monkeypatch.setattr(chat_router, "_save_ws_session_data", lambda workspace_id, data: saved.update(data))
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
