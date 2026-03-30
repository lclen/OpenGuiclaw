import pytest


def test_normalize_markdown_tables_for_channel():
    from core.channels.markdown import contains_markdown, normalize_markdown_for_channel

    source = """# 今日新闻热点TOP 10
| 排名 | 热点事件 | 热度 | 类别 |
| --- | --- | --- | --- |
| 1 | 美伊局势 | 🔥🔥🔥 | 国际 |
| 2 | 5G建设 | 🔥🔥 | 科技 |
"""

    normalized = normalize_markdown_for_channel(source, "dingtalk_test")

    assert contains_markdown(source) is True
    assert "1." in normalized
    assert "- 排名：1" in normalized
    assert "- 热点事件：美伊局势" in normalized
    assert "| 排名 |" not in normalized
    assert "|" not in normalized


@pytest.mark.asyncio
async def test_gateway_marks_markdown_parse_mode_for_im_reply():
    from core.channels.gateway import ChannelGateway
    from core.channels.types import MessageContent, UnifiedMessage

    class FakeSessions:
        def __init__(self):
            self._current = None

        def load(self, session_id):
            return None

        def save(self, session=None):
            return None

    class FakeAgent:
        def __init__(self):
            self.sessions = FakeSessions()

        async def chat_stream(self, user_input):
            yield {"type": "text_delta", "content": "# 标题\n| A | B |\n| --- | --- |\n| 1 | 2 |"}
            yield {"type": "done"}

    class FakeAdapter:
        def __init__(self):
            self.channel_name = "dingtalk_test"
            self.bot_id = "test"
            self.sent = []

        async def send_typing(self, chat_id):
            return None

        def supports_streaming(self):
            return False

        async def finalize_stream(self, chat_id, final_text, thread_id=None):
            return False

        async def send_message(self, message):
            self.sent.append(message)
            return "msg_1"

    gateway = ChannelGateway(FakeAgent())
    adapter = FakeAdapter()
    gateway.adapters[adapter.channel_name] = adapter

    message = UnifiedMessage.create(
        channel=adapter.channel_name,
        channel_message_id="raw-1",
        user_id="user-1",
        channel_user_id="cu-1",
        chat_id="chat-1",
        content=MessageContent.text_only("给我新闻"),
        metadata={},
    )

    await gateway._process_message_task(message)

    assert len(adapter.sent) == 1
    outgoing = adapter.sent[0]
    assert outgoing.parse_mode == "markdown"
    assert "1." in outgoing.content.text
    assert "- A：1" in outgoing.content.text
    assert "- B：2" in outgoing.content.text


@pytest.mark.asyncio
async def test_dingtalk_send_message_normalizes_markdown_tables_before_webhook():
    from core.channels.adapters.dingtalk import DingTalkAdapter
    from core.channels.types import OutgoingMessage

    captured_payloads: list[dict] = []

    class FakeResponse:
        def json(self):
            return {"errcode": 0}

    class FakeHttpClient:
        async def post(self, url, json):
            captured_payloads.append(json)
            return FakeResponse()

    adapter = DingTalkAdapter(app_key="ding-test", app_secret="secret")
    adapter._http_client = FakeHttpClient()

    message = OutgoingMessage.text(
        chat_id="chat-1",
        text="# 标题\n| 序号 | 模块 | 状态 |\n| --- | --- | --- |\n| 1 | 记忆系统 | 完成 |",
        parse_mode="markdown",
        metadata={"session_webhook": "https://example.com/webhook"},
    )

    result = await adapter.send_message(message)

    assert result.startswith("webhook_")
    assert len(captured_payloads) == 1
    sent_text = captured_payloads[0]["markdown"]["text"]
    assert "1." in sent_text
    assert "- 序号：1" in sent_text
    assert "- 模块：记忆系统" in sent_text
    assert "- 状态：完成" in sent_text
    assert "| 序号 | 模块 | 状态 |" not in sent_text
    assert "|" not in sent_text


@pytest.mark.asyncio
async def test_dingtalk_finalize_stream_normalizes_markdown_tables_before_card_update():
    from core.channels.adapters.dingtalk import DingTalkAdapter, _CardState

    adapter = DingTalkAdapter(app_key="ding-test", app_secret="secret")
    adapter._thinking_cards["chat-1:"] = _CardState(card_id="card-1", is_ai_card=True)

    captured: list[tuple[str, bool]] = []

    async def fake_stream_ai_card(card_id: str, content: str, *, finished: bool = False):
        captured.append((content, finished))

    adapter._stream_ai_card = fake_stream_ai_card

    ok = await adapter.finalize_stream(
        "chat-1",
        "# 标题\n| A | B |\n| --- | --- |\n| 1 | 2 |",
    )

    assert ok is True
    assert captured
    assert captured[0][1] is True
    assert "1." in captured[0][0]
    assert "- A：1" in captured[0][0]
    assert "- B：2" in captured[0][0]
    assert "| A | B |" not in captured[0][0]
