import pytest


@pytest.mark.asyncio
async def test_probe_network_matrix_detects_proxy_issue(monkeypatch):
    from core import runtime_diagnostics

    async def fake_probe(target, timeout_seconds=5.0, probe_mode="default"):
        if probe_mode == "no_proxy":
            return {
                "name": target["name"],
                "status": "healthy",
                "configured": True,
                "probe_mode": probe_mode,
                "probe_label": "禁用代理",
                "error": None,
                "error_code": None,
                "hint": None,
            }
        return {
            "name": target["name"],
            "status": "unhealthy",
            "configured": True,
            "probe_mode": probe_mode,
            "probe_label": probe_mode,
            "error": "连接失败",
            "error_code": "connection_failed",
            "hint": "检查网络",
        }

    monkeypatch.setattr(runtime_diagnostics, "probe_health_target", fake_probe)

    result = await runtime_diagnostics.probe_network_matrix(
        {"name": "chat:primary", "label": "Primary", "base_url": "https://example.invalid/v1", "model": "gpt-test"}
    )

    assert result["status"] == "degraded"
    assert result["diagnosis_code"] == "proxy_issue"
    assert "代理" in result["summary"]
