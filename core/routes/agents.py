"""Agent profiles, models, diagnostics, scheduler, and token-stats routes."""

import sys
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from core.process_runtime import cleanup_process_runtime_targets, detect_runtime_mode
from core.runtime_diagnostics import (
    ROLE_HEALTH_LABELS as _ROLE_HEALTH_LABELS,
    build_health_targets as _build_health_targets_impl,
    classify_health_error as _classify_health_error_impl,
    collect_diagnostics_snapshot,
    probe_health_target as _probe_health_target_impl,
    safe_text as _safe_text_impl,
)
from core.state import app_state, _APP_BASE, logger, get_profile_store

router = APIRouter(tags=["agents"])

_ROLE_HEALTH_LABELS = {
    "api": "主模型",
    "vision": "视觉模型",
    "image_analyzer": "图像解析",
    "embedding": "嵌入模型",
    "autogui": "GUI 操作",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_scheduler():
    s = app_state.get("task_scheduler")
    if not s:
        raise HTTPException(status_code=500, detail="Scheduler not ready")
    return s


def _load_config_json() -> tuple[dict[str, Any], Path]:
    cfg_path = _APP_BASE / "config.json"
    if not cfg_path.exists():
        raise HTTPException(status_code=404, detail="config.json not found")
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f), cfg_path


def _safe_text(value: Any) -> str:
    return _safe_text_impl(value)


def _classify_health_error(exc: Exception) -> tuple[str, str, str]:
    return _classify_health_error_impl(exc)


