from types import SimpleNamespace

import pytest


def _runtime_snapshot(*, conflicts=None, endpoints=None, network_status="healthy", im_channels=None):
    return {
        "environment": {
            "system": {"pid": 321, "frozen": False},
            "restart": {"mode": "reload", "supported": True, "reason": None},
            "network": {"proxies": {}, "connectivity": {"status": "ok", "latency_ms": 12}},
            "dependencies": {"fastapi": True},
        },
        "runtime": {
            "service": {
                "status": "ok",
                "pid": 321,
                "version": "test-version",
                "started_at": "2026-03-27T10:00:00",
                "uptime_seconds": 30,
                "restart_mode": "reload",
            },
            "process_runtime": {
                "current_pid": 321,
                "conflicts": conflicts or [],
                "run_records": [],
                "running_processes": [],
            },
        },
        "network_matrix": {
            "status": network_status,
            "target_name": "chat:primary",
            "target_label": "Primary",
            "summary": "默认网络测活成功" if network_status == "healthy" else "存在网络问题",
            "diagnosis_code": None,
            "hint": None,
            "results": [],
        },
        "endpoints": {
            "status": "healthy" if endpoints else "unknown",
            "active_target": "chat:primary" if endpoints else None,
            "results": endpoints or [],
        },
        "im_channels": {
            "status": "healthy" if im_channels else "unknown",
            "results": im_channels or [],
        },
    }


@pytest.mark.asyncio
async def test_daily_selfcheck_cleans_stale_records_and_sends_im_summary(tmp_path, monkeypatch):
    from core import tasks

    monkeypatch.setattr(tasks, "_APP_BASE", tmp_path)
    monkeypatch.setitem(tasks.app_state, "server_version", "test-version")
    monkeypatch.setitem(tasks.app_state, "server_started_at", 1_711_000_000.0)
    monkeypatch.setitem(tasks.app_state, "agent", None)
    monkeypatch.setitem(tasks.app_state, "task_scheduler", None)

    snapshots = [
        _runtime_snapshot(
            conflicts=[
                {
                    "type": "stale_record",
                    "pid": 999,
                    "record_id": "openguiclaw-server-999.json",
                    "summary": "运行记录文件仍存在，但对应 PID 已不存在",
                }
            ]
        ),
        _runtime_snapshot(),
    ]

    async def fake_collect_runtime(*args, **kwargs):
        return snapshots.pop(0)

    deliveries = []
    pushed = []

    monkeypatch.setattr(tasks, "collect_runtime_selfcheck_snapshot", fake_collect_runtime)
    monkeypatch.setattr(
        tasks,
        "cleanup_process_runtime_targets",
        lambda *args, **kwargs: {
            "results": [{"record_id": "openguiclaw-server-999.json", "action": "remove_record", "status": "cleaned"}],
            "remaining_conflicts": [],
        },
    )
    monkeypatch.setattr(tasks, "deliver_automation_event", lambda role, content, **kwargs: deliveries.append((role, content, kwargs)) or ([], None))
    monkeypatch.setattr(tasks, "_scan_log_error_summary", lambda: {})

    task = SimpleNamespace(
        get_delivery_targets=lambda: [
            {
                "kind": "im_session",
                "workspace_id": None,
                "session_id": "im:telegram:test-bot:chat-1",
                "channel": "telegram_test-bot",
                "chat_id": "chat-1",
            }
        ]
    )

    success, status = await tasks._system_daily_selfcheck(lambda event: pushed.append(event), task)

    assert success is True
    assert "可恢复问题" not in status
    assert len(deliveries) == 2
    assert deliveries[0][1].startswith("## 🔍 系统自检报告")
    assert deliveries[1][1].startswith("🔍 系统自检摘要")
    assert pushed[-1]["content"].startswith("🔍 系统自检摘要")
    assert (tmp_path / "data" / "selfcheck" / "latest.json").exists()


@pytest.mark.asyncio
async def test_daily_selfcheck_handles_empty_runtime_without_failing(tmp_path, monkeypatch):
    from core import tasks

    monkeypatch.setattr(tasks, "_APP_BASE", tmp_path)
    monkeypatch.setitem(tasks.app_state, "server_version", "test-version")
    monkeypatch.setitem(tasks.app_state, "server_started_at", 1_711_000_000.0)
    monkeypatch.setitem(tasks.app_state, "agent", None)
    monkeypatch.setitem(tasks.app_state, "task_scheduler", None)

    async def fake_collect_runtime(*args, **kwargs):
        return _runtime_snapshot(endpoints=[], im_channels=[], network_status="unknown")

    deliveries = []
    monkeypatch.setattr(tasks, "collect_runtime_selfcheck_snapshot", fake_collect_runtime)
    monkeypatch.setattr(tasks, "deliver_automation_event", lambda role, content, **kwargs: deliveries.append((role, content, kwargs)) or ([], None))
    monkeypatch.setattr(tasks, "_scan_log_error_summary", lambda: {})

    task = SimpleNamespace(
        get_delivery_targets=lambda: [
            {"kind": "workspace_inbox", "workspace_id": "default", "session_id": None, "channel": None, "chat_id": None}
        ]
    )

    success, status = await tasks._system_daily_selfcheck(lambda event: None, task)

    assert success is True
    assert status.startswith("✅")
    assert len(deliveries) == 1
    assert "当前未配置可测活端点" in deliveries[0][1]

