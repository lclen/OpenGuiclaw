"""
core/tasks.py — Built-in scheduled system tasks.

Extracted from server.py lifespan to keep server.py focused on
HTTP wiring only.  All functions are async and receive a push_fn
callable so they can broadcast events to SSE subscribers.
"""
import asyncio
import glob
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from core.automation_context import get_automation_source_context
from core.im_selfcheck_subscriptions import list_active_selfcheck_subscriptions, record_selfcheck_delivery_status
from core.im_bots import make_im_session_id, parse_im_session_id
from core.process_runtime import cleanup_process_runtime_targets, detect_runtime_mode
from core.runtime_diagnostics import collect_runtime_selfcheck_snapshot
from core.session import Session
from core.state import app_state, _APP_BASE, logger
from core.workspace_manager import get_workspace_manager


# ── Session mirror helpers ────────────────────────────────────────────────────

def _workspace_session_paths(session_id: str) -> list[Path]:
    """Return workspace session files that mirror the given global session id."""
    if not session_id:
        return []
    workspaces_dir = _APP_BASE / "data" / "workspaces"
    if not workspaces_dir.exists():
        return []
    return sorted(workspaces_dir.glob(f"*/sessions/{session_id}.json"))


def _workspace_ids_for_session(session_id: str) -> list[str]:
    ids: list[str] = []
    for path in _workspace_session_paths(session_id):
        workspace_id = path.parent.parent.name
        if workspace_id and workspace_id not in ids:
            ids.append(workspace_id)
    return ids


def _sync_current_session_to_workspace_mirrors(agent) -> list[str]:
    """
    Mirror the current global session JSON into any workspace session files that
    share the same session_id, so background scheduler updates appear in the
    workspace-scoped chat storage used by the shell.
    """
    session = getattr(agent, "sessions", None)
    current = getattr(session, "current", None)
    if not current or not getattr(current, "session_id", None):
        return []

    session_dict = current.to_dict() if hasattr(current, "to_dict") else None
    if not session_dict:
        return []

    workspace_ids: list[str] = []
    for path in _workspace_session_paths(current.session_id):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(session_dict, f, ensure_ascii=False, indent=2)
            workspace_id = path.parent.parent.name
            if workspace_id and workspace_id not in workspace_ids:
                workspace_ids.append(workspace_id)
        except Exception as e:
            logger.warning(f"Failed to sync workspace session mirror {path}: {e}")
    return workspace_ids


def _push_chat_event(
    push_fn: Callable,
    agent,
    role: str,
    content: str,
    workspace_ids: Optional[list[str]] = None,
    session_id: Optional[str] = None,
) -> None:
    if not session_id and agent and getattr(agent, "sessions", None) and getattr(agent.sessions, "current", None):
        session_id = getattr(agent.sessions.current, "session_id", None)

    payload = {
        "type": "chat_event",
        "role": role,
        "content": content,
    }
    if session_id:
        payload["session_id"] = session_id
    resolved_workspace_ids = workspace_ids if workspace_ids is not None else _workspace_ids_for_session(session_id or "")
    if resolved_workspace_ids:
        payload["workspace_ids"] = resolved_workspace_ids
    push_fn(payload)


def _resolve_task_workspace(task) -> tuple[str | None, str | None]:
    try:
        wm = get_workspace_manager()
        workspace_id = getattr(task, "target_workspace_id", None)
        if workspace_id:
            try:
                info = wm.get_workspace(workspace_id)
            except Exception:
                info = wm.get_default_workspace(create_if_missing=True)
        else:
            info = wm.get_default_workspace(create_if_missing=True)
        return info.id, info.name
    except Exception as e:
        logger.warning(f"Failed to resolve task workspace: {e}")
        return None, None


def _resolve_workspace_info(workspace_id: str | None) -> tuple[str | None, str | None]:
    try:
        wm = get_workspace_manager()
        if workspace_id:
            try:
                info = wm.get_workspace(workspace_id)
            except Exception:
                info = wm.get_default_workspace(create_if_missing=True)
        else:
            info = wm.get_default_workspace(create_if_missing=True)
        return info.id, info.name
    except Exception as e:
        logger.warning(f"Failed to resolve workspace info: {e}")
        return None, None


def _global_session_path(session_id: str) -> Path:
    return _APP_BASE / "data" / "sessions" / f"{session_id}.json"


def _load_named_session(session_id: str) -> Session:
    path = _global_session_path(session_id)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return Session.from_dict(json.load(f))
        except Exception as e:
            logger.warning(f"Failed to load session {session_id}: {e}")
    return Session(session_id)


def _save_named_session(session: Session) -> None:
    path = _global_session_path(session.session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)


def _append_named_session_message(session_id: str, role: str, content: str, **kwargs) -> None:
    session = _load_named_session(session_id)
    session.add_message(role, content, **kwargs)
    _save_named_session(session)


def _parse_im_target_session(session_id: str) -> tuple[str | None, str | None]:
    parsed = parse_im_session_id(session_id)
    if not parsed:
        return None, None
    return parsed["channel_name"], parsed["chat_id"]


def _fanout_im_delivery(
    session_id: str,
    role: str,
    content: str,
    *,
    channel: str | None = None,
    chat_id: str | None = None,
) -> None:
    if role not in {"assistant", "system"}:
        return
    channel = channel or None
    chat_id = chat_id or None
    if not channel or not chat_id:
        channel, chat_id = _parse_im_target_session(session_id)
    if not channel or not chat_id:
        return

    gateway = app_state.get("gateway")
    adapter = gateway.adapters.get(channel) if gateway else None
    if not adapter or not getattr(adapter, "_running", False):
        return

    async def _send() -> None:
        try:
            await adapter.send_text(chat_id, content)
        except Exception as e:
            logger.warning(f"Failed to send scheduler result to IM {session_id}: {e}")

    try:
        asyncio.get_running_loop().create_task(_send())
    except RuntimeError:
        logger.warning(f"No running loop available to fanout IM delivery for {session_id}")


