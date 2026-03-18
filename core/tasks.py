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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from core.automation_context import get_automation_source_context
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
    prefixes = ("dingtalk_", "feishu_", "telegram_")
    for prefix in prefixes:
        if session_id.startswith(prefix):
            return prefix[:-1], session_id[len(prefix):]
    return None, None


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
        resolved_session_id = f"{channel}_{chat_id}"
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
            target_session_id = f"{target_channel}_{target_chat_id}"
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
        return await _system_daily_selfcheck(push_fn)
    if action == "system:memory_consolidate":
        return await _system_memory_consolidate(push_fn, task)
    if action == "system:memory_audit":
        return await _system_memory_audit(push_fn)
    if action == "system:daily_evolution":
        return await _system_daily_evolution(push_fn, task)
    return False, f"Unknown system action: {action}"


# ── Daily self-check ──────────────────────────────────────────────────────────

async def _system_daily_selfcheck(push_fn: Callable) -> tuple[bool, str]:
    """
    Check data-directory integrity, scan log files for errors, and
    summarise scheduler task health.  Pushes a Markdown report to chat.
    """
    lines = [f"## 🔍 系统自检报告 — {datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    issues: list[str] = []

    # 1. Required directories
    required_dirs = [
        str(_APP_BASE / d) for d in [
            "data", "data/sessions", "data/memory", "data/scheduler",
            "data/diary", "data/journals", "data/identities", "data/identity",
            "data/plans", "data/consolidation",
        ]
    ]
    for d in required_dirs:
        if not os.path.exists(d):
            try:
                os.makedirs(d, exist_ok=True)
                issues.append(f"⚠️ 目录 `{d}` 不存在，已自动创建")
            except Exception as e:
                issues.append(f"❌ 目录 `{d}` 创建失败: {e}")

    # 2. Log error scan
    log_errors: dict[str, int] = {}
    for lf in glob.glob("*.log") + glob.glob("logs/*.log"):
        try:
            with open(lf, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if " ERROR " in line or " CRITICAL " in line:
                        parts = line.split(" - ")
                        module = parts[1].strip() if len(parts) > 2 else "unknown"
                        log_errors[module] = log_errors.get(module, 0) + 1
        except Exception:
            pass

    # 3. Scheduler summary
    scheduler = app_state.get("task_scheduler")
    task_summary = {"total": 0, "enabled": 0, "failed": 0}
    if scheduler:
        tasks = scheduler.list_tasks()
        task_summary["total"] = len(tasks)
        task_summary["enabled"] = sum(1 for t in tasks if t.enabled)
        task_summary["failed"] = sum(1 for t in tasks if t.fail_count > 0)

    # 4. Agent + session + memory counts
    ag = app_state.get("agent")
    agent_ok = ag is not None
    session_count = len(glob.glob(str(_APP_BASE / "data" / "sessions" / "*.json")))
    memory_count = 0
    memory_file = str(_APP_BASE / "data" / "memory.jsonl")
    if os.path.exists(memory_file):
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                memory_count = sum(1 for line in f if line.strip())
        except Exception:
            pass

    # 5. AI log analysis & auto-fix (分层修复 + 验证 + 重试降级)
    core_errs, tool_errs, records = 0, 0, []
    if log_errors and ag:
        try:
            from core.self_check import SelfChecker
            checker = SelfChecker(agent=ag)
            core_errs, tool_errs, records = await checker.analyze_and_fix(push_fn)
        except Exception as e:
            logger.error(f"AI self-check failed: {e}")

    # Build report
    lines.append(f"\n**Agent 状态**: {'✅ 在线' if agent_ok else '❌ 离线'}")
    lines.append(f"**会话文件**: {session_count} 个")
    lines.append(f"**记忆条目**: {memory_count} 条")
    lines.append(
        f"\n**计划任务**: 共 {task_summary['total']} 个，"
        f"启用 {task_summary['enabled']} 个，"
        f"有失败记录 {task_summary['failed']} 个"
    )
    if log_errors:
        lines.append(f"\n**日志错误** ({sum(log_errors.values())} 条):")
        for mod, cnt in sorted(log_errors.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"  - `{mod}`: {cnt} 次")
        if records:
            fixed_count = sum(1 for r in records if r.success)
            lines.append(
                f"\n  *AI 诊断*: 核心错误 **{core_errs}** 个 (需人工处理)，"
                f"能力层错误 **{tool_errs}** 个，"
                f"自动修复成功 **{fixed_count}** 个"
            )
    else:
        lines.append("\n**日志错误**: 无")

    if issues or records:
        lines.append("\n**自动修复 / 诊断建议**:")
        for issue in issues:
            lines.append(f"  - {issue}")
        for rec in records:
            if not rec.can_fix:
                prefix = "🔴 [需人工处理]"
            elif rec.success:
                prefix = "✅ [已自动修复]"
            else:
                prefix = "⚠️ [修复失败]"
            lines.append(f"  - {prefix} `{rec.component}`: {rec.error_pattern}")
            lines.append(f"    👉 {rec.fix_action}")
            if rec.verification_result:
                lines.append(f"    🔍 验证: {rec.verification_result}")

    status = (
        "✅ 系统运行正常"
        if not issues and not log_errors
        else f"⚠️ 发现 {len(issues)} 个问题，{len(log_errors)} 个错误模块"
    )
    lines.append(f"\n**总结**: {status}")
    report = "\n".join(lines)

    workspace_ids: list[str] = []
    if ag:
        ag.sessions.current.add_message("assistant", report)
        ag.sessions.save()
        workspace_ids = _sync_current_session_to_workspace_mirrors(ag)
    _push_chat_event(push_fn, ag, "assistant", report, workspace_ids)
    logger.info(f"System selfcheck completed: {status}")
    return True, status


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
