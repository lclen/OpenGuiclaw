import httpx
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def client():
    from core.server import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_health_api_returns_runtime_metadata(client):
    response = await client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert isinstance(payload["pid"], int)
    assert isinstance(payload["version"], str)
    assert isinstance(payload["started_at"], str)
    assert isinstance(payload["uptime_seconds"], int)
    assert payload["restart_mode"] in {"watchdog", "reload", "unsupported"}