def _build_probe_result(
    target: dict[str, Any],
    *,
    status: str,
    latency_ms: int | None,
    error: str | None,
    error_code: str | None,
    hint: str | None,
    configured: bool,
) -> dict[str, Any]:
    return {
        "name": target["name"],
        "label": target.get("label"),
        "kind": target.get("kind"),
        "role": target.get("role"),
        "status": status,
        "latency_ms": latency_ms,
        "error": error,
        "error_code": error_code,
        "hint": hint,
        "configured": configured,
        "last_checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def _check_target_configuration(target: dict[str, Any]) -> tuple[bool, str | None, str | None, str | None]:
    base_url = _safe_text(target.get("base_url"))
    model = _safe_text(target.get("model"))

    if not base_url:
        return (
            False,
            "missing_base_url",
            "Base URL 未配置",
            "请在模型设置中填写 Base URL 后再执行健康检查",
        )
    if not model:
        return (
            False,
            "missing_model",
            "模型名称未配置",
            "请在模型设置中填写模型名后再执行健康检查",
        )
    return (True, None, None, None)


def _build_health_targets(config: dict[str, Any]) -> list[dict[str, Any]]:
    return _build_health_targets_impl(config)


async def _probe_health_target(target: dict[str, Any], timeout_seconds: float = 15.0) -> dict[str, Any]:
    return await _probe_health_target_impl(target, timeout_seconds=timeout_seconds)


# ── Pydantic models ───────────────────────────────────────────────────────────

class AgentProfileRequest(BaseModel):
    name: str
    description: str = ""
    icon: str = "🤖"
    color: str = "#4A90D9"
    category: str = "general"
    custom_prompt: str = ""
    skills: list = []
    skills_mode: str = "inclusive"
    preferred_model: Optional[str] = None


class HealthCheckRequest(BaseModel):
    endpoint_name: Optional[str] = None


class ProcessCleanupRequest(BaseModel):
    target_pids: Optional[list[int]] = None
    target_records: Optional[list[str]] = None


# ── Agent profiles ────────────────────────────────────────────────────────────

@router.get("/api/agents")
async def list_agents():
    store = get_profile_store()
    return {"agents": [p.to_dict() for p in store.get_all()]}


@router.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    store = get_profile_store()
    profile = store.get(agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent not found")
    return profile.to_dict()


@router.post("/api/agents")
async def create_agent(req: AgentProfileRequest):
    import re, uuid
    from core.profiles import AgentProfile, AgentType, SkillsMode
    store = get_profile_store()
    base_id = re.sub(r"[^\w\-]", "-", req.name.lower().strip())
    agent_id = base_id or str(uuid.uuid4())[:8]
    if store.exists(agent_id):
        agent_id = f"{agent_id}-{str(uuid.uuid4())[:4]}"
    try:
        sm = SkillsMode(req.skills_mode)
    except ValueError:
        sm = SkillsMode.INCLUSIVE
    profile = AgentProfile(
        id=agent_id, name=req.name, description=req.description,
        type=AgentType.CUSTOM, skills=req.skills, skills_mode=sm,
        custom_prompt=req.custom_prompt, icon=req.icon, color=req.color,
        category=req.category, created_by="user", user_customized=True,
        preferred_model=req.preferred_model,
    )
    store.save(profile)
    logger.info(f"Created agent profile: {agent_id}")
    return {"status": "ok", "agent": profile.to_dict()}


@router.put("/api/agents/{agent_id}")
async def update_agent(agent_id: str, req: AgentProfileRequest):
    from core.profiles import SkillsMode
    store = get_profile_store()
    profile = store.get(agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        sm = SkillsMode(req.skills_mode)
    except ValueError:
        sm = profile.skills_mode
    profile.name = req.name
    profile.description = req.description
    profile.icon = req.icon
    profile.color = req.color
    profile.category = req.category
    profile.custom_prompt = req.custom_prompt
    profile.skills = req.skills
    profile.skills_mode = sm
    profile.user_customized = True
    profile.preferred_model = req.preferred_model
    store.save(profile)
    logger.info(f"Updated agent profile: {agent_id}")
    return {"status": "ok", "agent": profile.to_dict()}


@router.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str):
    from core.profiles import AgentType
    store = get_profile_store()
    profile = store.get(agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Agent not found")
    if profile.type == AgentType.SYSTEM:
        raise HTTPException(status_code=403, detail="System agents cannot be deleted")
    filepath = _APP_BASE / "data" / "profiles" / f"{agent_id}.json"
    try:
        if filepath.exists():
            filepath.unlink()
        del store._cache[agent_id]
        logger.info(f"Deleted agent profile: {agent_id}")
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Models list ───────────────────────────────────────────────────────────────

@router.get("/api/models/list")
async def list_available_models():
    cfg_path = _APP_BASE / "config.json"
    if not cfg_path.exists():
        return {"models": []}
    try:
        with open(cfg_path, encoding="utf-8") as f:
            config = json.load(f)
        models = []
        seen: set = set()
        for ep in config.get("chat_endpoints", []):
            m = ep.get("model")
            if m and m not in seen:
                models.append({"id": m, "name": ep.get("name", m)})
                seen.add(m)
        main_m = config.get("api", {}).get("model")
        if main_m and main_m not in seen:
            models.append({"id": main_m, "name": f"核心模型 ({main_m})"})
        return {"models": models}
    except Exception as e:
        logger.error(f"Failed to load models: {e}")
        return {"models": []}


# ── Diagnostics ───────────────────────────────────────────────────────────────

@router.get("/api/diagnostics")
async def get_diagnostics():
    return collect_diagnostics_snapshot(
        _APP_BASE,
        current_pid=os.getpid(),
        version=str(app_state.get("server_version") or "unknown"),
        started_at=float(app_state.get("server_started_at") or time.time()),
        mode=detect_runtime_mode(),
        is_frozen=getattr(sys, "frozen", False),
    )


@router.post("/api/health/check")
async def health_check_endpoints(body: HealthCheckRequest):
    config, _ = _load_config_json()
    targets = _build_health_targets(config)

    if body.endpoint_name:
        target = next((item for item in targets if item["name"] == body.endpoint_name), None)
        if not target:
            raise HTTPException(status_code=404, detail=f"Endpoint not found: {body.endpoint_name}")
        results = [await _probe_health_target(target)]
        return {"results": results}

    if not targets:
        return {"results": []}

    results = await asyncio.gather(*[_probe_health_target(target) for target in targets])
    return {"results": results}


@router.post("/api/diagnostics/process/cleanup")
async def cleanup_process_runtime(body: ProcessCleanupRequest):
    started_at = float(app_state.get("server_started_at") or time.time())
    version = str(app_state.get("server_version") or "unknown")
    result = cleanup_process_runtime_targets(
        _APP_BASE,
        current_pid=os.getpid(),
        version=version,
        started_at=started_at,
        target_pids=body.target_pids or [],
        target_records=body.target_records or [],
        mode=detect_runtime_mode(),
        is_frozen=getattr(sys, "frozen", False),
    )
    return result


@router.get("/api/diagnostics/export")
async def export_diagnostics():
    info = await get_diagnostics()
    lines = [
        "=== openGuiclaw 环境诊断报告 ===",
        f"时间: {datetime.fromtimestamp(info['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}",
        "", "[系统信息]",
        f"操作系统: {info['system']['os']}",
        f"Python 版本: {info['system']['python_version']}",
        f"Python 路径: {info['system']['python_executable']}",
        f"应用目录: {info['system']['app_dir']}",
        f"是否打包运行 (Frozen): {info['system']['frozen']}",
        "", "[网络与代理]",
    ]
    for k, v in info["network"]["proxies"].items():
        lines.append(f"{k.upper()}_PROXY: {v if v else '未设置'}")
    net = info["network"]["connectivity"]
    if net["status"] == "ok":
        lines.append(f"外网连通性 (阿里云镜像): 正常 ({net['latency_ms']}ms)")
    else:
        lines.append(f"外网连通性 (阿里云镜像): 失败 ({net.get('error')})")
    process_runtime = info.get("process_runtime", {})
    lines += ["", "[进程运行态]"]
    lines.append(f"当前 PID: {process_runtime.get('current_pid', '未知')}")
    for conflict in process_runtime.get("conflicts", []):
        lines.append(
            f"- {conflict.get('type')}: pid={conflict.get('pid')} record={conflict.get('record_id') or '-'} {conflict.get('summary')}"
        )
    lines += ["", "[核心依赖检查]"]
    for mod, ok in info["dependencies"].items():
        lines.append(f"{mod}: {'[OK] 已安装' if ok else '[FAILED] 缺失'}")
    report = "\n".join(lines)
    filename = f"openguiclaw_diag_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    return PlainTextResponse(report, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ── Scheduler ─────────────────────────────────────────────────────────────────

@router.get("/api/scheduler/tasks")
async def list_tasks():
    scheduler = _require_scheduler()
    tasks = []
    for task in scheduler.list_tasks():
        item = task.to_dict()
        latest_execution = scheduler.get_latest_execution(task.id)
        item["last_execution"] = latest_execution.to_dict() if latest_execution else None
        tasks.append(item)
    return {"tasks": tasks}


@router.post("/api/scheduler/tasks")
async def create_task(req: Request):
    from core.scheduler import ScheduledTask, TriggerType, TaskType
    scheduler = _require_scheduler()
    data = await req.json()
    try:
        task = ScheduledTask.create(
            name=data["name"],
            description=data.get("description", ""),
            trigger_type=TriggerType(data["trigger_type"]),
            trigger_config=data["trigger_config"],
            prompt=data.get("prompt", ""),
            task_type=TaskType(data.get("task_type", "task")),
            reminder_message=data.get("reminder_message"),
            action=data.get("action"),
            delivery_targets=data.get("delivery_targets") or [],
            target_kind=data.get("target_kind"),
            target_workspace_id=data.get("target_workspace_id"),
            target_session_id=data.get("target_session_id"),
            target_channel=data.get("target_channel"),
            target_chat_id=data.get("target_chat_id"),
        )
        if not data.get("enabled", True):
            task.disable()
        await scheduler.add_task(task)
        return {"status": "success", "task_id": task.id}
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/scheduler/tasks/{task_id}")
async def update_task(task_id: str, req: Request):
    scheduler = _require_scheduler()
    data = await req.json()
    if not await scheduler.update_task(task_id, data):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "success"}


@router.delete("/api/scheduler/tasks/{task_id}")
async def delete_task(task_id: str):
    scheduler = _require_scheduler()
    if not await scheduler.remove_task(task_id, force=True):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "success"}


@router.post("/api/scheduler/tasks/{task_id}/toggle")
async def toggle_task(task_id: str, req: Request):
    scheduler = _require_scheduler()
    data = await req.json()
    enabled = data.get("enabled", True)
    success = await (scheduler.enable_task(task_id) if enabled else scheduler.disable_task(task_id))
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "success"}


