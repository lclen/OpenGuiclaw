"""
core/state.py — Shared application state.

All modules import from here to avoid circular dependencies.
server.py populates these at startup; routers read them at request time.
"""
import logging
import os
import queue
import threading
from pathlib import Path
from typing import Any, Dict

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("qwen_autogui.server")

# ── App base directory ────────────────────────────────────────────────────────
# Set by bootstrap.run() via APP_BASE_DIR env var; falls back to repo root.
_APP_BASE = Path(os.environ.get("APP_BASE_DIR", str(Path(__file__).resolve().parent.parent)))

# ── Runtime state dict ────────────────────────────────────────────────────────
# Keys populated during lifespan startup:
#   "agent"           – Agent instance
#   "context_manager" – ContextManager instance
#   "plugin_manager"  – PluginManager instance
#   "task_scheduler"  – TaskScheduler instance
#   "event_loop"      – asyncio event loop (for thread→async bridging)
app_state: Dict[str, Any] = {}

# ── SSE broadcast system ──────────────────────────────────────────────────────
# Background threads push events into _ctx_event_queue (thread-safe).
# _broadcast_thread() forwards them to every connected SSE client's asyncio.Queue.
_ctx_event_queue: queue.Queue = queue.Queue()
_sse_subscribers: set = set()
_sse_lock = threading.Lock()


def _broadcast_thread() -> None:
    """Bridge: moves items from _ctx_event_queue to all asyncio SSE subscribers."""
    loop = None
    while True:
        try:
            event = _ctx_event_queue.get(timeout=1)
        except queue.Empty:
            continue
        if loop is None:
            loop = app_state.get("event_loop")
        if loop is None:
            continue
        with _sse_lock:
            dead: set = set()
            for q in _sse_subscribers:
                try:
                    loop.call_soon_threadsafe(q.put_nowait, event)
                except Exception:
                    dead.add(q)
            _sse_subscribers.difference_update(dead)


_bridge = threading.Thread(target=_broadcast_thread, daemon=True, name="SSEBridge")
_bridge.start()


# ── Lazy helpers ──────────────────────────────────────────────────────────────

def get_profile_store():
    """Lazily initialise and return the ProfileStore, also deploy presets."""
    if "profile_store" not in app_state:
        from core.profiles import ProfileStore
        from core.presets import deploy_system_presets
        store = ProfileStore(str(_APP_BASE / "data" / "profiles"))
        deploy_system_presets(store)
        app_state["profile_store"] = store
    return app_state["profile_store"]
