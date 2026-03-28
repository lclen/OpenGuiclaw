from dataclasses import dataclass
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from core.routes.chat import router as chat_router
from core.skills import SkillDefinition, SkillManager
from core.state import app_state


@dataclass
class _ChunkAgent:
    model: str = "test-model"

    async def chat_stream(self, *args, **kwargs):
        yield '{"type":"status","content":"思考中..."}'
        yield '{"type":"text_delta","content":"你好"}'
        yield '{"type":"text_delta","content":"，世界"}'
        yield '{"type":"done"}'


class _FallbackAgent:
    def __init__(self):
        self.model = "fallback-model"
        self.called = False

    def chat(self, *args, **kwargs):
        self.called = True
        return "fallback response"


@pytest_asyncio.fixture
async def chat_client():
    app = FastAPI()
    app.include_router(chat_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client
    app_state.pop("agent", None)


@pytest.mark.asyncio
async def test_chat_sync_collects_stream_output(chat_client):
    app_state["agent"] = _ChunkAgent()

    response = await chat_client.post("/api/chat/sync", json={"message": "你好"})

    assert response.status_code == 200
    assert response.json()["response"] == "你好，世界"


@pytest.mark.asyncio
async def test_chat_sync_falls_back_to_legacy_chat(chat_client):
    agent = _FallbackAgent()
    app_state["agent"] = agent

    response = await chat_client.post("/api/chat/sync", json={"message": "hello"})

    assert response.status_code == 200
    assert response.json()["response"] == "fallback response"
    assert agent.called is True


def test_skill_manager_filters_tools_by_profile_scope(tmp_path):
    manager = SkillManager(config_path=str(tmp_path / "skills.json"))

    manager.set_registration_context(source_type="builtin_skill")
    manager.register(
        SkillDefinition(
            name="remember",
            description="remember",
            parameters={"properties": {}, "required": []},
            handler=lambda: "ok",
            category="memory",
        )
    )
    manager.clear_registration_context()

    manager.set_registration_context(source_type="system_plugin", plugin_name="sandbox_repl")
    manager.register(
        SkillDefinition(
            name="run_python",
            description="run python",
            parameters={"properties": {}, "required": []},
            handler=lambda: "ok",
            category="runtime",
        )
    )
    manager.clear_registration_context()

    manager.set_registration_context(source_type="system_plugin", plugin_name="system_tools")
    manager.register(
        SkillDefinition(
            name="exec_shell",
            description="exec shell",
            parameters={"properties": {}, "required": []},
            handler=lambda: "ok",
            category="system",
        )
    )
    manager.clear_registration_context()

    inclusive_names = [tool["function"]["name"] for tool in manager.get_tool_definitions(["sandbox_repl"], "inclusive")]
    exclusive_names = [tool["function"]["name"] for tool in manager.get_tool_definitions(["system_tools"], "exclusive")]
    summary = manager.summary(["sandbox_repl"], "inclusive")

    assert "remember" in inclusive_names
    assert "run_python" in inclusive_names
    assert "exec_shell" not in inclusive_names

    assert "remember" in exclusive_names
    assert "exec_shell" not in exclusive_names
    assert "run_python" in exclusive_names

    assert "run_python" in summary
    assert "exec_shell" not in summary
