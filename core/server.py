"""
core/server.py — FastAPI application entry point.

Responsibilities:
  - Define the lifespan context manager (startup / shutdown)
  - Create the FastAPI app instance
  - Register all APIRouters from core/routes/
  - Mount static files and templates

All route handlers live in core/routes/*.py.
All shared state lives in core/state.py.
"""
import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from core.im_bots import load_im_bots_from_config, make_channel_name
from core.process_runtime import (
    detect_runtime_mode,
    register_current_run_record,
    remove_run_record,
)
from core.state import (
    _APP_BASE,
    _ctx_event_queue,
    _sse_lock,
    _sse_subscribers,
    app_state,
    logger,
)

_SERVER_STARTED_AT = time.time()


# ── Lifespan ──────────────────────────────────────────────────────────────────

def register_im_adapters(gateway, bots: list[dict]):
    for bot in bots:
        if not bot.get("enabled"):
            continue
        platform = bot["platform"]
        credentials = bot.get("credentials") if isinstance(bot.get("credentials"), dict) else {}
        channel_name = make_channel_name(platform, bot["id"])

        if platform == "dingtalk" and credentials.get("client_id") and credentials.get("client_secret"):
            from core.channels.adapters.dingtalk import DingTalkAdapter

            gateway.register_adapter(
                DingTalkAdapter(
                    app_key=credentials["client_id"],
                    app_secret=credentials["client_secret"],
                    agent_id=credentials.get("agent_id"),
                    channel_name=channel_name,
                    bot_id=bot["id"],
                    footer_elapsed=credentials.get("footer_elapsed"),
                    footer_status=credentials.get("footer_status"),
                )
            )

        if platform == "feishu" and credentials.get("app_id") and credentials.get("app_secret"):
            from core.channels.adapters.feishu import FeishuAdapter

            gateway.register_adapter(
                FeishuAdapter(
                    app_id=credentials["app_id"],
                    app_secret=credentials["app_secret"],
                    verification_token=credentials.get("verification_token"),
                    encrypt_key=credentials.get("encrypt_key"),
                    channel_name=channel_name,
                    bot_id=bot["id"],
                )
            )

        if platform == "telegram" and credentials.get("bot_token"):
            from core.channels.adapters.telegram import TelegramAdapter

            gateway.register_adapter(
                TelegramAdapter(
                    bot_token=credentials["bot_token"],
                    webhook_url=credentials.get("webhook_url"),
                    pairing_code=credentials.get("pairing_code"),
                    proxy=credentials.get("proxy"),
                    channel_name=channel_name,
                    bot_id=bot["id"],
                )
            )

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise all subsystems on startup; clean up on shutdown."""
    logger.info("Starting OpenGuiclaw Server...")
    try:
        from core.agent import Agent
        from core.context import ContextManager
        from core.plugin_manager import PluginManager
        from core import bootstrap
        from core.tasks import scheduled_task_runner
        from core.scheduler import ScheduledTask, TaskScheduler, TriggerType, TaskType
        from core.workspace_manager import get_workspace_manager

        bootstrap.run()

        # ── WorkspaceManager: migrate legacy sessions + ensure default workspace ──
        get_workspace_manager()

        # ── Agent ──────────────────────────────────────────────────────────
        config_path = str(_APP_BASE / "config.json")
        agent = Agent(config_path=config_path, data_dir=str(_APP_BASE / "data"), auto_evolve=True)
        agent.event_queue = _ctx_event_queue

        # ── Plugins (includes all skills, now unified in plugins/) ─────────
        plugin_manager = PluginManager(
            skill_manager=agent.skills,
            plugins_dir=str(_APP_BASE / "plugins"),
        )
        plugin_manager.load_all()
        plugin_manager.start_watcher()
        agent.start_background_tasks()

        async def _auto_connect_mcp_servers():
            try:
                from plugins.mcp_gateway import connect_all_enabled_mcp_servers
                result = await asyncio.to_thread(connect_all_enabled_mcp_servers)
                logger.info(
                    "MCP auto-connect completed: attempted=%s connected=%s failed=%s",
                    result.get("attempted", 0),
                    result.get("connected", 0),
                    result.get("failed", 0),
                )
            except Exception as exc:
                logger.warning("MCP auto-connect failed during startup: %s", exc, exc_info=True)

        startup_mcp_task = asyncio.create_task(_auto_connect_mcp_servers())
        app_state["startup_mcp_task"] = startup_mcp_task

        # ── Channel Gateway ────────────────────────────────────────────────
        from core.channels.gateway import ChannelGateway
        gateway = ChannelGateway(agent=agent)
        register_im_adapters(gateway, load_im_bots_from_config(agent.config))
            
        await gateway.start()
        app_state["gateway"] = gateway

        # ── Vision context manager ─────────────────────────────────────────
        context_manager = ContextManager(
            client=agent.vision_client,
            vision_model=agent.vision_model,
            add_visual_log_func=agent.add_visual_log,
            get_visual_history_func=lambda: [
                m["content"]
                for m in agent.sessions.current.messages
                if m["role"] == "visual_log"
            ],
            update_visual_log_func=agent.update_visual_log,
            get_history_func=lambda: [
                m for m in agent.sessions.current.messages
                if m["role"] in ("user", "assistant")
            ],
            interval_minutes=agent.config.get("proactive", {}).get("interval_minutes", 5),
            proactive_config=agent.config.get("proactive", {}),
        )
        agent.context = context_manager
        context_manager.log_queue = _ctx_event_queue
        context_manager.start()

        app_state["agent"] = agent
        app_state["context_manager"] = context_manager
        app_state["plugin_manager"] = plugin_manager
        app_state["event_loop"] = asyncio.get_event_loop()
        app_state["server_version"] = app.version
        app_state["server_started_at"] = _SERVER_STARTED_AT

        # ── Task scheduler ─────────────────────────────────────────────────
        task_scheduler = TaskScheduler(
            storage_path=_APP_BASE / "data" / "scheduler",
            executor=scheduled_task_runner,
        )
        await task_scheduler.start()
        app_state["task_scheduler"] = task_scheduler

        # Register built-in system tasks (idempotent)
        await _register_builtin_tasks(task_scheduler, ScheduledTask, TriggerType, TaskType)

        run_record_path = register_current_run_record(
            _APP_BASE,
            pid=os.getpid(),
            version=app.version,
            started_at=_SERVER_STARTED_AT,
            mode=detect_runtime_mode(),
            is_frozen=getattr(sys, "frozen", False),
        )
        app_state["run_record_path"] = str(run_record_path)

        logger.info("OpenGuiclaw Server initialized successfully.")
        yield

    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        raise
    finally:
        logger.info("Shutting down OpenGuiclaw Server...")
        remove_run_record(app_state.pop("run_record_path", None))
        startup_mcp_task = app_state.pop("startup_mcp_task", None)
        if startup_mcp_task and not startup_mcp_task.done():
            startup_mcp_task.cancel()
            with suppress(asyncio.CancelledError):
                await startup_mcp_task
        if "plugin_manager" in app_state:
            app_state["plugin_manager"].stop_watcher()
        if "gateway" in app_state:
            await app_state["gateway"].stop()
        if "context_manager" in app_state:
            app_state["context_manager"].stop()
        if "task_scheduler" in app_state:
            await app_state["task_scheduler"].stop()


async def _register_builtin_tasks(scheduler, ScheduledTask, TriggerType, TaskType):
    """Register built-in system tasks if they don't already exist."""
    existing_actions = {t.action for t in scheduler.list_tasks()}

    if "system:daily_selfcheck" not in existing_actions:
        await scheduler.add_task(ScheduledTask(
            id="system_daily_selfcheck",
            name="系统自检",
            description="每日凌晨自动检查数据目录、日志错误、任务状态，生成健康报告",
            trigger_type=TriggerType.CRON,
            trigger_config={"cron": "0 4 * * *"},
            task_type=TaskType.SYSTEM,
            prompt="",
            action="system:daily_selfcheck",
            deletable=False,
        ))
        logger.info("Registered built-in task: system_daily_selfcheck")
    else:
        task = next(t for t in scheduler.list_tasks() if t.action == "system:daily_selfcheck")
        if task.deletable:
            task.deletable = False

    # 自我进化任务：每日凌晨 3 点执行
    if "system:daily_evolution" not in existing_actions:
        await scheduler.add_task(ScheduledTask(
            id="system_daily_evolution",
            name="自我进化",
            description="每日凌晨自动回顾对话日志，提取记忆，更新用户画像和人设",
            trigger_type=TriggerType.CRON,
            trigger_config={"cron": "0 3 * * *"},
            task_type=TaskType.SYSTEM,
            prompt="",
            action="system:daily_evolution",
            deletable=False,
        ))
        logger.info("Registered built-in task: system_daily_evolution")
    else:
        task = next(t for t in scheduler.list_tasks() if t.action == "system:daily_evolution")
        if task.deletable:
            task.deletable = False
            scheduler._save_tasks()

    _CONSOLIDATE_CRON = "0 */3 * * *"
    if "system:memory_consolidate" not in existing_actions:
        await scheduler.add_task(ScheduledTask(
            id="system_memory_consolidate",
            name="记忆整理",
            description="每3小时自动扫描近7天历史会话，提取并写入新的长期记忆",
            trigger_type=TriggerType.CRON,
            trigger_config={"cron": _CONSOLIDATE_CRON},
            task_type=TaskType.SYSTEM,
            prompt="",
            action="system:memory_consolidate",
            deletable=False,
        ))
        logger.info("Registered built-in task: system_memory_consolidate")
    else:
        task = next(t for t in scheduler.list_tasks() if t.action == "system:memory_consolidate")
        changed = False
        if task.deletable:
            task.deletable = False
            changed = True
        if task.trigger_config.get("cron") != _CONSOLIDATE_CRON:
            task.trigger_config["cron"] = _CONSOLIDATE_CRON
            changed = True
        if changed:
            scheduler._save_tasks()

    _AUDIT_CRON = "0 */12 * * *"
    if "system:memory_audit" not in existing_actions:
        await scheduler.add_task(ScheduledTask(
            id="system_memory_audit",
            name="记忆审计与去重",
            description="每12小时自动调用 AI 审查记忆库，执行语义去重、内容合并与冲突纠正",
            trigger_type=TriggerType.CRON,
            trigger_config={"cron": _AUDIT_CRON},
            task_type=TaskType.SYSTEM,
            prompt="",
            action="system:memory_audit",
            deletable=False,
        ))
        logger.info("Registered built-in task: system_memory_audit")
    else:
        task = next(t for t in scheduler.list_tasks() if t.action == "system:memory_audit")
        changed = False
        if task.deletable:
            task.deletable = False
            changed = True
        if task.trigger_config.get("cron") != _AUDIT_CRON:
            task.trigger_config["cron"] = _AUDIT_CRON
            changed = True
        if changed:
            scheduler._save_tasks()


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="OpenGuiclaw Server",
    description="Backend API for OpenGuiclaw AI Desktop Companion.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files & templates
