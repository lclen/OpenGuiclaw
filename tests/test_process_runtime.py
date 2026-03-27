import json
from pathlib import Path

import pytest


def _write_record(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_register_and_remove_run_record(tmp_path):
    from core import process_runtime

    record_path = process_runtime.register_current_run_record(
        tmp_path,
        pid=321,
        version="1.0.0",
        started_at=1710000000,
        mode="reload",
        is_frozen=False,
    )

    assert record_path.exists()
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert payload["pid"] == 321
    assert payload["mode"] == "reload"
    assert payload["version"] == "1.0.0"

    process_runtime.remove_run_record(record_path)
    assert not record_path.exists()


def test_collect_process_runtime_classifies_conflicts(tmp_path, monkeypatch):
    from core import process_runtime

    app_base = tmp_path
    run_dir = app_base / "data" / "run"
    _write_record(
        run_dir / "openguiclaw-server-222.json",
        {
            "pid": 222,
            "started_at": "2026-03-27T10:00:00",
            "mode": "reload",
            "version": "1.0.0",
            "app_dir": str(app_base),
            "executable": "python.exe",
            "is_frozen": False,
        },
    )
    _write_record(
        run_dir / "openguiclaw-server-333.json",
        {
            "pid": 333,
            "started_at": "2026-03-27T09:00:00",
            "mode": "watchdog",
            "version": "1.0.0",
            "app_dir": str(app_base),
            "executable": "python.exe",
            "is_frozen": False,
        },
    )

    snapshots = {
        111: {
            "pid": 111,
            "name": "python.exe",
            "exe": "python.exe",
            "cwd": str(app_base),
            "cmdline": ["python", "-m", "uvicorn", "core.server:app"],
            "cmdline_text": "python -m uvicorn core.server:app",
            "started_at": "2026-03-27T11:00:00",
        },
        222: {
            "pid": 222,
            "name": "python.exe",
            "exe": "python.exe",
            "cwd": str(app_base),
            "cmdline": ["python", "-m", "uvicorn", "core.server:app"],
            "cmdline_text": "python -m uvicorn core.server:app",
            "started_at": "2026-03-27T10:00:00",
        },
        444: {
            "pid": 444,
            "name": "openGuiclaw-server.exe",
            "exe": str(app_base / "openGuiclaw-server.exe"),
            "cwd": str(app_base),
            "cmdline": [str(app_base / "openGuiclaw-server.exe")],
            "cmdline_text": str(app_base / "openGuiclaw-server.exe"),
            "started_at": "2026-03-27T08:30:00",
        },
    }

    monkeypatch.setattr(process_runtime, "_get_process_snapshot", lambda pid: snapshots.get(pid))
    monkeypatch.setattr(process_runtime, "_iter_related_process_snapshots", lambda: list(snapshots.values()))

    runtime = process_runtime.collect_process_runtime(
        app_base,
        current_pid=111,
        version="1.0.0",
        started_at=1710000000,
        mode="reload",
        is_frozen=False,
    )

    conflict_types = {item["type"] for item in runtime["conflicts"]}
    assert {"running_conflict", "stale_record", "orphan_process"} <= conflict_types
    assert runtime["current_pid"] == 111
    assert any(item["status"] == "healthy_current" for item in runtime["running_processes"])


def test_cleanup_process_runtime_targets_handles_records_and_current_pid(tmp_path, monkeypatch):
    from core import process_runtime

    app_base = tmp_path
    run_dir = app_base / "data" / "run"
    stale_path = run_dir / "openguiclaw-server-333.json"
    conflict_path = run_dir / "openguiclaw-server-222.json"
    _write_record(
        stale_path,
        {
            "pid": 333,
            "started_at": "2026-03-27T09:00:00",
            "mode": "reload",
            "version": "1.0.0",
            "app_dir": str(app_base),
            "executable": "python.exe",
            "is_frozen": False,
        },
    )
    _write_record(
        conflict_path,
        {
            "pid": 222,
            "started_at": "2026-03-27T09:30:00",
            "mode": "reload",
            "version": "1.0.0",
            "app_dir": str(app_base),
            "executable": "python.exe",
            "is_frozen": False,
        },
    )

    live_pids = {111, 222}

    def fake_get_process_snapshot(pid: int):
        if pid not in live_pids:
            return None
        return {
            "pid": pid,
            "name": "python.exe" if pid != 222 else "openGuiclaw-server.exe",
            "exe": "python.exe" if pid != 222 else str(app_base / "openGuiclaw-server.exe"),
            "cwd": str(app_base),
            "cmdline": ["python", "-m", "uvicorn", "core.server:app"] if pid == 111 else [str(app_base / "openGuiclaw-server.exe")],
            "cmdline_text": "python -m uvicorn core.server:app" if pid == 111 else str(app_base / "openGuiclaw-server.exe"),
            "started_at": "2026-03-27T10:00:00",
        }

    monkeypatch.setattr(process_runtime, "_get_process_snapshot", fake_get_process_snapshot)
    monkeypatch.setattr(
        process_runtime,
        "_iter_related_process_snapshots",
        lambda: [fake_get_process_snapshot(pid) for pid in sorted(live_pids) if fake_get_process_snapshot(pid)],
    )

    def fake_terminate_process(pid: int):
        live_pids.discard(pid)
        return ("cleaned", None)

    monkeypatch.setattr(process_runtime, "_terminate_process", fake_terminate_process)

    result = process_runtime.cleanup_process_runtime_targets(
        app_base,
        current_pid=111,
        version="1.0.0",
        started_at=1710000000,
        target_records=["openguiclaw-server-333.json"],
        target_pids=[222, 111],
        mode="reload",
        is_frozen=False,
    )

    assert any(item["action"] == "remove_record" and item["status"] == "cleaned" for item in result["results"])
    assert any(item["pid"] == 222 and item["status"] == "cleaned" for item in result["results"])
    assert any(item["pid"] == 111 and item["status"] == "skipped" for item in result["results"])
    assert not stale_path.exists()
    assert not conflict_path.exists()
