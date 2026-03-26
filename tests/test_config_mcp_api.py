from unittest.mock import ANY, MagicMock, patch

import httpx
import pytest_asyncio
from fastapi import FastAPI


@pytest_asyncio.fixture
async def client():
    from core.routes.config import router

    app = FastAPI()
    app.include_router(router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


async def test_get_mcp_servers_exposes_runtime_status_fields(client):
    payload = {
        "mcpServers": {
            "context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp@latest"]},
        }
    }
    server_statuses = [
        {
            "name": "context7",
            "transport": "stdio",
            "connected": False,
            "tool_count": 0,
            "catalog_tool_count": 0,
            "tools": [],
            "last_connect_attempt_at": "2026-03-26T10:00:00+00:00",
            "last_connect_error": "连接失败: context7",
            "last_connect_result": "error",
            "auto_connected": True,
        }
    ]

    with patch("core.routes.config._load_mcp_config", return_value=payload), patch(
        "plugins.mcp_gateway.get_server_statuses",
        return_value=server_statuses,
    ), patch("plugins.mcp_gateway.MCP_SDK_AVAILABLE", True):
        response = await client.get("/api/mcp/servers")

    assert response.status_code == 200
    data = response.json()
    assert data["mcpServers"]["context7"]["command"] == "npx"
    assert data["servers"][0]["last_connect_result"] == "error"
    assert data["servers"][0]["last_connect_error"] == "连接失败: context7"
    assert data["servers"][0]["auto_connected"] is True


async def test_restart_backend_reload_schedules_detached_timer(client):
    timer = MagicMock()

    with patch("core.routes.config._detect_restart_mode", return_value="reload"), patch(
        "core.routes.config.threading.Timer",
        return_value=timer,
    ) as timer_cls:
        response = await client.post("/api/system/restart")

    assert response.status_code == 200
    assert response.json()["mode"] == "reload"
    timer_cls.assert_called_once_with(0.15, ANY)
    assert timer.daemon is True
    timer.start.assert_called_once()


async def test_restart_backend_watchdog_schedules_detached_timer(client):
    timer = MagicMock()

    with patch("core.routes.config._detect_restart_mode", return_value="watchdog"), patch(
        "core.routes.config.threading.Timer",
        return_value=timer,
    ) as timer_cls:
        response = await client.post("/api/system/restart")

    assert response.status_code == 200
    assert response.json()["mode"] == "watchdog"
    timer_cls.assert_called_once_with(0.15, ANY)
    assert timer.daemon is True
    timer.start.assert_called_once()


async def test_restart_backend_returns_409_when_unsupported(client):
    with patch("core.routes.config._detect_restart_mode", return_value="unsupported"):
        response = await client.post("/api/system/restart")

    assert response.status_code == 409