os.makedirs(_APP_BASE / "static", exist_ok=True)
os.makedirs(_APP_BASE / "templates", exist_ok=True)
os.makedirs(_APP_BASE / "data" / "screenshots", exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_APP_BASE / "static")), name="static")
app.mount("/screenshots", StaticFiles(directory=str(_APP_BASE / "data" / "screenshots")), name="screenshots")
templates = Jinja2Templates(directory=str(_APP_BASE / "templates"))


# ── Register routers ──────────────────────────────────────────────────────────

from core.routes import chat, memory, skills, agents, vrm, im, config as config_router
from core.routes import workspace as workspace_router

app.include_router(workspace_router.router)
app.include_router(chat.router)
app.include_router(memory.router)
app.include_router(skills.router)
app.include_router(agents.router)
app.include_router(vrm.router)
app.include_router(im.router)
app.include_router(config_router.router)


# ── Core routes (UI + health + SSE) ──────────────────────────────────────────

@app.get("/", response_class=FileResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "pid": os.getpid(),
        "version": app.version,
        "started_at": datetime.fromtimestamp(_SERVER_STARTED_AT).isoformat(timespec="seconds"),
        "uptime_seconds": max(0, int(time.time() - _SERVER_STARTED_AT)),
        "restart_mode": detect_runtime_mode(),
    }


@app.get("/api/events")
async def sse_events(request: Request):
    """SSE endpoint — streams real-time events to the frontend."""
    async def event_generator():
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        with _sse_lock:
            _sse_subscribers.add(q)
        try:
            yield {"data": json.dumps({"type": "connected"})}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=20)
                    yield {"data": json.dumps(event, ensure_ascii=False)}
                except asyncio.TimeoutError:
                    yield {"data": json.dumps({"type": "heartbeat"})}
        except asyncio.CancelledError:
            pass
        finally:
            with _sse_lock:
                _sse_subscribers.discard(q)

    return EventSourceResponse(event_generator())
