"""
Plugin Manager: Hot-loadable user plugins.

Plugins live in the `plugins/` folder. Each plugin is a .py file that
must expose a `register(manager: SkillManager)` function.

Example plugin file (plugins/my_plugin.py):
-------------------------------------------------
PLUGIN_INFO = {
    "name": "My Plugin",
    "description": "Does something useful.",
    "version": "1.0.0",
    "author": "You",
}

def register(manager):
    @manager.skill(
        name="my_tool",
        description="Does something.",
        parameters={"properties": {"text": {"type": "string"}}, "required": ["text"]},
        category="my_plugin",
    )
    def my_tool(text: str) -> str:
        return f"Result: {text}"
-------------------------------------------------

Usage:
    plugin_mgr = PluginManager(skill_manager, plugins_dir="plugins")
    plugin_mgr.load_all()        # Load all plugins on startup
    plugin_mgr.reload("my_plugin")  # Hot-reload a single plugin
"""

import importlib
import importlib.util
import sys
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional


class PluginInfo:
    """Metadata and state for a loaded plugin."""

    def __init__(self, name: str, path: Path, module, registered_skills: list = None):
        self.name = name
        self.path = path
        self.module = module
        self.loaded_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.enabled = True
        self.skills: list = registered_skills or []  # skill names registered by this plugin

        # Read optional PLUGIN_INFO dict from the module
        meta = getattr(module, "PLUGIN_INFO", {})
        self.display_name = meta.get("name", name)
        self.description = meta.get("description", "（无描述）")
        self.version = meta.get("version", "?")
        self.author = meta.get("author", "unknown")

    def __repr__(self):
        return (
            f"<Plugin {self.name!r} v{self.version}"
            f" by {self.author} — {self.description[:40]}>"
        )