def _append_workspace_chat_message(
    workspace_id: str,
    session_id: str,
    role: str,
    content: str,
    **kwargs,
) -> None:
    wm = get_workspace_manager()
    session_data = wm._read_session_json(workspace_id, session_id)
    session = Session.from_dict(session_data)
    session.add_message(role, content, **kwargs)
    payload = session.to_dict()
    payload["title"] = session_data.get("title", "自动化收件箱")
    payload["system_thread_type"] = session_data.get("system_thread_type", "automation_inbox")
    payload["pinned"] = session_data.get("pinned", True)
    wm._write_session_json(workspace_id, payload)


def _deliver_event_to_workspace(workspace_id: str | None, role: str, content: str) -> tuple[list[str], str | None]:
    workspace_id, _workspace_name = _resolve_workspace_info(workspace_id)
    if not workspace_id:
        return [], None

    try:
        wm = get_workspace_manager()
        session_id = wm.ensure_system_session(
            workspace_id,
            thread_type="automation_inbox",
            title="自动化收件箱",
            pinned=True,
        )
        _append_workspace_chat_message(workspace_id, session_id, role, content)
        return [workspace_id], session_id
    except Exception as e:
        logger.warning(f"Failed to deliver scheduler message to workspace inbox: {e}")
        return [workspace_id], None


def _deliver_event_to_desktop_session(session_id: str, role: str, content: str) -> tuple[list[str], str | None]:
    try:
        _append_named_session_message(session_id, role, content)
        return _workspace_ids_for_session(session_id), session_id
    except Exception as e:
        logger.warning(f"Failed to deliver scheduler message to desktop session {session_id}: {e}")
        return [], None


def _deliver_event_to_im_session(
    session_id: str | None,
    role: str,
    content: str,
    *,
    channel: str | None = None,
    chat_id: str | None = None,
) -> tuple[list[str], str | None]:
    resolved_session_id = session_id
    if not resolved_session_id and channel and chat_id:
        resolved_session_id = make_im_session_id(channel, chat_id)
    if not resolved_session_id:
        return [], None

    resolved_channel = channel
    resolved_chat_id = chat_id
    if not resolved_channel or not resolved_chat_id:
        resolved_channel, resolved_chat_id = _parse_im_target_session(resolved_session_id)

    try:
        _append_named_session_message(resolved_session_id, role, content)
        _fanout_im_delivery(
            resolved_session_id,
            role,
            content,
            channel=resolved_channel,
            chat_id=resolved_chat_id,
        )
        return [], resolved_session_id
    except Exception as e:
        logger.warning(f"Failed to deliver scheduler message to IM session {resolved_session_id}: {e}")
        return [], None


def _resolve_task_delivery_target(task) -> list[dict[str, str | None]]:
    if hasattr(task, "normalize_target"):
        task.normalize_target()
    if hasattr(task, "get_delivery_targets"):
        targets = []
        for item in task.get_delivery_targets():
            if not isinstance(item, dict):
                continue
            targets.append(
                {
                    "target_kind": item.get("kind"),
                    "target_workspace_id": item.get("workspace_id"),
                    "target_session_id": item.get("session_id"),
                    "target_channel": item.get("channel"),
                    "target_chat_id": item.get("chat_id"),
                }
            )
        if targets:
            return targets

    target_kind = getattr(task, "target_kind", None)
    target_workspace_id = getattr(task, "target_workspace_id", None)
    target_session_id = getattr(task, "target_session_id", None)
    target_channel = getattr(task, "target_channel", None)
    target_chat_id = getattr(task, "target_chat_id", None)

    if not target_kind:
        if target_session_id:
            channel, chat_id = _parse_im_target_session(target_session_id)
            if channel and chat_id:
                target_kind = "im_session"
                target_channel = target_channel or channel
                target_chat_id = target_chat_id or chat_id
            else:
                target_kind = "desktop_session"
        else:
            target_kind = "workspace_inbox"

    if target_kind == "im_session":
        if not target_session_id and target_channel and target_chat_id:
            target_session_id = make_im_session_id(target_channel, target_chat_id)
        if (not target_channel or not target_chat_id) and target_session_id:
            target_channel, target_chat_id = _parse_im_target_session(target_session_id)
        if not target_session_id and not (target_channel and target_chat_id):
            target_kind = "workspace_inbox"

    if target_kind == "desktop_session" and not target_session_id:
        target_kind = "workspace_inbox"

    return [{
        "target_kind": target_kind,
        "target_workspace_id": target_workspace_id,
        "target_session_id": target_session_id,
        "target_channel": target_channel,
        "target_chat_id": target_chat_id,
    }]


def deliver_automation_event(
    role: str,
    content: str,
    *,
    target_kind: str | None = None,
    target_workspace_id: str | None = None,
    target_session_id: str | None = None,
    target_channel: str | None = None,
    target_chat_id: str | None = None,
) -> tuple[list[str], str | None]:
    resolved_kind = target_kind
    resolved_workspace_id = target_workspace_id
    resolved_session_id = target_session_id
    resolved_channel = target_channel
    resolved_chat_id = target_chat_id

    if not resolved_kind:
        source = get_automation_source_context()
        if source and source.source_kind == "im" and source.source_session_id:
            resolved_kind = "im_session"
            resolved_session_id = source.source_session_id
            resolved_channel = source.source_channel
            resolved_chat_id = source.source_chat_id
        elif source and source.source_kind == "desktop" and source.source_session_id:
            resolved_kind = "desktop_session"
            resolved_session_id = source.source_session_id

    if resolved_kind == "im_session":
        return _deliver_event_to_im_session(
            resolved_session_id,
            role,
            content,
            channel=resolved_channel,
            chat_id=resolved_chat_id,
        )
    if resolved_kind == "desktop_session" and resolved_session_id:
        return _deliver_event_to_desktop_session(resolved_session_id, role, content)
    return _deliver_event_to_workspace(resolved_workspace_id, role, content)


