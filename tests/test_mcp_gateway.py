import importlib

import pytest

import plugins.mcp_gateway as mcp_gateway


@pytest.fixture
def gateway_module(monkeypatch):
    module = importlib.reload(mcp_gateway)
    monkeypatch.setattr(module, "MCP_SDK_AVAILABLE", True)
    module._ACTIVE_CLIENTS.clear()
    module._SERVER_RUNTIME_STATUS.clear()
    return module


def test_connect_server_sync_records_success(gateway_module, monkeypatch):
    monkeypatch.setattr(
        gateway_module,
        "load_servers_from_config",
        lambda config_path=None: {"context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp@latest"]}},
    )

    def fake_run_async(coro, timeout=None):
        coro.close()
        gateway_module._ACTIVE_CLIENTS["context7"] = {"tools": ["query-docs"], "tool_details": [{"name": "query-docs"}]}
        gateway_module._mark_connect_success("context7", auto_connected=True)
        return {"status": "connected", "server_name": "context7", "connected": True, "tool_count": 1}

    monkeypatch.setattr(gateway_module, "_run_async", fake_run_async)

    result = gateway_module.connect_server_sync("context7", auto_connected=True)

    assert result["status"] == "connected"
    status = gateway_module.get_server_statuses()[0]
    assert status["connected"] is True
    assert status["last_connect_result"] == "connected"
    assert status["last_connect_error"] is None
    assert status["auto_connected"] is True


def test_connect_server_sync_records_timeout(gateway_module, monkeypatch):
    monkeypatch.setattr(
        gateway_module,
        "load_servers_from_config",
        lambda config_path=None: {"context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp@latest"]}},
    )
    monkeypatch.setattr(gateway_module, "_run_async", lambda coro, timeout=None: (coro.close(), None)[1])

    result = gateway_module.connect_server_sync("context7", auto_connected=True)

    assert result["status"] == "error"
    status = gateway_module.get_server_statuses()[0]
    assert status["connected"] is False
    assert status["last_connect_result"] == "timeout"
    assert "连接超时" in status["last_connect_error"]
    assert status["auto_connected"] is True


def test_connect_all_enabled_servers_skips_disabled_and_continues(gateway_module, monkeypatch):
    monkeypatch.setattr(
        gateway_module,
        "load_servers_from_config",
        lambda config_path=None: {
            "ok-server": {"command": "npx"},
            "bad-server": {"command": "npx"},
            "disabled-server": {"command": "npx", "disabled": True},
        },
    )

    def fake_connect(name, auto_connected=False):
        if name == "ok-server":
            gateway_module._mark_connect_success(name, auto_connected=auto_connected)
            gateway_module._ACTIVE_CLIENTS[name] = {"tools": ["alpha"], "tool_details": [{"name": "alpha"}]}
            return {"status": "connected", "server_name": name, "connected": True, "tool_count": 1}
        gateway_module._mark_connect_failure(name, f"连接失败: {name}", auto_connected=auto_connected)
        return {"status": "error", "error": f"连接失败: {name}"}

    monkeypatch.setattr(gateway_module, "connect_server_sync", fake_connect)

    result = gateway_module.connect_all_enabled_mcp_servers()

    assert result["attempted"] == 2
    assert result["connected"] == 1
    assert result["failed"] == 1
    statuses = {item["name"]: item for item in gateway_module.get_server_statuses()}
    assert statuses["ok-server"]["connected"] is True
    assert statuses["bad-server"]["last_connect_result"] == "error"
    assert statuses["disabled-server"]["last_connect_result"] == "not_attempted"
