import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI


@pytest_asyncio.fixture
async def client():
    from core.routes.agents import router

    app = FastAPI()
    app.include_router(router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


def _write_config(base_dir: Path, payload: dict) -> Path:
    config_path = base_dir / "config.json"
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return config_path


@pytest.mark.asyncio
async def test_get_diagnostics_exposes_pid(client):
    response = await client.get("/api/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert "system" in payload
    assert isinstance(payload["system"].get("pid"), int)
    assert "restart" in payload
    assert "dependencies" in payload
    assert "process_runtime" in payload


@pytest.mark.asyncio
async def test_health_check_returns_all_targets_without_mutation(client, tmp_path, monkeypatch):
    from core.routes import agents

    config_payload = {
        "active_chat_endpoint_id": "primary",
        "chat_endpoints": [
            {
                "id": "primary",
                "name": "Primary Chat",
                "base_url": "https://example.invalid/v1",
                "api_key": "sk-test-primary",
                "model": "gpt-test",
            }
        ],
        "vision": {
            "base_url": "https://vision.invalid/v1",
            "api_key": "sk-test-vision",
            "model": "vision-test",
        },
        "api": {
            "base_url": "https://legacy.invalid/v1",
            "api_key": "sk-test-legacy",
            "model": "legacy-test",
        },
    }
    config_path = _write_config(tmp_path, config_payload)
    original_text = config_path.read_text(encoding="utf-8")

    monkeypatch.setattr(agents, "_APP_BASE", tmp_path)

    async def fake_probe(target, timeout_seconds=15.0):
        return {
            "name": target["name"],
            "label": target["label"],
            "kind": target["kind"],
            "role": target["role"],
            "status": "healthy",
            "latency_ms": 12,
            "error": None,
            "last_checked_at": "2026-03-27T10:00:00",
        }

    with patch("core.routes.agents._probe_health_target", side_effect=fake_probe):
        response = await client.post("/api/health/check", json={})

    assert response.status_code == 200
    payload = response.json()
    assert [item["name"] for item in payload["results"]] == ["chat:primary", "role:vision"]
    assert config_path.read_text(encoding="utf-8") == original_text


@pytest.mark.asyncio
async def test_health_check_returns_single_named_target(client, tmp_path, monkeypatch):
    from core.routes import agents

    _write_config(
        tmp_path,
        {
            "chat_endpoints": [
                {
                    "id": "primary",
                    "name": "Primary Chat",
                    "base_url": "https://example.invalid/v1",
                    "api_key": "sk-test-primary",
                    "model": "gpt-test",
                }
            ],
            "embedding": {
                "base_url": "https://embedding.invalid/v1",
                "api_key": "sk-test-embedding",
                "model": "embed-test",
            },
        },
    )
    monkeypatch.setattr(agents, "_APP_BASE", tmp_path)

    async def fake_probe(target, timeout_seconds=15.0):
        return {
            "name": target["name"],
            "label": target["label"],
            "kind": target["kind"],
            "role": target["role"],
            "status": "healthy",
            "latency_ms": 8,
            "error": None,
            "last_checked_at": "2026-03-27T10:00:00",
        }

    with patch("core.routes.agents._probe_health_target", side_effect=fake_probe) as probe:
        response = await client.post("/api/health/check", json={"endpoint_name": "role:embedding"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"] == [
        {
            "name": "role:embedding",
            "label": "嵌入模型",
            "kind": "role",
            "role": "embedding",
            "status": "healthy",
            "latency_ms": 8,
            "error": None,
            "last_checked_at": "2026-03-27T10:00:00",
        }
    ]
    assert probe.call_count == 1


@pytest.mark.asyncio
async def test_health_check_unknown_target_returns_404(client, tmp_path, monkeypatch):
    from core.routes import agents

    _write_config(tmp_path, {"chat_endpoints": []})
    monkeypatch.setattr(agents, "_APP_BASE", tmp_path)

    response = await client.post("/api/health/check", json={"endpoint_name": "chat:missing"})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_probe_health_target_returns_timeout_result():
    from core.routes import agents

    with patch("core.routes.agents.asyncio.to_thread", side_effect=agents.asyncio.TimeoutError):
        result = await agents._probe_health_target(
            {
                "name": "role:api",
                "label": "主模型",
                "kind": "role",
                "role": "api",
                "base_url": "https://example.invalid/v1",
                "model": "gpt-test",
            },
            timeout_seconds=1.0,
        )

    assert result["status"] == "unhealthy"
    assert result["error_code"] == "timeout"
    assert "超时" in result["error"]


@pytest.mark.asyncio
async def test_probe_health_target_returns_unknown_for_missing_configuration():
    from core.routes import agents

    result = await agents._probe_health_target(
        {
            "name": "role:vision",
            "label": "视觉模型",
            "kind": "role",
            "role": "vision",
            "base_url": "",
            "model": "",
        }
    )

    assert result["status"] == "unknown"
    assert result["configured"] is False
    assert result["error_code"] == "missing_base_url"
    assert "Base URL" in result["error"]


@pytest.mark.asyncio
async def test_cleanup_process_runtime_endpoint_returns_results(client):
    from core.routes import agents

    with patch(
        "core.routes.agents.cleanup_process_runtime_targets",
        return_value={
            "results": [
                {"pid": 222, "action": "terminate_then_kill", "status": "cleaned"},
                {"pid": 111, "action": "skip", "status": "skipped", "error": "refusing to cleanup current server pid"},
            ],
            "remaining_conflicts": [],
        },
    ) as cleanup:
        response = await client.post(
            "/api/diagnostics/process/cleanup",
            json={"target_pids": [222, 111], "target_records": ["openguiclaw-server-222.json"]},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"][0]["status"] == "cleaned"
    assert payload["results"][1]["status"] == "skipped"
    cleanup.assert_called_once()