@router.post("/api/scheduler/tasks/{task_id}/trigger")
async def trigger_task(task_id: str):
    scheduler = _require_scheduler()
    execution = await scheduler.trigger_now(task_id, trigger_source="manual_trigger")
    if not execution:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "success", "execution": execution.to_dict()}


@router.get("/api/scheduler/executions")
async def list_task_executions(task_id: str | None = None, limit: int = 50):
    scheduler = _require_scheduler()
    limit = max(1, min(limit, 200))
    executions = scheduler.get_executions(task_id=task_id, limit=limit)
    return {"executions": [execution.to_dict() for execution in executions]}

# ── Token stats ───────────────────────────────────────────────────────────────

_DELTA_MAP = {
    "1d": timedelta(days=1), "3d": timedelta(days=3),
    "1w": timedelta(weeks=1), "1m": timedelta(days=30),
    "6m": timedelta(days=180), "1y": timedelta(days=365),
}


@router.get("/api/token-stats")
async def get_token_stats(period: str = "all"):
    """Return token usage statistics for the given period."""
    agent = app_state.get("agent")
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    where_clause = ""
    params: list = []
    
    # Calculate timezone offset
    utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
    local_now = datetime.now()
    offset_seconds = (local_now - utc_now).total_seconds()
    offset_hours = offset_seconds / 3600
    offset_modifier = f"{offset_hours:+.1f} hours"

    if period in _DELTA_MAP:
        # Calculate 'since' based on local midnight to align with user expectations of "days"
        days_to_subtract = _DELTA_MAP[period].days
        if days_to_subtract == 1:
            # For 1d (Today), start at 00:00:00 local time today
            local_since = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # For 3d, 1w etc., go back the corresponding number of days from today's midnight
            local_since = (local_now - timedelta(days=days_to_subtract - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Convert local_since back to UTC for the database query
        utc_since = local_since - timedelta(seconds=offset_seconds)
        since = utc_since.strftime("%Y-%m-%d %H:%M:%S")
        
        where_clause = "WHERE timestamp >= ?"
        params = [since]

    try:
        with sqlite3.connect(agent._token_db_path) as conn:
            row = conn.execute(
                f"SELECT SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens), COUNT(*) "
                f"FROM token_usage {where_clause}", params
            ).fetchone()
            total_p, total_c, total_t, total_req = (row[0] or 0, row[1] or 0, row[2] or 0, row[3] or 0)

            model_rows = conn.execute(
                f"SELECT model, SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens), COUNT(*) "
                f"FROM token_usage {where_clause} GROUP BY model", params
            ).fetchall()
            by_model = {
                r[0]: {"prompt": r[1] or 0, "completion": r[2] or 0, "total": r[3] or 0, "count": r[4] or 0}
                for r in model_rows
            }

            if period in ("1d", "3d"):
                sqlite_fmt = f"strftime('%Y-%m-%d %H:00', datetime(timestamp, '{offset_modifier}'))"
            else:
                sqlite_fmt = f"strftime('%Y-%m-%d', datetime(timestamp, '{offset_modifier}'))"
            tl_rows = conn.execute(
                f"SELECT {sqlite_fmt} as bucket, SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens) "
                f"FROM token_usage {where_clause} GROUP BY bucket ORDER BY bucket", params
            ).fetchall()
            timeline = [
                {"time": r[0], "prompt": r[1] or 0, "completion": r[2] or 0, "total": r[3] or 0}
                for r in tl_rows
            ]
    except Exception:
        return agent.token_stats

    return {
        "period": period,
        "total_prompt_tokens": total_p,
        "total_completion_tokens": total_c,
        "total_tokens": total_t,
        "request_count": total_req,
        "by_model": by_model,
        "timeline": timeline,
    }


@router.post("/api/token-stats/reset")
async def reset_token_stats():
    agent = app_state.get("agent")
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    try:
        with sqlite3.connect(agent._token_db_path) as conn:
            conn.execute("DELETE FROM token_usage")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}")
    agent.token_stats = {
        "total_prompt_tokens": 0, "total_completion_tokens": 0,
        "total_tokens": 0, "request_count": 0, "by_model": {},
    }
    return {"status": "ok"}
