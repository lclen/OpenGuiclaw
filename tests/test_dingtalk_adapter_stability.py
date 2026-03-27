import asyncio
import pytest

from core.channels.adapters.dingtalk import DingTalkAdapter, DingTalkStreamState


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _TokenHttpClient:
    def __init__(self):
        self.post_calls = 0
        self.get_calls = 0

    async def post(self, url, json):
        self.post_calls += 1
        await asyncio.sleep(0.01)
        return _FakeResponse({"accessToken": "new-token", "expireIn": 7200})

    async def get(self, url, params):
        self.get_calls += 1
        await asyncio.sleep(0.01)
        return _FakeResponse({"errcode": 0, "access_token": "old-token", "expires_in": 7200})


@pytest.mark.asyncio
async def test_refresh_token_uses_lock_to_prevent_duplicate_requests(monkeypatch):
    monkeypatch.setattr("core.channels.adapters.dingtalk._import_httpx", lambda: None)
    adapter = DingTalkAdapter(app_key="ak", app_secret="sk", bot_id="ding-1")
    client = _TokenHttpClient()
    adapter._http_client = client

    first, second = await asyncio.gather(adapter._refresh_token(), adapter._refresh_token())

    assert first == "new-token"
    assert second == "new-token"
    assert client.post_calls == 1


@pytest.mark.asyncio
async def test_refresh_old_token_uses_lock_to_prevent_duplicate_requests(monkeypatch):
    monkeypatch.setattr("core.channels.adapters.dingtalk._import_httpx", lambda: None)
    adapter = DingTalkAdapter(app_key="ak", app_secret="sk", bot_id="ding-1")
    client = _TokenHttpClient()
    adapter._http_client = client

    first, second = await asyncio.gather(adapter._refresh_old_token(), adapter._refresh_old_token())

    assert first == "old-token"
    assert second == "old-token"
    assert client.get_calls == 1


@pytest.mark.asyncio
async def test_stop_disables_reconnect_and_closes_websocket(monkeypatch):
    adapter = DingTalkAdapter(app_key="ak", app_secret="sk", bot_id="ding-1")
    adapter._running = True
    adapter._set_stream_state(DingTalkStreamState.RUNNING)

    class _FakeWebSocket:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    fake_websocket = _FakeWebSocket()

    class _FakeClient:
        def __init__(self):
            self.websocket = fake_websocket

        def open_connection(self):
            return "should be disabled"

    adapter._stream_client = _FakeClient()
    adapter._stream_loop = asyncio.get_running_loop()
    adapter._stream_thread = None

    class _FakeHttpClient:
        def __init__(self):
            self.closed = False

        async def aclose(self):
            self.closed = True

    adapter._http_client = _FakeHttpClient()

    await adapter.stop()

    assert adapter._stream_client is None
    assert fake_websocket.closed is True
    assert adapter._http_client.closed is True
    assert adapter._stream_thread is None
    assert adapter._stream_loop is None
    assert adapter._running is False
