"""Helpers for server process runtime registration, diagnostics, and cleanup."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

from core.state import logger

RUN_RECORD_PREFIX = "openguiclaw-server-"
RUN_RECORD_GLOB = f"{RUN_RECORD_PREFIX}*.json"
TERMINATE_TIMEOUT_SECONDS = 2.0
_PROCESS_NAME_MARKERS = ("openguiclaw", "open-guiclaw")
_PROCESS_CMD_MARKERS = ("core.server:app", "launcher.py", "openguiclaw-server", "openguiclaw")


def detect_runtime_mode() -> str:
    if os.environ.get("OPENGUICLAW_WATCHDOG") == "1":
        return "watchdog"
    if "--reload" in sys.argv:
        return "reload"
    return "unsupported"


def run_records_dir(app_base: Path) -> Path:
    return app_base / "data" / "run"


def build_current_run_record(
    app_base: Path,
    *,
    pid: int,
    version: str,
    started_at: float,
    mode: str | None = None,
    is_frozen: bool | None = None,
) -> dict[str, Any]:
    normalized_mode = mode or detect_runtime_mode()
    frozen = getattr(sys, "frozen", False) if is_frozen is None else bool(is_frozen)
    return {
        "pid": int(pid),
        "started_at": datetime.fromtimestamp(started_at).isoformat(timespec="seconds"),
        "mode": normalized_mode,
        "version": version,
        "app_dir": str(app_base),
        "cwd": os.getcwd(),
        "executable": sys.executable,
        "is_frozen": frozen,
    }


def register_current_run_record(
    app_base: Path,
    *,
    pid: int,
    version: str,
    started_at: float,
    mode: str | None = None,
    is_frozen: bool | None = None,
) -> Path:
    payload = build_current_run_record(
        app_base,
        pid=pid,
        version=version,
        started_at=started_at,
        mode=mode,
        is_frozen=is_frozen,
    )
    records_dir = run_records_dir(app_base)
    records_dir.mkdir(parents=True, exist_ok=True)
    record_path = records_dir / f"{RUN_RECORD_PREFIX}{pid}.json"
    record_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return record_path


def remove_run_record(record_path: str | Path | None) -> None:
    if not record_path:
        return
    try:
        path = Path(record_path)
        if path.exists():
            path.unlink()
    except Exception as exc:
        logger.warning("Failed to remove run record %s: %s", record_path, exc)


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _parse_datetime(value: Any) -> float | None:
    raw = _safe_text(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return None


def _normalize_run_record(path: Path, payload: dict[str, Any] | None, error: str | None = None) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    pid_raw = data.get("pid")
    pid = pid_raw if isinstance(pid_raw, int) else None
    started_at = _safe_text(data.get("started_at"))
    return {
        "record_id": path.name,
        "file_path": str(path),
        "pid": pid,
        "started_at": started_at,
        "mode": _safe_text(data.get("mode")) or "unknown",
        "version": _safe_text(data.get("version")) or "unknown",
        "app_dir": _safe_text(data.get("app_dir")),
        "cwd": _safe_text(data.get("cwd")),
        "executable": _safe_text(data.get("executable")),
        "is_frozen": bool(data.get("is_frozen", False)),
        "record_error": error,
    }


def load_run_records(app_base: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(run_records_dir(app_base).glob(RUN_RECORD_GLOB)):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            records.append(_normalize_run_record(path, payload))
        except Exception as exc:
            records.append(_normalize_run_record(path, None, error=str(exc)))
    return records


def _snapshot_from_psutil_process(proc: psutil.Process) -> dict[str, Any] | None:
    try:
        with proc.oneshot():
            pid = proc.pid
            name = _safe_text(proc.name())
            exe = _safe_text(proc.exe())
            try:
                cwd = _safe_text(proc.cwd())
            except (psutil.AccessDenied, psutil.ZombieProcess, OSError):
                cwd = ""
            try:
                cmdline_list = proc.cmdline()
            except (psutil.AccessDenied, psutil.ZombieProcess, OSError):
                cmdline_list = []
            create_time = proc.create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None

    return {
        "pid": pid,
        "name": name,
        "exe": exe,
        "cwd": cwd,
        "cmdline": [str(item) for item in cmdline_list if str(item).strip()],
        "cmdline_text": " ".join(str(item) for item in cmdline_list if str(item).strip()),
        "started_at": datetime.fromtimestamp(create_time).isoformat(timespec="seconds"),
    }


def _get_process_snapshot(pid: int) -> dict[str, Any] | None:
    try:
        return _snapshot_from_psutil_process(psutil.Process(pid))
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None


def _iter_related_process_snapshots() -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for proc in psutil.process_iter():
        snapshot = _snapshot_from_psutil_process(proc)
        if snapshot:
            snapshots.append(snapshot)
    return snapshots


def _looks_like_server_process(snapshot: dict[str, Any], app_base: Path) -> bool:
    name = _safe_text(snapshot.get("name")).lower()
    exe = _safe_text(snapshot.get("exe")).lower()
    cwd = _safe_text(snapshot.get("cwd")).lower()
    cmdline = _safe_text(snapshot.get("cmdline_text")).lower()
    haystack = " ".join(part for part in (name, exe, cwd, cmdline) if part)
    app_dir = str(app_base).lower()

    has_name_marker = any(marker in name or marker in exe for marker in _PROCESS_NAME_MARKERS)
    has_cmd_marker = any(marker in haystack for marker in _PROCESS_CMD_MARKERS)
    has_app_marker = bool(app_dir and app_dir in haystack)

    if has_name_marker:
        return True
    if has_cmd_marker and (has_app_marker or "uvicorn" in haystack or "python" in haystack):
        return True
    return False


def _build_conflict_item(
    *,
    conflict_type: str,
    summary: str,
    pid: int | None = None,
    record_id: str | None = None,
    file_path: str | None = None,
    cleanup_allowed: bool,
) -> dict[str, Any]:
    return {
        "type": conflict_type,
        "pid": pid,
        "record_id": record_id,
        "file_path": file_path,
        "summary": summary,
        "cleanup_allowed": cleanup_allowed,
    }


def collect_process_runtime(
    app_base: Path,
    *,
    current_pid: int,
    version: str,
    started_at: float,
    mode: str | None = None,
    is_frozen: bool | None = None,
) -> dict[str, Any]:
    normalized_mode = mode or detect_runtime_mode()
    current_snapshot = _get_process_snapshot(current_pid) or {
        "pid": current_pid,
        "name": Path(sys.executable).name,
        "exe": sys.executable,
        "cwd": os.getcwd(),
        "cmdline": sys.argv[:],
        "cmdline_text": " ".join(sys.argv),
        "started_at": datetime.fromtimestamp(started_at).isoformat(timespec="seconds"),
    }
    current_run_record = build_current_run_record(
        app_base,
        pid=current_pid,
        version=version,
        started_at=started_at,
        mode=normalized_mode,
        is_frozen=is_frozen,
    )
    records = load_run_records(app_base)

    running_processes: list[dict[str, Any]] = [
        {
            "pid": current_pid,
            "status": "healthy_current",
            "name": current_snapshot.get("name") or "current-server",
            "executable": current_snapshot.get("exe") or current_run_record["executable"],
            "cmdline": current_snapshot.get("cmdline", []),
            "started_at": current_snapshot.get("started_at") or current_run_record["started_at"],
            "mode": normalized_mode,
            "record_id": f"{RUN_RECORD_PREFIX}{current_pid}.json",
            "summary": "当前正在服务的后端进程",
            "cleanup_allowed": False,
        }
    ]
    conflicts: list[dict[str, Any]] = []
    seen_running_pids = {current_pid}
    normalized_records: list[dict[str, Any]] = []

    for record in records:
        pid = record.get("pid")
        runtime_status = "stale_record"
        process_snapshot = _get_process_snapshot(pid) if isinstance(pid, int) else None
        cleanup_allowed = True

        if pid == current_pid:
            runtime_status = "healthy_current"
            cleanup_allowed = False
        elif process_snapshot:
            runtime_status = "running_conflict"
            seen_running_pids.add(pid)
            running_processes.append(
                {
                    "pid": pid,
                    "status": runtime_status,
                    "name": process_snapshot.get("name") or "residual-server",
                    "executable": process_snapshot.get("exe") or record.get("executable"),
                    "cmdline": process_snapshot.get("cmdline", []),
                    "started_at": process_snapshot.get("started_at") or record.get("started_at"),
                    "mode": record.get("mode") or "unknown",
                    "record_id": record["record_id"],
                    "summary": "发现旧实例仍在运行，与当前后端形成冲突",
                    "cleanup_allowed": True,
                }
            )
            conflicts.append(
                _build_conflict_item(
                    conflict_type="running_conflict",
                    pid=pid,
                    record_id=record["record_id"],
                    file_path=record["file_path"],
                    summary="运行记录对应的旧实例仍存活",
                    cleanup_allowed=True,
                )
            )
        else:
            reason = "运行记录文件仍存在，但对应 PID 已不存在"
            if record.get("record_error"):
                reason = f"运行记录损坏或不可读：{record['record_error']}"
            conflicts.append(
                _build_conflict_item(
                    conflict_type="stale_record",
                    pid=pid,
                    record_id=record["record_id"],
                    file_path=record["file_path"],
                    summary=reason,
                    cleanup_allowed=True,
                )
            )

        normalized_records.append(
            {
                **record,
                "runtime_status": runtime_status,
                "cleanup_allowed": cleanup_allowed,
            }
        )

    for snapshot in _iter_related_process_snapshots():
        pid = snapshot["pid"]
        if pid in seen_running_pids:
            continue
        if not _looks_like_server_process(snapshot, app_base):
            continue
        seen_running_pids.add(pid)
        running_processes.append(
            {
                "pid": pid,
                "status": "orphan_process",
                "name": snapshot.get("name") or "orphan-process",
                "executable": snapshot.get("exe"),
                "cmdline": snapshot.get("cmdline", []),
                "started_at": snapshot.get("started_at"),
                "mode": "unknown",
                "record_id": None,
                "summary": "发现疑似 OpenGuiclaw 旧进程，但没有对应运行记录",
                "cleanup_allowed": True,
            }
        )
        conflicts.append(
            _build_conflict_item(
                conflict_type="orphan_process",
                pid=pid,
                summary="疑似 OpenGuiclaw 残留进程，没有对应运行记录",
                cleanup_allowed=True,
            )
        )

    normalized_records.sort(key=lambda item: _parse_datetime(item.get("started_at")) or 0, reverse=True)
    running_processes.sort(key=lambda item: (0 if item["status"] == "healthy_current" else 1, item["pid"]))

    return {
        "current_pid": current_pid,
        "current_record": current_run_record,
        "run_records": normalized_records,
        "running_processes": running_processes,
        "conflicts": conflicts,
        "cleanup_supported": True,
    }


def _terminate_process(pid: int) -> tuple[str, str | None]:
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return ("cleaned", None)

    try:
        proc.terminate()
        proc.wait(timeout=TERMINATE_TIMEOUT_SECONDS)
        return ("cleaned", None)
    except psutil.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(timeout=TERMINATE_TIMEOUT_SECONDS)
            return ("cleaned", None)
        except psutil.NoSuchProcess:
            return ("cleaned", None)
        except Exception as exc:
            return ("failed", str(exc))
    except psutil.NoSuchProcess:
        return ("cleaned", None)
    except Exception as exc:
        return ("failed", str(exc))


def cleanup_process_runtime_targets(
    app_base: Path,
    *,
    current_pid: int,
    version: str,
    started_at: float,
    target_pids: list[int] | None = None,
    target_records: list[str] | None = None,
    mode: str | None = None,
    is_frozen: bool | None = None,
) -> dict[str, Any]:
    snapshot = collect_process_runtime(
        app_base,
        current_pid=current_pid,
        version=version,
        started_at=started_at,
        mode=mode,
        is_frozen=is_frozen,
    )
    allowed_by_pid = {
        item["pid"]: item
        for item in snapshot["conflicts"]
        if item.get("cleanup_allowed") and isinstance(item.get("pid"), int)
    }
    allowed_by_record = {
        item["record_id"]: item
        for item in snapshot["conflicts"]
        if item.get("cleanup_allowed") and item.get("record_id")
    }
    results: list[dict[str, Any]] = []
    handled_records: set[str] = set()
    handled_pids: set[int] = set()

    for record_id in target_records or []:
        if record_id in handled_records:
            continue
        handled_records.add(record_id)
        conflict = allowed_by_record.get(record_id)
        if not conflict:
            results.append(
                {
                    "pid": None,
                    "record_id": record_id,
                    "action": "skip",
                    "status": "skipped",
                    "error": "record is not eligible for cleanup",
                }
            )
            continue
        if conflict["type"] == "stale_record":
            remove_run_record(conflict.get("file_path"))
            results.append(
                {
                    "pid": conflict.get("pid"),
                    "record_id": record_id,
                    "action": "remove_record",
                    "status": "cleaned",
                }
            )
            continue

        pid = conflict.get("pid")
        if not isinstance(pid, int):
            results.append(
                {
                    "pid": None,
                    "record_id": record_id,
                    "action": "skip",
                    "status": "skipped",
                    "error": "record does not map to a cleanup pid",
                }
            )
            continue
        if pid == current_pid:
            results.append(
                {
                    "pid": pid,
                    "record_id": record_id,
                    "action": "skip",
                    "status": "skipped",
                    "error": "refusing to cleanup current server pid",
                }
            )
            continue

        handled_pids.add(pid)
        status, error = _terminate_process(pid)
        if status == "cleaned":
            remove_run_record(conflict.get("file_path"))
        results.append(
            {
                "pid": pid,
                "record_id": record_id,
                "action": "terminate_then_kill",
                "status": status,
                "error": error,
            }
        )

    for pid in target_pids or []:
        if pid in handled_pids:
            continue
        handled_pids.add(pid)
        if pid == current_pid:
            results.append(
                {
                    "pid": pid,
                    "action": "skip",
                    "status": "skipped",
                    "error": "refusing to cleanup current server pid",
                }
            )
            continue
        conflict = allowed_by_pid.get(pid)
        if not conflict:
            results.append(
                {
                    "pid": pid,
                    "action": "skip",
                    "status": "skipped",
                    "error": "pid is not eligible for cleanup",
                }
            )
            continue

        if conflict["type"] == "stale_record":
            remove_run_record(conflict.get("file_path"))
            results.append(
                {
                    "pid": pid,
                    "record_id": conflict.get("record_id"),
                    "action": "remove_record",
                    "status": "cleaned",
                }
            )
            continue

        status, error = _terminate_process(pid)
        if status == "cleaned" and conflict.get("file_path"):
            remove_run_record(conflict["file_path"])
        results.append(
            {
                "pid": pid,
                "record_id": conflict.get("record_id"),
                "action": "terminate_then_kill",
                "status": status,
                "error": error,
            }
        )

    remaining = collect_process_runtime(
        app_base,
        current_pid=current_pid,
        version=version,
        started_at=started_at,
        mode=mode,
        is_frozen=is_frozen,
    )
    return {
        "results": results,
        "remaining_conflicts": remaining["conflicts"],
    }