def _deliver_task_event(task, role: str, content: str) -> tuple[list[str], str | None, list[str]]:
    targets = _resolve_task_delivery_target(task)
    workspace_ids: list[str] = []
    session_id: str | None = None
    session_ids: list[str] = []
    for target in targets:
        target_workspace_ids, target_session_id = deliver_automation_event(
            role,
            content,
            target_kind=target["target_kind"],
            target_workspace_id=target["target_workspace_id"],
            target_session_id=target["target_session_id"],
            target_channel=target["target_channel"],
            target_chat_id=target["target_chat_id"],
        )
        for workspace_id in target_workspace_ids:
            if workspace_id not in workspace_ids:
                workspace_ids.append(workspace_id)
        if target_session_id and target_session_id not in session_ids:
            session_ids.append(target_session_id)
        if session_id is None and target_session_id:
            session_id = target_session_id
    return workspace_ids, session_id, session_ids


def _make_scheduler_push(task, agent, push_fn: Callable) -> Callable[[dict], None]:
    def _wrapped(event: dict) -> None:
        payload = dict(event)
        if payload.get("type") == "chat_event":
            workspace_ids, session_id, session_ids = _deliver_task_event(
                task,
                payload.get("role", "assistant"),
                payload.get("content", ""),
            )
            if session_id:
                payload["session_id"] = session_id
            if session_ids:
                payload["session_ids"] = session_ids
            if workspace_ids:
                payload["workspace_ids"] = workspace_ids
        push_fn(payload)

    return _wrapped


# ── Dispatcher ────────────────────────────────────────────────────────────────

async def execute_system_task(task, push_fn: Callable) -> tuple[bool, str]:
    """Route a system task to its handler by action name."""
    action = task.action or ""
    if action == "system:daily_selfcheck":
        return await _system_daily_selfcheck(push_fn, task)
    if action == "system:memory_consolidate":
        return await _system_memory_consolidate(push_fn, task)
    if action == "system:memory_audit":
        return await _system_memory_audit(push_fn)
    if action == "system:daily_evolution":
        return await _system_daily_evolution(push_fn, task)
    return False, f"Unknown system action: {action}"


# ── Daily self-check ──────────────────────────────────────────────────────────

_SELFCHECK_REQUIRED_DIRS = [
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
]
_STATUS_EMOJI = {"healthy": "✅", "degraded": "⚠️", "unhealthy": "❌", "unknown": "❔"}


def _scan_log_error_summary() -> dict[str, int]:
    log_errors: dict[str, int] = {}
    candidates = list((_APP_BASE).glob("*.log")) + list((_APP_BASE / "logs").glob("*.log"))
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if " ERROR " not in line and " CRITICAL " not in line:
                        continue
                    parts = line.split(" - ")
                    module = parts[1].strip() if len(parts) > 2 else "unknown"
                    log_errors[module] = log_errors.get(module, 0) + 1
        except Exception:
            continue
    return log_errors


def _summarize_scheduler_health() -> dict[str, int]:
    scheduler = app_state.get("task_scheduler")
    if not scheduler:
        return {"total": 0, "enabled": 0, "failed": 0}
    tasks = scheduler.list_tasks()
    return {
        "total": len(tasks),
        "enabled": sum(1 for task in tasks if task.enabled),
        "failed": sum(1 for task in tasks if task.fail_count > 0),
    }


