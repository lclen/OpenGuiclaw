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
    assert "1. 排名: 1 | 热点事件: 美伊局势 | 热度: 🔥🔥🔥 | 类别: 国际" in normalized
    assert "| 排名 |" not in normalized


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
    assert "1. A: 1 | B: 2" in outgoing.content.text
