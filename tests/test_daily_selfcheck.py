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


def _ensure_required_dirs(base_dir):
    for rel_path in [
        "data",
        "data/sessions",
        "data/memory",
        "data/scheduler",
        "data/diary",
        "data/journals",
        "data/identities",
        "data/identity",
        "data/plans",
        "data/consolidation",
    ]:
        (base_dir / rel_path).mkdir(parents=True, exist_ok=True)


@pytest.mark.asyncio
async def test_daily_selfcheck_cleans_stale_records_and_sends_im_summary(tmp_path, monkeypatch):
    from core import tasks

    _ensure_required_dirs(tmp_path)
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
    assert status.startswith("✅")
    assert len(deliveries) == 2
    assert deliveries[0][1].startswith("## 🔍 系统自检报告")
    assert deliveries[1][1].startswith("🔍 系统自检摘要")
    assert pushed[-1]["content"].startswith("🔍 系统自检摘要")
    assert (tmp_path / "data" / "selfcheck" / "latest.json").exists()


@pytest.mark.asyncio
async def test_daily_selfcheck_handles_empty_runtime_without_failing(tmp_path, monkeypatch):
    from core import tasks

    _ensure_required_dirs(tmp_path)
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


@pytest.mark.asyncio
async def test_daily_selfcheck_initializes_missing_dirs_without_degrading(tmp_path, monkeypatch):
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
    assert tmp_path.joinpath("data", "consolidation").exists()
    assert "总体状态**: ✅" in deliveries[0][1]


@pytest.mark.asyncio
async def test_daily_selfcheck_survives_artifact_write_failure(tmp_path, monkeypatch):
    from core import tasks

    _ensure_required_dirs(tmp_path)
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
    monkeypatch.setattr(tasks, "_write_selfcheck_file", lambda path, content: (_ for _ in ()).throw(OSError("disk full")))

    task = SimpleNamespace(
        get_delivery_targets=lambda: [
            {"kind": "workspace_inbox", "workspace_id": "default", "session_id": None, "channel": None, "chat_id": None}
        ]
    )

    success, status = await tasks._system_daily_selfcheck(lambda event: None, task)

    assert success is True
    assert status.startswith("✅")
    assert "报告落盘" in deliveries[0][1]
    assert "disk full" in deliveries[0][1]


@pytest.mark.asyncio
async def test_daily_selfcheck_fanouts_to_subscribed_im_sessions(tmp_path, monkeypatch):
    from core import tasks
    from core.im_bots import make_channel_name, make_im_session_id
    from core.im_selfcheck_subscriptions import upsert_selfcheck_subscription

    _ensure_required_dirs(tmp_path)
    monkeypatch.setattr(tasks, "_APP_BASE", tmp_path)
    monkeypatch.setattr("core.im_selfcheck_subscriptions._APP_BASE", tmp_path)
    monkeypatch.setitem(tasks.app_state, "server_version", "test-version")
    monkeypatch.setitem(tasks.app_state, "server_started_at", 1_711_000_000.0)
    monkeypatch.setitem(tasks.app_state, "agent", None)
    monkeypatch.setitem(tasks.app_state, "task_scheduler", None)
    (tmp_path / "config.json").write_text(
        __import__("json").dumps(
            {
                "im_bots": [
                    {
                        "id": "ding-main",
                        "name": "Ding Main",
                        "platform": "dingtalk",
                        "enabled": True,
                        "credentials": {"client_id": "cid", "client_secret": "secret", "agent_id": "123"},
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    channel_name = make_channel_name("dingtalk", "ding-main")
    session_id = make_im_session_id(channel_name, "chat-001")
    upsert_selfcheck_subscription(session_id=session_id, channel_name=channel_name, chat_id="chat-001")
    monkeypatch.setitem(
        tasks.app_state,
        "gateway",
        SimpleNamespace(adapters={channel_name: SimpleNamespace(_running=True)}),
    )

    async def fake_collect_runtime(*args, **kwargs):
        return _runtime_snapshot(endpoints=[], im_channels=[], network_status="unknown")

    deliveries = []
    monkeypatch.setattr(tasks, "collect_runtime_selfcheck_snapshot", fake_collect_runtime)
    monkeypatch.setattr(tasks, "_scan_log_error_summary", lambda: {})
    monkeypatch.setattr(tasks, "deliver_automation_event", lambda role, content, **kwargs: deliveries.append((role, content, kwargs)) or ([], None))

    task = SimpleNamespace(
        get_delivery_targets=lambda: [
            {"kind": "workspace_inbox", "workspace_id": "default", "session_id": None, "channel": None, "chat_id": None}
        ]
    )

    success, status = await tasks._system_daily_selfcheck(lambda event: None, task)

    assert success is True
    assert status.startswith("✅")
    workspace_deliveries = [item for item in deliveries if item[2].get("target_kind") == "workspace_inbox"]
    subscription_deliveries = [item for item in deliveries if item[2].get("target_session_id") == session_id]
    assert len(workspace_deliveries) == 1
    assert len(subscription_deliveries) == 1
    assert subscription_deliveries[0][1].startswith("🔍 系统自检摘要")