def _count_memory_entries() -> int:
    memory_file = _APP_BASE / "data" / "memory.jsonl"
    if not memory_file.exists():
        return 0
    try:
        with open(memory_file, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0


def _fix_record_to_dict(record: Any) -> dict[str, Any]:
    if hasattr(record, "model_dump"):
        return record.model_dump()
    if hasattr(record, "dict"):
        return record.dict()
    return {
        "component": getattr(record, "component", "unknown"),
        "error_pattern": getattr(record, "error_pattern", ""),
        "can_fix": bool(getattr(record, "can_fix", False)),
        "fix_action": getattr(record, "fix_action", ""),
        "success": bool(getattr(record, "success", False)),
        "verification_result": getattr(record, "verification_result", ""),
    }


def _merge_overall_status(statuses: list[str]) -> str:
    normalized = [str(item or "") for item in statuses if item]
    if any(item == "unhealthy" for item in normalized):
        return "unhealthy"
    if any(item == "degraded" for item in normalized):
        return "degraded"
    if any(item == "healthy" for item in normalized):
        return "healthy"
    return "unknown"


def _render_status(status: str, label: str) -> str:
    return f"{_STATUS_EMOJI.get(status, '❔')} {label}"


def _write_selfcheck_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _persist_selfcheck_artifacts(result: dict[str, Any], report: str) -> list[str]:
    reports_dir = _APP_BASE / "data" / "selfcheck"
    failures: list[str] = []
    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("Failed to prepare selfcheck report directory %s: %s", reports_dir, exc)
        return [f"{reports_dir}: {exc}"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    latest_json = reports_dir / "latest.json"
    latest_md = reports_dir / "latest.md"
    dated_json = reports_dir / f"selfcheck_{timestamp}.json"
    dated_md = reports_dir / f"selfcheck_{timestamp}.md"
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    for path, content in (
        (latest_json, payload),
        (latest_md, report),
        (dated_json, payload),
        (dated_md, report),
    ):
        try:
            _write_selfcheck_file(path, content)
        except Exception as exc:
            logger.warning("Failed to write selfcheck artifact %s: %s", path, exc)
            failures.append(f"{path}: {exc}")
    return failures


def _build_selfcheck_runtime_lines(result: dict[str, Any]) -> list[str]:
    endpoints = result["endpoints"]
    network_matrix = result["network_matrix"]
    im_channels = result["im_channels"]
    process_runtime = result["runtime"]["process_runtime"]
    endpoint_label = f"{len(endpoints['results'])} 个目标"
    im_label = f"{len(im_channels['results'])} 个通道"

    lines = ["\n### 运行时探测"]
    lines.append(
        f"- 服务: {_render_status('healthy', '在线')} · 重启模式 `{result['environment']['restart']['mode']}`"
    )
    lines.append(f"- 端点: {_render_status(endpoints['status'], endpoint_label)}")
    lines.append(f"- 网络矩阵: {_render_status(network_matrix['status'], network_matrix['summary'])}")
    lines.append(f"- IM 通道: {_render_status(im_channels['status'], im_label)}")

    conflicts = process_runtime.get("conflicts", [])
    lines.append("\n### 进程残留 / 冲突")
    if conflicts:
        for item in conflicts[:6]:
            pid_text = f"pid={item.get('pid')}" if item.get("pid") is not None else "pid=-"
            lines.append(f"- `{item.get('type')}` {pid_text}: {item.get('summary')}")
    else:
        lines.append("- ✅ 未发现残留进程或 stale run record")

    if network_matrix["results"]:
        lines.append("\n### 网络矩阵")
        for probe in network_matrix["results"]:
            label = probe.get("probe_label") or probe.get("probe_mode")
            detail = f"{probe['latency_ms']}ms" if probe.get("latency_ms") is not None else "未返回延迟"
            if probe.get("error"):
                detail = f"{detail} · {probe['error']}"
            lines.append(f"- {_render_status(probe['status'], str(label))}: {detail}")

    return lines


def _build_selfcheck_endpoint_lines(result: dict[str, Any]) -> list[str]:
    endpoints = result["endpoints"]
    im_channels = result["im_channels"]
    lines: list[str] = []
    if endpoints["results"]:
        lines.append("\n### LLM Endpoints")
        for endpoint in endpoints["results"]:
            detail = f"{endpoint['latency_ms']}ms" if endpoint.get("latency_ms") is not None else "未返回延迟"
            if endpoint.get("error"):
                detail = f"{detail} · {endpoint['error']}"
            lines.append(f"- {_render_status(endpoint['status'], endpoint['label'] or endpoint['name'])}: {detail}")
    else:
        lines.append("\n### LLM Endpoints")
        lines.append("- ❔ 当前未配置可测活端点")

    lines.append("\n### IM 通道")
    if im_channels["results"]:
        for channel in im_channels["results"]:
            detail = channel.get("summary") or "无摘要"
            if channel.get("last_error"):
                detail = f"{detail} · {channel['last_error']}"
            lines.append(f"- {_render_status(channel['status'], channel['display_name'])}: {detail}")
    else:
        lines.append("- ❔ 当前未配置 IM 通道")
    return lines


def _build_selfcheck_fix_lines(result: dict[str, Any]) -> list[str]:
    logs = result["logs"]
    fixes = result["fixes"]
    lines = ["\n### 日志与轻修复"]
    lines.append(f"- 日志错误模块: {len(logs['by_module'])} 个 · 错误行 {logs['total_errors']} 条")
    if logs["by_module"]:
        for module, count in sorted(logs["by_module"].items(), key=lambda item: -item[1])[:5]:
            lines.append(f"  - `{module}`: {count} 次")
    lines.append(
        f"- AI 分析: core={fixes['core_error_count']} · capability={fixes['tool_error_count']} · 自动修复成功={fixes['fixed_count']}"
    )
    if fixes["actions"]:
        for item in fixes["actions"]:
            prefix = "✅" if item.get("success") else ("⚠️" if item.get("can_fix") else "🔴")
            lines.append(f"  - {prefix} `{item.get('component')}`: {item.get('error_pattern')}")
            if item.get("fix_action"):
                lines.append(f"    👉 {item['fix_action']}")
            if item.get("verification_result"):
                lines.append(f"    🔍 {item['verification_result']}")
    if fixes["stale_record_cleanup"]:
        lines.append("\n### 自动清理")
        for cleanup in fixes["stale_record_cleanup"]:
            target = cleanup.get("record_id") or cleanup.get("pid")
            lines.append(f"- `{target}`: {cleanup.get('status')} ({cleanup.get('action')})")
    if fixes.get("artifact_write_failures"):
        lines.append("\n### 报告落盘")
        for item in fixes["artifact_write_failures"]:
            lines.append(f"- ⚠️ {item}")
    return lines


def _build_selfcheck_report(result: dict[str, Any]) -> str:
    generated_at = result["generated_at"]
    service = result["runtime"]["service"]
    scheduler = result["scheduler"]

    lines = [f"## 🔍 系统自检报告 — {generated_at}"]
    lines.append(f"\n**总体状态**: {_render_status(result['overall_status'], result['overall_summary'])}")
    lines.append(
        f"**服务运行**: PID `{service['pid']}` · 版本 `{service['version']}` · 模式 `{service['restart_mode']}` · 运行 {service['uptime_seconds']}s"
    )
    lines.append(
        f"**计划任务**: 共 {scheduler['total']} 个，启用 {scheduler['enabled']} 个，失败 {scheduler['failed']} 个"
    )
    lines.append(
        f"**数据概况**: 会话 {result['environment']['session_count']} 个 · 记忆 {result['environment']['memory_count']} 条"
    )
    lines.extend(_build_selfcheck_runtime_lines(result))
    lines.extend(_build_selfcheck_endpoint_lines(result))
    lines.extend(_build_selfcheck_fix_lines(result))
    return "\n".join(lines)


def _collect_selfcheck_status_inputs(
    *,
    dir_failures: list[str],
    process_conflicts: list[dict[str, Any]],
    scheduler_summary: dict[str, int],
    logs: dict[str, Any],
    core_errs: int,
    fix_records: list[dict[str, Any]],
    runtime_snapshot: dict[str, Any],
) -> list[str]:
    status_inputs: list[str] = []
    if dir_failures:
        status_inputs.append("unhealthy")
    if any(item.get("type") in {"running_conflict", "orphan_process"} for item in process_conflicts):
        status_inputs.append("unhealthy")
    if scheduler_summary["failed"] > 0:
        status_inputs.append("degraded")
    if logs["total_errors"] > 0 or core_errs > 0:
        status_inputs.append("degraded")
    if any(item.get("can_fix") and not item.get("success") for item in fix_records):
        status_inputs.append("degraded")
    if runtime_snapshot["endpoints"]["status"] in {"degraded", "unhealthy"}:
        status_inputs.append(runtime_snapshot["endpoints"]["status"])
    if runtime_snapshot["network_matrix"]["status"] in {"degraded", "unhealthy"}:
        status_inputs.append(runtime_snapshot["network_matrix"]["status"])
    if runtime_snapshot["im_channels"]["status"] in {"degraded", "unhealthy"}:
        status_inputs.append("degraded")
    return status_inputs


def _build_selfcheck_im_summary(result: dict[str, Any]) -> str:
    lines = [
        f"🔍 系统自检摘要 {result['generated_at']}",
        f"- 总体状态: {_render_status(result['overall_status'], result['overall_summary'])}",
        f"- 服务: PID {result['runtime']['service']['pid']} / {result['runtime']['service']['restart_mode']}",
        f"- 端点: {result['endpoints']['status']} ({len(result['endpoints']['results'])} 个)",
        f"- 网络矩阵: {result['network_matrix']['status']} / {result['network_matrix']['summary']}",
        f"- IM 通道: {result['im_channels']['status']} ({len(result['im_channels']['results'])} 个)",
        f"- 日志错误: {result['logs']['total_errors']} 条 / 模块 {len(result['logs']['by_module'])} 个",
    ]
    conflicts = result["runtime"]["process_runtime"].get("conflicts", [])
    if conflicts:
        lines.append(f"- 进程冲突: {len(conflicts)} 项，建议在 Diagnostics 中人工处理")
    if result["fixes"]["stale_record_cleanup"]:
        lines.append(f"- 已自动清理 stale record: {len(result['fixes']['stale_record_cleanup'])} 项")
    advice = _build_selfcheck_im_advice(result)
    if advice:
        lines.append("")
        lines.append("建议：")
        lines.extend(f"- {item}" for item in advice)
    return "\n".join(lines)


def _build_selfcheck_im_advice(result: dict[str, Any]) -> list[str]:
    advice: list[str] = []
    process_runtime = result["runtime"]["process_runtime"]
    endpoint_status = str(result["endpoints"]["status"])
    network_status = str(result["network_matrix"]["status"])
    im_status = str(result["im_channels"]["status"])

    if process_runtime.get("conflicts"):
        advice.append("请打开 Diagnostics 查看冲突进程或残留运行记录")
    if endpoint_status == "unhealthy":
        advice.append("主模型端点异常，请检查 API Key、Base URL 和模型名称")
    elif endpoint_status == "unknown":
        advice.append("当前未配置可测活端点，可在 Diagnostics 中补充并手动 Check")
    if network_status == "unhealthy":
        advice.append("网络矩阵异常，请检查代理、IPv4/IPv6 路由和外网连通性")
    if im_status == "unhealthy":
        advice.append("IM 通道离线，请检查对应 Bot 配置并确认重启后已上线")
    if result["logs"]["total_errors"] > 0:
        advice.append("存在日志错误，请优先查看最新错误模块并结合 Diagnostics 排查")
    return advice


def _deliver_selfcheck_subscription_fanout(im_summary: str) -> None:
    subscriptions = list_active_selfcheck_subscriptions()
    delivered: set[str] = set()

    for item in subscriptions:
        session_id = str(item.get("session_id") or "")
        channel_name = str(item.get("channel_name") or "")
        chat_id = str(item.get("chat_id") or "")
        if not session_id or not channel_name or not chat_id or session_id in delivered:
            continue
        delivered.add(session_id)

        gateway = app_state.get("gateway")
        adapter = gateway.adapters.get(channel_name) if gateway else None
        if not adapter or not getattr(adapter, "_running", False):
            logger.warning("[SelfCheck] Skip subscribed IM selfcheck delivery for offline channel=%s chat=%s", channel_name, chat_id)
            record_selfcheck_delivery_status(session_id, status="skipped", error="channel offline")
            continue

        try:
            deliver_automation_event(
                "assistant",
                im_summary,
                target_kind="im_session",
                target_session_id=session_id,
                target_channel=channel_name,
                target_chat_id=chat_id,
            )
            record_selfcheck_delivery_status(session_id, status="sent")
        except Exception as exc:
            logger.warning(
                "[SelfCheck] Failed to fanout subscribed IM selfcheck channel=%s chat=%s: %s",
                channel_name,
                chat_id,
                exc,
            )
            record_selfcheck_delivery_status(session_id, status="failed", error=str(exc))


def _deliver_selfcheck_reports(task: Optional[Any], report: str, im_summary: str) -> None:
    targets = _resolve_task_delivery_target(task) if task else []
    if not targets:
        deliver_automation_event("assistant", report)
        _deliver_selfcheck_subscription_fanout(im_summary)
        return

    non_im_targets = [item for item in targets if item.get("target_kind") != "im_session"]
    im_targets = [item for item in targets if item.get("target_kind") == "im_session"]

    for target in non_im_targets:
        deliver_automation_event(
            "assistant",
            report,
            target_kind=target["target_kind"],
            target_workspace_id=target["target_workspace_id"],
            target_session_id=target["target_session_id"],
            target_channel=target["target_channel"],
            target_chat_id=target["target_chat_id"],
        )

    _deliver_selfcheck_subscription_fanout(im_summary)

    if im_targets and not non_im_targets:
        deliver_automation_event("assistant", report, target_kind="workspace_inbox")

    for target in im_targets:
        deliver_automation_event(
            "assistant",
            im_summary,
            target_kind=target["target_kind"],
            target_workspace_id=target["target_workspace_id"],
            target_session_id=target["target_session_id"],
            target_channel=target["target_channel"],
            target_chat_id=target["target_chat_id"],
        )


async def _system_daily_selfcheck(push_fn: Callable, task: Optional[Any] = None) -> tuple[bool, str]:
    """Daily automated selfcheck with runtime probes, light repair, and summary delivery."""
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    created_dirs: list[str] = []
    dir_failures: list[str] = []
    for rel_path in _SELFCHECK_REQUIRED_DIRS:
        target = _APP_BASE / rel_path
        if target.exists():
            continue
        try:
            target.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(target))
        except Exception as exc:
            dir_failures.append(f"{target}: {exc}")

    runtime_snapshot = await collect_runtime_selfcheck_snapshot(
        _APP_BASE,
        current_pid=os.getpid(),
        version=str(app_state.get("server_version") or "unknown"),
        started_at=float(app_state.get("server_started_at") or datetime.now().timestamp()),
        mode=detect_runtime_mode(),
        is_frozen=getattr(sys, "frozen", False),
    )

    stale_records = [
        item.get("record_id")
        for item in runtime_snapshot["runtime"]["process_runtime"].get("conflicts", [])
        if item.get("type") == "stale_record" and item.get("record_id")
    ]
    stale_cleanup_results: list[dict[str, Any]] = []
    if stale_records:
        cleanup_result = cleanup_process_runtime_targets(
            _APP_BASE,
            current_pid=os.getpid(),
            version=str(app_state.get("server_version") or "unknown"),
            started_at=float(app_state.get("server_started_at") or datetime.now().timestamp()),
            target_records=stale_records,
            target_pids=[],
            mode=detect_runtime_mode(),
            is_frozen=getattr(sys, "frozen", False),
        )
        stale_cleanup_results = cleanup_result.get("results", [])
        runtime_snapshot = await collect_runtime_selfcheck_snapshot(
            _APP_BASE,
            current_pid=os.getpid(),
            version=str(app_state.get("server_version") or "unknown"),
            started_at=float(app_state.get("server_started_at") or datetime.now().timestamp()),
            mode=detect_runtime_mode(),
            is_frozen=getattr(sys, "frozen", False),
        )

    log_errors = _scan_log_error_summary()
    ag = app_state.get("agent")
    fix_records: list[dict[str, Any]] = []
    core_errs = 0
    tool_errs = 0
    if log_errors and ag:
        try:
            from core.self_check import SelfChecker

            checker = SelfChecker(agent=ag)
            core_errs, tool_errs, raw_records = await checker.analyze_and_fix(push_fn)
            fix_records = [_fix_record_to_dict(item) for item in raw_records]
        except Exception as exc:
            logger.error(f"AI self-check failed: {exc}")

    scheduler_summary = _summarize_scheduler_health()
    environment = {
        "session_count": len(glob.glob(str(_APP_BASE / "data" / "sessions" / "*.json"))),
        "memory_count": _count_memory_entries(),
        "directories_created": created_dirs,
        "directory_failures": dir_failures,
        **runtime_snapshot["environment"],
    }
    fixes = {
        "core_error_count": core_errs,
        "tool_error_count": tool_errs,
        "fixed_count": sum(1 for item in fix_records if item.get("success")),
        "actions": fix_records,
        "stale_record_cleanup": stale_cleanup_results,
    }
    logs = {
        "total_errors": sum(log_errors.values()),
        "by_module": log_errors,
    }

    process_conflicts = runtime_snapshot["runtime"]["process_runtime"].get("conflicts", [])
    status_inputs = _collect_selfcheck_status_inputs(
        dir_failures=dir_failures,
        process_conflicts=process_conflicts,
        scheduler_summary=scheduler_summary,
        logs=logs,
        core_errs=core_errs,
        fix_records=fix_records,
        runtime_snapshot=runtime_snapshot,
    )
    overall_status = _merge_overall_status(status_inputs) if status_inputs else "healthy"

    if overall_status == "healthy":
        overall_summary = "运行时与环境检查均正常"
    elif overall_status == "degraded":
        overall_summary = "存在可恢复问题，已完成轻修复并保留人工处理建议"
    else:
        overall_summary = "存在运行时风险，请优先查看 Diagnostics 手动排障"

    result = {
        "generated_at": generated_at,
        "environment": environment,
        "runtime": runtime_snapshot["runtime"],
        "network_matrix": runtime_snapshot["network_matrix"],
        "endpoints": runtime_snapshot["endpoints"],
        "im_channels": runtime_snapshot["im_channels"],
        "scheduler": scheduler_summary,
        "logs": logs,
        "fixes": fixes,
        "overall_status": overall_status,
        "overall_summary": overall_summary,
    }
    report = _build_selfcheck_report(result)
    im_summary = _build_selfcheck_im_summary(result)
    artifact_write_failures = _persist_selfcheck_artifacts(result, report)
    if artifact_write_failures:
        result["fixes"]["artifact_write_failures"] = artifact_write_failures
        report = _build_selfcheck_report(result)
        im_summary = _build_selfcheck_im_summary(result)
    _deliver_selfcheck_reports(task, report, im_summary)
    push_fn({"type": "chat_event", "role": "assistant", "content": im_summary})

    logger.info("System selfcheck completed: %s", overall_summary)
    return True, f"{_STATUS_EMOJI.get(overall_status, '❔')} {overall_summary}"


# ── Memory consolidation ──────────────────────────────────────────────────────

async def _system_memory_consolidate(push_fn: Callable, task: Optional[Any] = None) -> tuple[bool, str]:
    """
    Scan recent sessions and extract new long-term memories via MemoryExtractor.
    Pushes a Markdown summary report to chat.
    """
    ag = app_state.get("agent")
    if not ag or not hasattr(ag, "memory_extractor") or not hasattr(ag, "memory"):
        return False, "Agent or memory subsystem not ready"

    _push_chat_event(push_fn, ag, "system", "🧠 [记忆整理] 开始扫描会话历史信息…")

    # Optimization: Use task.last_run if available to scan only new/modified sessions
    now = datetime.now()
    if task and task.last_run:
        # Buffer of 10 minutes to ensure no overlap loss
        cutoff = task.last_run - timedelta(minutes=10)
    else:
        # Initial run: scan last 7 days
        cutoff = now - timedelta(days=7)

    logger.info(f"Memory consolidate scan starting (cutoff: {cutoff})")
    # Forward-block guard:
    # only scan legacy/global sessions under data/sessions/.
    # Workspace-scoped chat files live under data/workspaces/*/sessions/ and
    # must never be included here, especially after a workspace/session has
    # been permanently deleted from the workspace tree.
    session_files = sorted(
        (_APP_BASE / "data" / "sessions").glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    current_sid = ag.sessions.current.session_id if ag.sessions.current else None
    scanned = written = skipped = 0

    for sf in session_files:
        try:
            if datetime.fromtimestamp(sf.stat().st_mtime) < cutoff:
                break
            with open(sf, "r", encoding="utf-8") as f:
                data = json.load(f)
            sid = data.get("session_id", sf.stem)
            messages = data.get("messages", [])
            if sid == current_sid or not messages:
                skipped += 1
                continue
            chat_msgs = [m for m in messages if m.get("role") in ("user", "assistant")]
            if len(chat_msgs) < 2:
                skipped += 1
                continue
            scanned += 1
            loop = asyncio.get_running_loop()
            new_items = await loop.run_in_executor(
                None, ag.memory_extractor.extract_from_conversation, chat_msgs
            )
            written += len(new_items) if new_items else 0
        except Exception as e:
            logger.warning(f"Memory consolidate: skipped {sf.name}: {e}")
            skipped += 1

    total_memories = len(ag.memory.list_all())
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    type_meta = [
        ("fact", "客观事实"), ("preference", "用户偏好"), ("rule", "规则约束"),
        ("skill", "技能模式"), ("error", "待规避错误"), ("experience", "可复用经验"),
    ]
    type_rows = "\n".join(
        f"| `{t}` | {desc} | {len(ag.memory.list_by_type(t))} |"
        for t, desc in type_meta
    )
    report = (
        f"## 🧠 记忆整理报告 — {ts}\n\n"
        f"- **扫描会话**: {scanned} 个　**跳过**: {skipped} 个　**写入新记忆**: {written} 条\n\n"
        f"| 类型 | 说明 | 当前总量 |\n|------|------|---------|\n{type_rows}\n\n"
        f"{'✅ 整理完成，记忆库已更新。' if written > 0 else '✅ 整理完成，无新增内容（已是最新）。'}"
        f"  记忆库共 **{total_memories}** 条。"
    )
    workspace_ids: list[str] = []
    if ag:
        ag.sessions.current.add_message("assistant", report)
        ag.sessions.save()
        workspace_ids = _sync_current_session_to_workspace_mirrors(ag)
    _push_chat_event(push_fn, ag, "assistant", report, workspace_ids)
    status = f"扫描 {scanned} 个会话，写入 {written} 条新记忆"
    logger.info(f"Memory consolidate completed: {status}")
    return True, status


# ── Scheduler task runner (called by TaskScheduler) ───────────────────────────

def _summarize_task_message(text: str | None, limit: int = 800) -> str:
    if not text:
        return "无可用结果。"
    text = str(text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _build_task_notification(title: str, task_name: str, body: str) -> str:
    return f"{title} {task_name}\n\n{body}".strip()

async def scheduled_task_runner(task) -> tuple[bool, str]:
    """
    Universal task runner passed to TaskScheduler as its executor.
    Handles reminder / prompt / system task types.
    """
    import concurrent.futures
    from core.state import _ctx_event_queue

    ag = app_state.get("agent")
    if not ag:
        return False, "Agent not ready"

    def _push(event: dict) -> None:
        _ctx_event_queue.put(event)

    task_push = _make_scheduler_push(task, ag, _push)

    try:
        if task.task_type.value == "system":
            task_push({
                "type": "chat_event",
                "role": "system",
                "content": _build_task_notification("🚀 [计划任务开始]", task.name, "系统任务已启动。"),
            })
            captured_messages: list[str] = []

            def _capture_push(event: dict) -> None:
                if event.get("type") != "chat_event":
                    return
                content = str(event.get("content", "")).strip()
                if content:
                    captured_messages.append(content)

            success, result = await execute_system_task(task, _capture_push)
            task_push({
                "type": "chat_event",
                "role": "assistant" if success else "system",
                "content": _build_task_notification(
                    "✅ [计划任务完成]" if success else "❌ [计划任务失败]",
                    task.name,
                    _summarize_task_message(captured_messages[-1] if captured_messages else result),
                ),
            })
            return success, result

        if task.task_type.value == "reminder":
            msg = task.reminder_message or "无提醒内容"
            task_push({"type": "chat_event", "role": "assistant", "content": f"⏰ **{task.name}**\n\n{msg}"})
            return True, "Reminder sent"

        # Default: LLM prompt task
        full_prompt = f"[计划任务: {task.name}] {task.prompt}"
        task_push({
            "type": "chat_event",
            "role": "system",
            "content": _build_task_notification("🚀 [计划任务开始]", task.name, "AI 正在处理中，请稍候。"),
        })

        def _run_chat():
            import asyncio as _asyncio
            loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(loop)
            try:
                return ag.chat(full_prompt)
            finally:
                loop.close()
                _asyncio.set_event_loop(None)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="sched") as pool:
            response = await asyncio.get_running_loop().run_in_executor(pool, _run_chat)

        task_push({
            "type": "chat_event",
            "role": "assistant",
            "content": _build_task_notification(
                "✅ [计划任务完成]",
                task.name,
                _summarize_task_message(response),
            ),
        })
        return True, response

    except Exception as e:
        logger.error(f"Scheduled task error: {e}", exc_info=True)
        task_push({
            "type": "chat_event",
            "role": "system",
            "content": _build_task_notification(
                "❌ [计划任务失败]",
                task.name,
                _summarize_task_message(str(e), limit=500),
            ),
        })
        return False, str(e)

async def _system_memory_audit(push_fn: Callable) -> tuple[bool, str]:
    """
    Perform AI-driven memory deduplication and cleanup.
    Wipes old memories and replaces them with audited/optimized entries.
    """
    ag = app_state.get("agent")
    if not ag or not hasattr(ag, "memory_extractor") or not hasattr(ag, "memory"):
        return False, "Agent or memory subsystem not ready"

    _push_chat_event(push_fn, ag, "system", "🧹 [记忆审计] 正在启动 AI 自主审查与去重…")

    try:
        loop = asyncio.get_running_loop()
        # Audit: Get optimized list from AI
        # Audit: AI natively handles actions (delete/update/merge/keep)
        old_count = len(ag.memory.list_all())
        report = await loop.run_in_executor(
            None, ag.memory_extractor.audit_memories
        )
        
        if not report:
            logger.warning("[Task] Memory audit returned empty/failed.")
            return False, "AI 审计未能完成，已中止。"

        new_count = len(ag.memory.list_all())
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        summary = (
            f"### 🧹 记忆库审计报告 — {ts}\n\n"
            f"- **审查前总数**: {old_count} 条\n"
            f"- **审查后总数**: {new_count} 条\n"
            f"- **操作统计**: 删除 {report.get('deleted', 0)} 条, 合并 {report.get('merged', 0)} 条, 更新 {report.get('updated', 0)} 条, 保留 {report.get('kept', 0)} 条\n\n"
            "✅ 记忆库已通过例行自检完成优化。"
        )
        
        if ag:
            ag.sessions.current.add_message("assistant", summary)
            ag.sessions.save()

        workspace_ids = _sync_current_session_to_workspace_mirrors(ag) if ag else []
        _push_chat_event(push_fn, ag, "assistant", summary, workspace_ids)
        return True, f"审计完成: {old_count} -> {new_count}"
        
    except Exception as e:
        logger.error(f"Memory audit error: {e}", exc_info=True)
        return False, str(e)


# ── Daily evolution ───────────────────────────────────────────────────────────

async def _system_daily_evolution(push_fn: Callable, task=None) -> tuple[bool, str]:
    """
    Run daily self-evolution: summarize yesterday's journal, extract memories,
    update persona. If task.prompt contains a date string (YYYY-MM-DD), use it
    as the target date (for catchup runs triggered by _startup_evolution).
    """
    ag = app_state.get("agent")
    if not ag:
        return False, "Agent not ready"

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Check if a specific date was passed via task.prompt (catchup scenario)
    import re as _re
    task_prompt = getattr(task, "prompt", "") or ""
    if _re.match(r"^\d{4}-\d{2}-\d{2}$", task_prompt.strip()):
        target_date = task_prompt.strip()
        # Clear the prompt so next scheduled run uses normal logic
        if task:
            task.prompt = ""
    elif ag.evolution.is_evolution_done(yesterday):
        target_date = today
    else:
        target_date = yesterday

    _push_chat_event(push_fn, ag, "system", f"🌱 [自我进化] 开始处理 {target_date} 的日志…")

    try:
        loop = asyncio.get_running_loop()

        # Step 1: summarize conversations for the day
        await loop.run_in_executor(None, ag._summarize_day_conversations, target_date)

        # Step 2: evolve from journal
        new_mems = await loop.run_in_executor(
            None, ag.evolution.evolve_from_journal, target_date
        )

        # Step 3: evolve persona
        await loop.run_in_executor(None, ag.evolution.evolve_persona)

        research_count = sum(1 for m in new_mems if m.startswith("[探索研究]"))
        base_count = len(new_mems) - research_count
        parts = []
        if base_count:
            parts.append(f"{base_count} 条日志记忆")
        if research_count:
            parts.append(f"{research_count} 条主动探索知识")

        summary = f"🌱 [自我进化] {target_date} 进化完成，习得 {' + '.join(parts)}。" if parts else \
                  f"🌱 [自我进化] {target_date} 进化完成，无新记忆。"

        workspace_ids = _sync_current_session_to_workspace_mirrors(ag) if ag else []
        _push_chat_event(push_fn, ag, "system", summary, workspace_ids)
        logger.info(f"Daily evolution completed for {target_date}: {len(new_mems)} memories")
        return True, summary

    except Exception as e:
        logger.error(f"Daily evolution error: {e}", exc_info=True)
        _push_chat_event(push_fn, ag, "system", f"⚠️ [自我进化] 出错: {e}")
        return False, str(e)
