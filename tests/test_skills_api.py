import pytest
import httpx
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI

from core.routes import skills as skills_router
from core.session import Session
from core.skill_runtime import InstalledSkill
from core.skills import SkillManager
from core.state import app_state


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
        catalog = {}
        for skill_md in skills_root.glob("*/SKILL.md"):
            name = skill_md.parent.name
            catalog[name] = {
                "description": f"{name} description",
                "path": str(skill_md),
                "scripts": [],
                "enabled": True,
            }
        self._local_skills_catalog = catalog
        self._catalog_dirty = False
        return self.skills.bump_version(reason)

    def set_local_skill_enabled(self, name: str, enabled: bool):
        entry = self._local_skills_catalog[name]
        entry["enabled"] = enabled
        return self.skills.bump_version(f"catalog_toggle:{name}")


def _make_client(tmp_path: Path):
    app = FastAPI()
    app.include_router(skills_router.router)
    agent = DummyAgent(tmp_path)
    app_state["agent"] = agent
    app_state.pop("plugin_manager", None)
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    return client, agent


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
    finally:
        await client.aclose()
