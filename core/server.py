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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from core.state import (
    _APP_BASE,
    _ctx_event_queue,
    _sse_lock,
    _sse_subscribers,
    app_state,
    logger,
)


# ── Lifespan ──────────────────────────────────────────────────────────────────

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

        bootstrap.run()

        # ── Agent ──────────────────────────────────────────────────────────
        config_path = str(_APP_BASE / "config.json")
        agent = Agent(config_path=config_path, data_dir=str(_APP_BASE / "data"), auto_evolve=True)
        agent.event_queue = _ctx_event_queue

        # ── Skills ─────────────────────────────────────────────────────────
        _skill_modules = [
            ("basic",        "basic (ask_user, get_time, ...)"),
            ("autogui",      "autogui (autogui_action, screenshot_and_act, ...)"),
            ("web_search",   "web_search (web_fetch)"),
            ("web_reader",   "web_reader (web_read)"),
            ("system_tools", "system_tools (execute_command)"),
            ("file_manager", "file_manager (read_file, write_file, list_dir, ...)"),
            ("office_tools", "office_tools (read_docx, create_pptx, ...)"),
        ]
        for mod_name, label in _skill_modules:
            try:
                import importlib
                mod = importlib.import_module(f"skills.{mod_name}")
                agent.register_skill_module(mod)
                logger.info(f"  [OK] 技能加载: {label}")
            except Exception as e:
                logger.warning(f"  [WARN] 技能加载失败 [{mod_name}]: {e}")

        # ── Plugins ────────────────────────────────────────────────────────
        plugin_manager = PluginManager(
            skill_manager=agent.skills,
            plugins_dir=str(_APP_BASE / "plugins"),
        )
        plugin_manager.load_all()
        plugin_manager.start_watcher()
        agent.start_background_tasks()

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

        # ── Task scheduler ─────────────────────────────────────────────────
        task_scheduler = TaskScheduler(
            storage_path=_APP_BASE / "data" / "scheduler",
            executor=scheduled_task_runner,
        )
        await task_scheduler.start()
        app_state["task_scheduler"] = task_scheduler

        # Register built-in system tasks (idempotent)
        await _register_builtin_tasks(task_scheduler, ScheduledTask, TriggerType, TaskType)

        logger.info("OpenGuiclaw Server initialized successfully.")
        yield

    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        raise
    finally:
        logger.info("Shutting down OpenGuiclaw Server...")
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

from core.routes import chat, memory, skills, agents, vrm, config as config_router

app.include_router(chat.router)
app.include_router(memory.router)
app.include_router(skills.router)
app.include_router(agents.router)
app.include_router(vrm.router)
app.include_router(config_router.router)


# ── Core routes (UI + health + SSE) ──────────────────────────────────────────

@app.get("/", response_class=FileResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


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
