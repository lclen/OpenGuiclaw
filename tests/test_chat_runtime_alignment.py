from dataclasses import dataclass
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from core.agent import Agent
from core.routes.chat import router as chat_router
from core.session import Session
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


def test_skill_manager_orders_preferred_skills_first(tmp_path):
    manager = SkillManager(config_path=str(tmp_path / "skills.json"))
    manager.register(
        SkillDefinition(
            name="beta_tool",
            description="beta",
            parameters={"properties": {}, "required": []},
            handler=lambda: "ok",
            category="beta",
        )
    )
    manager.register(
        SkillDefinition(
            name="alpha_tool",
            description="alpha",
            parameters={"properties": {}, "required": []},
            handler=lambda: "ok",
            category="alpha",
        )
    )

    tools = manager.get_tool_definitions(preferred_skills=["alpha_tool"])
    names = [tool["function"]["name"] for tool in tools]

    assert names[0] == "alpha_tool"


def test_session_history_can_skip_rolling_summary():
    session = Session("sess_summary")
    session.summary = "已经完成初始化"
    session.add_message("user", "继续处理")

    with_summary = session.get_history(max_messages=10)
    without_summary = session.get_history(max_messages=10, include_summary=False)

    assert with_summary[0]["role"] == "user"
    assert "前情提要请求" in with_summary[0]["content"]
    assert without_summary == [{"role": "user", "content": "继续处理"}]


def test_agent_runtime_context_assembles_summary_tools_and_memory():
    agent = object.__new__(Agent)
    agent.identity = None
    agent.user_profile = SimpleNamespace(build_prompt=lambda: "")
    agent.skills = SimpleNamespace(summary=lambda **kwargs: "- `write_file`: 写入文件")
    agent.memory = SimpleNamespace(
        build_prompt_sections=lambda *args, **kwargs: {
            "preference": "# 用户偏好与行为约束\n- 默认使用中文",
            "experience": "# 相关任务经验与避坑\n- 写文件后记得校验",
        }
    )
    agent._local_skills_catalog = {}
    agent._catalog_dirty = False
    agent.interaction_habits = ""
    agent._load_habits = lambda: None
    agent._find_relevant_skills = lambda user_query: []
    agent._build_tool_routing_plan = lambda *args, **kwargs: {
        "preferred_skills": ["write_file"],
        "note": "# 工具路由提示\n- `write_file`：经验层推荐",
    }

    session = Session("sess_runtime")
    session.summary = "用户已经确认要在当前项目中写入摘要文件。"
    session.add_message(
        "assistant",
        "",
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": "{\"path\":\"summary.txt\"}",
                },
            }
        ],
    )
    session.add_message("tool", "写入完成，文件已保存。", tool_call_id="call_1", name="write_file")
    session.add_message("visual_log", "用户当前打开了项目终端。")

    runtime_context = agent._assemble_runtime_context(
        "请继续整理 summary.txt",
        session=session,
        workspace_context={
            "workspace_id": "ws_demo",
            "workspace_name": "Demo",
            "workspace_path": "D:/demo",
        },
    )

    assert runtime_context["session_summary"] == "用户已经确认要在当前项目中写入摘要文件。"
    assert runtime_context["history_messages"][0]["role"] == "assistant"
    assert "write_file" in runtime_context["recent_tool_context"]
    assert "用户当前打开了项目终端" in runtime_context["recent_visual_context"]
    assert runtime_context["memory_sections"]["preference"].startswith("# 用户偏好与行为约束")

    prompt = agent._build_system_prompt(
        "请继续整理 summary.txt",
        workspace_context=runtime_context["resolved_workspace_context"],
        runtime_context=runtime_context,
    )

    assert "# 当前会话前情提要" in prompt
    assert "# 最近工具调用脉络" in prompt
    assert "# 用户偏好与行为约束" in prompt
    assert "# 工具路由提示" in prompt


def test_tool_runtime_build_routing_plan_dedupes_reasons_without_slice_error():
    from core.chat_runtime import ToolRuntime

    class FakeSkills:
        @staticmethod
        def list_visible(allowed_skills=None, skills_mode="inclusive"):
            return [SimpleNamespace(name="file-manager", category="files", plugin_name="file-manager")]

    class FakeMemory:
        @staticmethod
        def search(*args, **kwargs):
            return [
                SimpleNamespace(content="file-manager is useful", tags=["file-manager"]),
                SimpleNamespace(content="file-manager again", tags=["files"]),
            ]

    class FakeAgent:
        def __init__(self):
            self.skills = FakeSkills()
            self.memory = FakeMemory()

        @staticmethod
        def _normalize_query_text(user_query):
            return str(user_query or "")

        @staticmethod
        def _resolve_workspace_context(workspace_context=None):
            return workspace_context

        @staticmethod
        def _find_relevant_skills(query_text):
            return ["file-manager"]

    plan = ToolRuntime(FakeAgent()).build_routing_plan("please help with file-manager cleanup")

    assert plan["preferred_skills"] == ["file-manager"]
    assert "file-manager" in plan["note"]
