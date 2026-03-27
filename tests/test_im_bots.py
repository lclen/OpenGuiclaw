import json
import types
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from core.channels.base import ChannelAdapter
from core.channels.gateway import ChannelGateway
from core.channels.types import MediaFile, OutgoingMessage, UnifiedMessage
from core.im_bots import (
    derive_legacy_channels,
    is_im_session_id,
    load_im_bots_from_config,
    make_channel_name,
    make_im_session_id,
    migrate_channels_to_im_bots,
    parse_im_session_id,
)
from core.scheduler.task import ScheduledTask, TaskTargetKind, TaskType
from core.server import register_im_adapters


def write_config(base_dir: Path, payload: dict) -> None:
    (base_dir / "config.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@pytest.fixture
def im_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "data" / "sessions").mkdir(parents=True)
    monkeypatch.setattr("core.routes.im._APP_BASE", tmp_path)
    return tmp_path


@pytest_asyncio.fixture
async def im_client(im_base: Path):
    from core.routes.im import router

    app = FastAPI()
    app.include_router(router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


def test_migrate_channels_to_im_bots():
    bots = migrate_channels_to_im_bots(
        {
            "telegram": {"bot_token": "tg-token", "proxy": "http://127.0.0.1:7890"},
            "feishu": {"app_id": "cli_xxx", "app_secret": "secret"},
            "dingtalk": {"client_id": "", "client_secret": ""},
        }
    )

    assert [bot["platform"] for bot in bots] == ["telegram", "feishu"]
    assert bots[0]["id"] == "telegram"
    assert bots[1]["credentials"]["app_secret"] == "secret"


def test_migrate_dingtalk_channels_to_im_bots_sets_footer_defaults():
    bots = migrate_channels_to_im_bots(
        {
            "dingtalk": {
                "client_id": "ding-client",
                "client_secret": "ding-secret",
                "agent_id": "123456",
            }
        }
    )

    assert len(bots) == 1
    assert bots[0]["platform"] == "dingtalk"
    assert bots[0]["credentials"]["footer_elapsed"] is True
    assert bots[0]["credentials"]["footer_status"] is True


def test_load_im_bots_prefers_new_config_and_derives_legacy_channels():
    config = {
        "im_bots": [
            {
                "id": "tg-alpha",
                "name": "Telegram Alpha",
                "platform": "telegram",
                "enabled": False,
                "credentials": {"bot_token": "token-a", "proxy": ""},
            },
            {
                "id": "tg-beta",
                "name": "Telegram Beta",
                "platform": "telegram",
                "enabled": True,
                "credentials": {"bot_token": "token-b", "proxy": "http://proxy"},
            },
            {
                "id": "feishu-main",
                "name": "Feishu Main",
                "platform": "feishu",
                "enabled": True,
                "credentials": {"app_id": "cli_x", "app_secret": "sec"},
            },
        ]
    }

    bots = load_im_bots_from_config(config)
    channels = derive_legacy_channels(bots)

    assert len(bots) == 3
    assert channels["telegram"]["bot_token"] == "token-b"
    assert channels["feishu"]["app_id"] == "cli_x"
    assert channels["dingtalk"]["client_id"] == ""


def test_bot_aware_session_helpers_support_new_and_legacy_formats():
    channel_name = make_channel_name("telegram", "bot-main")
    session_id = make_im_session_id(channel_name, "chat_42")
    parsed = parse_im_session_id(session_id)

    assert channel_name == "telegram@@bot-main"
    assert parsed == {
        "platform": "telegram",
        "bot_id": "bot-main",
        "channel_name": "telegram@@bot-main",
        "chat_id": "chat_42",
    }
    assert is_im_session_id(session_id) is True

    legacy = parse_im_session_id("telegram_legacy_chat")
    assert legacy == {
        "platform": "telegram",
        "bot_id": "telegram",
        "channel_name": "telegram",
        "chat_id": "legacy_chat",
    }


@pytest.mark.asyncio
async def test_im_bot_crud_toggle_health_and_sessions(
    im_client: httpx.AsyncClient,
    im_base: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    write_config(im_base, {"channels": {"telegram": {"bot_token": "legacy-token"}}})

    response = await im_client.get("/api/im/bots")
    assert response.status_code == 200
    payload = response.json()
    assert payload["bots"][0]["id"] == "telegram"

    create_resp = await im_client.post(
        "/api/im/bots",
        json={
            "id": "tg-sidecar",
            "name": "Telegram Sidecar",
            "platform": "telegram",
            "enabled": True,
            "credentials": {"bot_token": "sidecar-token", "proxy": ""},
        },
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["requires_restart"] is True

    config_after_create = json.loads((im_base / "config.json").read_text(encoding="utf-8"))
    assert len(config_after_create["im_bots"]) == 2
    assert config_after_create["channels"]["telegram"]["bot_token"] == "legacy-token"

    update_resp = await im_client.put(
        "/api/im/bots/tg-sidecar",
        json={
            "id": "tg-sidecar-v2",
            "name": "Telegram Sidecar V2",
            "platform": "telegram",
            "enabled": False,
            "credentials": {"bot_token": "sidecar-token-v2", "proxy": "http://127.0.0.1:7890"},
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["bot"]["id"] == "tg-sidecar-v2"

    toggle_resp = await im_client.post(
        "/api/im/bots/tg-sidecar-v2/toggle",
        json={"enabled": True},
    )
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["bot"]["enabled"] is True

    health_mock = AsyncMock(
        return_value={"status": "healthy", "error": None, "checked_at": "2026-03-26T10:00:00"}
    )
    monkeypatch.setattr("core.routes.im.run_im_bot_healthcheck", health_mock)
    health_resp = await im_client.post(
        "/api/im/bots/health",
        json={"bot_id": "tg-sidecar-v2", "persist": True},
    )
    assert health_resp.status_code == 200
    assert health_resp.json()["result"]["status"] == "healthy"

    session_new = make_im_session_id(make_channel_name("telegram", "tg-sidecar-v2"), "chat-a")
    session_old = "telegram_chat-legacy"
    sessions_dir = im_base / "data" / "sessions"
    for session_id, title in [(session_new, "new"), (session_old, "old")]:
        (sessions_dir / f"{session_id}.json").write_text(
            json.dumps(
                {
                    "session_id": session_id,
                    "updated_at": "2026-03-26T12:00:00",
                    "messages": [{"role": "user", "content": f"hello-{title}"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    filtered_resp = await im_client.get("/api/im/sessions", params={"bot_id": "tg-sidecar-v2"})
    assert filtered_resp.status_code == 200
    sessions = filtered_resp.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["platform"] == "telegram"
    assert sessions[0]["bot_id"] == "tg-sidecar-v2"
    assert sessions[0]["channel_name"] == "telegram@@tg-sidecar-v2"

    delete_resp = await im_client.delete("/api/im/bots/tg-sidecar-v2")
    assert delete_resp.status_code == 200
    bots_after_delete = (await im_client.get("/api/im/bots")).json()["bots"]
    assert [bot["id"] for bot in bots_after_delete] == ["telegram"]


@pytest.mark.asyncio
async def test_im_runtime_routes_and_channel_fields(
    im_client: httpx.AsyncClient,
    im_base: Path,
):
    write_config(
        im_base,
        {
            "im_bots": [
                {
                    "id": "ding-main",
                    "name": "Ding Main",
                    "platform": "dingtalk",
                    "enabled": True,
                    "credentials": {
                        "client_id": "ding-client",
                        "client_secret": "ding-secret",
                        "agent_id": "123",
                        "footer_elapsed": True,
                        "footer_status": False,
                    },
                }
            ]
        },
    )

    from core.state import app_state

    channel_name = make_channel_name("dingtalk", "ding-main")
    app_state["gateway"] = types.SimpleNamespace(
        adapters={
            channel_name: types.SimpleNamespace(
                _running=True,
                _stream_state=types.SimpleNamespace(value="running"),
                _last_error=None,
            )
        }
    )

    await im_client.post(
        "/api/im/chat-aliases",
        json={
            "platform": "dingtalk",
            "bot_id": "ding-main",
            "chat_id": "chat-001",
            "alias": "南京研发群",
        },
    )
    await im_client.post(
        "/api/im/bot-config",
        json={
            "platform": "dingtalk",
            "bot_id": "ding-main",
            "chat_id": "chat-001",
            "enabled": True,
            "response_mode": "smart",
        },
    )
    await im_client.post(
        "/api/im/group-policy",
        json={
            "platform": "dingtalk",
            "bot_id": "ding-main",
            "chat_id": "chat-001",
            "enabled": True,
            "response_mode": "always",
        },
    )

    session_id = make_im_session_id(channel_name, "chat-001")
    (im_base / "data" / "sessions" / f"{session_id}.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "updated_at": "2026-03-26 18:00:00",
                "metadata": {
                    "platform": "dingtalk",
                    "bot_id": "ding-main",
                    "channel_name": channel_name,
                    "chat_type": "group",
                    "chat_name": "研发群",
                    "display_name": "张三",
                },
                "messages": [{"role": "user", "content": "hello ding"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    channel_resp = await im_client.get("/api/im/channels")
    assert channel_resp.status_code == 200
    channel_payload = channel_resp.json()["channels"][0]
    assert channel_payload["display_name"] == "Ding Main"
    assert channel_payload["stream_state"] == "running"
    assert channel_payload["session_count"] == 1

    sessions_resp = await im_client.get("/api/im/sessions", params={"channel_name": channel_name})
    assert sessions_resp.status_code == 200
    sessions_payload = sessions_resp.json()["sessions"][0]
    assert sessions_payload["chat_type"] == "group"
    assert sessions_payload["chat_name"] == "研发群"
    assert sessions_payload["alias"] == "南京研发群"
    assert sessions_payload["response_mode"] == "smart"
    assert sessions_payload["bot_enabled"] is True

    aliases_resp = await im_client.get("/api/im/chat-aliases", params={"channel_name": channel_name})
    assert aliases_resp.status_code == 200
    assert aliases_resp.json()["items"][0]["alias"] == "南京研发群"

    del app_state["gateway"]


def test_register_im_adapters_supports_multiple_instances(monkeypatch: pytest.MonkeyPatch):
    created: list[tuple[str, dict]] = []

    def build_adapter(platform_name: str):
        class FakeAdapter:
            def __init__(self, **kwargs):
                self.channel_name = kwargs["channel_name"]
                self.kwargs = kwargs
                created.append((platform_name, kwargs))

        return FakeAdapter

    monkeypatch.setitem(
        __import__("sys").modules,
        "core.channels.adapters.telegram",
        types.SimpleNamespace(TelegramAdapter=build_adapter("telegram")),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "core.channels.adapters.feishu",
        types.SimpleNamespace(FeishuAdapter=build_adapter("feishu")),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "core.channels.adapters.dingtalk",
        types.SimpleNamespace(DingTalkAdapter=build_adapter("dingtalk")),
    )

    class FakeGateway:
        def __init__(self):
            self.adapters = []

        def register_adapter(self, adapter):
            self.adapters.append(adapter)

    gateway = FakeGateway()
    register_im_adapters(
        gateway,
        [
            {
                "id": "tg-1",
                "platform": "telegram",
                "enabled": True,
                "credentials": {"bot_token": "token-1", "proxy": "", "pairing_code": "", "webhook_url": ""},
            },
            {
                "id": "tg-2",
                "platform": "telegram",
                "enabled": True,
                "credentials": {"bot_token": "token-2", "proxy": "", "pairing_code": "", "webhook_url": ""},
            },
            {
                "id": "ding-main",
                "platform": "dingtalk",
                "enabled": True,
                "credentials": {
                    "client_id": "ding-client",
                    "client_secret": "ding-secret",
                    "agent_id": "123",
                    "footer_elapsed": True,
                    "footer_status": False,
                },
            },
            {
                "id": "feishu-main",
                "platform": "feishu",
                "enabled": True,
                "credentials": {"app_id": "cli_x", "app_secret": "secret"},
            },
        ],
    )

    assert len(gateway.adapters) == 4
    assert [adapter.channel_name for adapter in gateway.adapters] == [
        "telegram@@tg-1",
        "telegram@@tg-2",
        "dingtalk@@ding-main",
        "feishu@@feishu-main",
    ]
    assert created[0][1]["bot_id"] == "tg-1"
    assert created[1][1]["bot_id"] == "tg-2"
    assert created[2][1]["footer_elapsed"] is True
    assert created[2][1]["footer_status"] is False


def test_scheduled_task_normalizes_bot_aware_im_targets():
    session_id = make_im_session_id("telegram@@ops-bot", "chat-99")
    task = ScheduledTask.create(
        name="Bot aware task",
        description="deliver to im",
        trigger_type=__import__("core.scheduler.triggers", fromlist=["TriggerType"]).TriggerType.ONCE,
        trigger_config={},
        task_type=TaskType.TASK,
        target_kind=TaskTargetKind.IM_SESSION.value,
        target_session_id=session_id,
    )

    targets = task.get_delivery_targets()
    assert targets[0]["session_id"] == session_id
    assert targets[0]["channel"] == "telegram@@ops-bot"
    assert targets[0]["chat_id"] == "chat-99"


class _FakeAdapter(ChannelAdapter):
    channel_name = "dingtalk@@ops-bot"

    def __init__(self):
        super().__init__(channel_name=self.channel_name, bot_id="ops-bot")
        self.events: list[tuple[str, str]] = []
        self.sent_messages: list[str] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send_message(self, message: OutgoingMessage) -> str:
        self.sent_messages.append(message.content.text or "")
        return "sent"

    async def download_media(self, media: MediaFile) -> Path:
        raise NotImplementedError

    async def upload_media(self, path: Path, mime_type: str) -> MediaFile:
        raise NotImplementedError

    async def send_typing(self, chat_id: str) -> None:
        self.events.append(("typing", chat_id))

    def supports_streaming(self) -> bool:
        return True

    async def stream_thinking(self, chat_id: str, thinking_text: str, **kwargs) -> None:
        self.events.append(("thinking", thinking_text))

    async def stream_chain_text(self, chat_id: str, text: str, **kwargs) -> None:
        self.events.append(("chain", text))

    async def stream_token(self, chat_id: str, token: str, **kwargs) -> None:
        self.events.append(("token", token))

    async def finalize_stream(self, chat_id: str, final_text: str, **kwargs) -> bool:
        self.events.append(("finalize", final_text))
        return True


class _FakeSessions:
    def __init__(self):
        self._current = None
        self._items: dict[str, object] = {}

    def load(self, session_id: str):
        session = self._items.get(session_id)
        self._current = session
        return session

    def save(self, session=None):
        target = session or self._current
        if target is not None:
            self._items[target.session_id] = target


class _FakeAgent:
    def __init__(self):
        self.sessions = _FakeSessions()

    async def chat_stream(self, user_input):
        yield json.dumps({"type": "thinking_chunk", "content": "分析用户问题"})
        yield json.dumps({"type": "tool_call", "name": "get_weather", "params": {"city": "Nanjing"}})
        yield json.dumps({"type": "tool_result", "name": "get_weather", "result": "晴"})
        yield json.dumps({"type": "message_chunk", "content": "南京今天晴朗"})


class _FakeDeltaAgent:
    def __init__(self):
        self.sessions = _FakeSessions()

    async def chat_stream(self, user_input):
        yield json.dumps({"type": "thinking_start"})
        yield json.dumps({"type": "thinking_delta", "content": "先分析天气接口"})
        yield json.dumps({"type": "thinking_end", "duration_ms": 18, "has_thinking": True})
        yield json.dumps({"type": "text_delta", "content": "南京今天"})
        yield json.dumps({"type": "text_delta", "content": "晴朗"})
        yield json.dumps({"type": "done"})


@pytest.mark.asyncio
async def test_gateway_streams_thinking_chain_and_final_text():
    adapter = _FakeAdapter()
    gateway = ChannelGateway(agent=_FakeAgent())
    gateway.register_adapter(adapter)

    message = UnifiedMessage.create(
        channel="dingtalk@@ops-bot",
        channel_message_id="msg-001",
        user_id="dd_user_1",
        channel_user_id="user_1",
        chat_id="chat-001",
        content=__import__("core.channels.types", fromlist=["MessageContent"]).MessageContent(text="南京天气怎么样"),
        chat_type="group",
        metadata={"chat_name": "研发群", "sender_name": "张三"},
    )

    await gateway._process_message_task(message)

    assert adapter.sent_messages == []
    assert ("typing", "chat-001") in adapter.events
    assert any(item[0] == "thinking" for item in adapter.events)
    assert any(item[0] == "chain" for item in adapter.events)
    assert ("finalize", "南京今天晴朗") in adapter.events


@pytest.mark.asyncio
async def test_gateway_accepts_delta_protocol_and_finalizes_stream():
    adapter = _FakeAdapter()
    gateway = ChannelGateway(agent=_FakeDeltaAgent())
    gateway.register_adapter(adapter)

    message = UnifiedMessage.create(
        channel="dingtalk@@ops-bot",
        channel_message_id="msg-002",
        user_id="dd_user_2",
        channel_user_id="user_2",
        chat_id="chat-002",
        content=__import__("core.channels.types", fromlist=["MessageContent"]).MessageContent(text="南京天气怎么样"),
        chat_type="group",
        metadata={"chat_name": "研发群", "sender_name": "李四"},
    )

    await gateway._process_message_task(message)

    assert ("typing", "chat-002") in adapter.events
    assert any(item[0] == "thinking" for item in adapter.events)
    assert ("token", "南京今天") in adapter.events
    assert ("token", "晴朗") in adapter.events
    assert ("finalize", "南京今天晴朗") in adapter.events