class PluginManager:
    """
    Scans a `plugins/` directory and loads each .py file as a plugin.

    Each plugin must expose:
        register(manager: SkillManager) -> None

    Optionally exposes:
        PLUGIN_INFO = {"name": ..., "description": ..., "version": ..., "author": ...}
    """

    def __init__(self, skill_manager, plugins_dir: str = "plugins"):
        self.skill_manager = skill_manager
        self.plugins_dir = Path(plugins_dir)
        self.plugins_dir.mkdir(exist_ok=True)
        self._plugins: Dict[str, PluginInfo] = {}  # stem -> PluginInfo
        self._watcher_thread: Optional[threading.Thread] = None
        self._watcher_stop = threading.Event()
        self._file_mtimes: Dict[str, float] = {}  # stem -> last mtime
        self._load_lock = threading.Lock()  # BUG#4: protect _load_plugin/_unload_plugin vs skill enable/disable

    # ── Public API ─────────────────────────────────────────────────────

    def load_all(self) -> List[str]:
        """
        Scan plugins_dir and load every .py file.
        Returns list of successfully loaded plugin names.
        """
        loaded = []
        for path in sorted(self.plugins_dir.glob("*.py")):
            if path.stem.startswith("_"):
                continue  # Skip __init__.py etc.
            name = self._load_plugin(path)
            if name:
                loaded.append(name)
            # Record mtime regardless of load success so watcher doesn't re-trigger
            self._file_mtimes[path.stem] = path.stat().st_mtime
        return loaded

    def start_watcher(self, interval: float = 1.0) -> None:
        """Start background thread that auto-reloads plugins on file changes."""
        if self._watcher_thread and self._watcher_thread.is_alive():
            return
        self._watcher_stop.clear()
        self._watcher_thread = threading.Thread(
            target=self._watch_loop,
            args=(interval,),
            daemon=True,
            name="PluginWatcher",
        )
        self._watcher_thread.start()
        print(f"[Plugin] 🔍 文件监视已启动（轮询间隔 {interval}s）")

    def stop_watcher(self) -> None:
        """Stop the background watcher thread."""
        self._watcher_stop.set()

    def _watch_loop(self, interval: float) -> None:
        """Poll plugins_dir for changes and hot-reload as needed."""
        while not self._watcher_stop.wait(interval):
            try:
                current_files = {
                    p.stem: p
                    for p in self.plugins_dir.glob("*.py")
                    if not p.stem.startswith("_")
                }

                # New or modified files
                for stem, path in current_files.items():
                    mtime = path.stat().st_mtime
                    old_mtime = self._file_mtimes.get(stem)
                    if old_mtime is None:
                        # New file — wait briefly to ensure write is complete
                        time.sleep(0.5)
                        if path.stat().st_mtime == mtime:
                            print(f"[Plugin] ✨ 检测到新插件: {stem}.py，自动加载...")
                            self._load_plugin(path)
                            self._file_mtimes[stem] = mtime
                    elif mtime > old_mtime:
                        # Modified file — wait briefly to ensure write is complete
                        time.sleep(0.5)
                        if path.stat().st_mtime == mtime:
                            print(f"[Plugin] 🔄 检测到插件变更: {stem}.py，自动热重载...")
                            self._unload_plugin(stem)
                            self._load_plugin(path)
                            self._file_mtimes[stem] = mtime

                # Deleted files
                for stem in list(self._file_mtimes.keys()):
                    if stem not in current_files:
                        print(f"[Plugin] 🗑️ 检测到插件删除: {stem}.py，自动卸载...")
                        self._unload_plugin(stem)
                        del self._file_mtimes[stem]

            except Exception as e:
                print(f"[Plugin] [WARN] 文件监视异常: {e}")

    def load(self, filename: str) -> Optional[str]:
        """
        Load a single plugin by filename (with or without .py).
        Returns plugin name on success, None on failure.
        """
        stem = filename.removesuffix(".py")
        path = self.plugins_dir / f"{stem}.py"
        if not path.exists():
            print(f"[Plugin] [ERR] 找不到插件文件: {path}")
            return None
        return self._load_plugin(path)

    def reload(self, name: str) -> bool:
        """
        Hot-reload a plugin by stem name.
        Unloads the old version and loads fresh from disk.
        Returns True on success.
        """
        info = self._plugins.get(name)
        if not info:
            print(f"[Plugin] [WARN] 未找到已加载的插件 '{name}'，尝试首次加载...")
            result = self.load(name)
            return result is not None

        path = info.path
        self._unload_plugin(name)
        result = self._load_plugin(path)
        if result:
            print(f"[Plugin] [RELOAD] 插件 '{name}' 已热更新。")
            return True
        return False

    def reload_all(self) -> List[str]:
        """Reload all currently loaded plugins."""
        names = list(self._plugins.keys())
        reloaded = []
        for name in names:
            if self.reload(name):
                reloaded.append(name)
        return reloaded

    def unload(self, name: str) -> bool:
        """Unload a plugin and immediately remove all skills it registered."""
        if name not in self._plugins:
            print(f"[Plugin] [WARN] 插件 '{name}' 未加载。")
            return False
        self._unload_plugin(name)
        print(f"[Plugin] [DEL] 插件 '{name}' 已卸载（已注册的技能将在重启后失效）。")
        return True

    def list_plugins(self) -> List[PluginInfo]:
        """Return list of all loaded plugins."""
        return list(self._plugins.values())

    def summary(self) -> str:
        """Return a formatted summary of loaded plugins."""
        if not self._plugins:
            return "（没有已加载的插件）"
        lines = []
        for info in self._plugins.values():
            status = "[OK]" if info.enabled else "[ERR]"
            lines.append(
                f"  {status} [{info.name}] {info.display_name} v{info.version}"
                f" — {info.description}"
            )
        return "\n".join(lines)

    # ── Internal ───────────────────────────────────────────────────────

    def _load_plugin(self, path: Path) -> Optional[str]:
        """Load a single plugin from path. Returns plugin stem name or None."""
        stem = path.stem
        module_name = f"plugins.{stem}"

        with self._load_lock:
            try:
                # Force reload from disk by removing cached module
                if module_name in sys.modules:
                    del sys.modules[module_name]

                spec = importlib.util.spec_from_file_location(module_name, path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                # Must expose a register() function
                if not hasattr(module, "register"):
                    print(f"[Plugin] [WARN] '{stem}.py' 缺少 register(manager) 函数，跳过。")
                    del sys.modules[module_name]
                    return None

                # Refresh skill enabled/config state from disk before re-registering,
                # so any enable/disable changes made at runtime are preserved after reload.
                self.skill_manager._load_config()

                # Call register — diff registry to find which skills were added
                before_skills = set(self.skill_manager._registry.keys())
                module.register(self.skill_manager)
                after_skills = set(self.skill_manager._registry.keys())
                registered = list(after_skills - before_skills)

                info = PluginInfo(stem, path, module, registered_skills=registered)
                self._plugins[stem] = info
                print(f"  [OK] 插件加载: {info.display_name} v{info.version} ({stem}.py)")
                return stem

            except Exception as e:
                print(f"[Plugin] [ERR] 加载 '{stem}.py' 失败: {e}")
                return None

    def _unload_plugin(self, name: str) -> None:
        """Remove plugin from registry and sys.modules, and clean its skills."""
        with self._load_lock:
            info = self._plugins.get(name)
            if info:
                # Remove all skills registered by this plugin from SkillManager
                for skill_name in info.skills:
                    self.skill_manager._registry.pop(skill_name, None)
                if info.skills:
                    print(f"[Plugin] 🧹 已清除插件 '{name}' 注册的 {len(info.skills)} 个技能: {info.skills}")
            module_name = f"plugins.{name}"
            sys.modules.pop(module_name, None)
            self._plugins.pop(name, None)
