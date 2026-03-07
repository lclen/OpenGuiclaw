"""
run_gui.py — openGuiclaw Web UI 入口

由 launcher.py（或开发时直接 python run_gui.py）调用。
launcher 已负责 venv 创建和依赖安装，这里只需启动服务和 WebView 窗口。
"""

import logging
import os
import socket
import sys
import threading
import time
from pathlib import Path

# 项目根目录（此文件所在目录）
_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 执行自检：设置 APP_BASE_DIR、Node 环境变量、创建 data 目录、复制 config
from core import bootstrap
bootstrap.run()

# 日志文件
_log_path = Path(_project_root) / "openguiclaw_startup.log"
logging.basicConfig(
    filename=str(_log_path),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
logging.info("=== OpenGuiclaw 启动 ===")

import uvicorn
import webview
import subprocess
from PIL import Image

import ctypes
import ctypes.wintypes

# System tray
import pystray
from pystray import MenuItem as item

# Backend process reference and control flags
_backend_proc = None
_should_exit = False
_exit_event = threading.Event()  # Used to signal watchdog to stop

def find_free_port(start_port: int = 8010) -> int:
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
        port += 1
    return start_port


def start_backend_process(port: int) -> subprocess.Popen:
    """启动后端无头进程"""
    logging.info(f"Starting backend subsystem on port {port}...")
    env = os.environ.copy()
    env["PYTHONPATH"] = _project_root
    
    # In frozen mode (PyInstaller), sys.executable is the venv python provided by launcher
    # In dev mode, it's just the current python
    cmd = [sys.executable, "-m", "uvicorn", "core.server:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"]
    
    # Hide console window on Windows
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW
        
    return subprocess.Popen(
        cmd,
        cwd=_project_root,
        env=env,
        creationflags=creationflags
    )


def backend_watchdog(port: int):
    """守护线程：监控后端进程，退出则重启"""
    global _backend_proc, _should_exit
    while not _exit_event.is_set():
        if _backend_proc is None:
            _backend_proc = start_backend_process(port)
            
        _backend_proc.wait() # 阻塞直到进程退出
        
        if _exit_event.is_set():
            break
            
        logging.info("Backend subsystem exited. Restarting shortly...")
        time.sleep(0.5)
        _backend_proc = None  # Trigger restart in next loop


def wait_for_tcp(port: int, timeout: float = 30.0, interval: float = 0.2) -> bool:
    """等待端口可以接受 TCP 连接"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(interval)
    return False


class Api:
    """Exposed to JS via window.pywebview.api.*"""
    _window = None  # Set after window creation
    _maximized = False # Track maximization state

    def minimize_window(self):
        if self._window:
            self._window.minimize()

    def toggle_maximize_window(self):
        if self._window:
            try:
                if self._maximized:
                    self._window.restore()
                    self._maximized = False
                else:
                    self._window.maximize()
                    self._maximized = True
            except Exception:
                pass

    def close_window(self):
        # Hide window to tray instead of closing
        if self._window:
            self._window.hide()

    def exit_app(self):
        global _should_exit
        _should_exit = True
        if self._window:
            self._window.destroy()


def apply_native_dark_titlebar(window_title):
    """
    使用 Windows DWM API 修改原生窗口的标题栏颜色，
    从而避免在 frameless=True 模式下的重绘卡顿问题。
    """
    if sys.platform != "win32":
        return

    # 等待窗口被建立
    time.sleep(1.0)
    
    hwnd = ctypes.windll.user32.FindWindowW(None, window_title)
    if not hwnd:
        logging.warning("Could not find window HWND to apply dark titlebar.")
        return

    try:
        set_window_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
        
        # 强制开启系统的沉浸式暗黑模式 (Win11 适用 20, Win10 早期适用 19)
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        set_window_attribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))

        # 自定义标题栏背景色 (Win11 专属 API: 35)
        # 颜色格式为 COLORREF: 0x00bbggrr
        # #0b0f19 转换为 BGR: 0x190f0b
        DWMWA_CAPTION_COLOR = 35
        bg_color = ctypes.c_int(0x00190f0b)
        set_window_attribute(hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(bg_color), ctypes.sizeof(bg_color))
        
        # 确保标题栏文字依然是白色供阅读 (Win11 专属 API: 36)
        DWMWA_TEXT_COLOR = 36
        text_color = ctypes.c_int(0x00ffffff)
        set_window_attribute(hwnd, DWMWA_TEXT_COLOR, ctypes.byref(text_color), ctypes.sizeof(text_color))

        logging.info("Successfully applied native dark title bar.")
    except Exception as e:
        logging.warning(f"Failed to set custom title bar color: {e}")

def create_tray_icon(window):
    """创建系统托盘图标"""
    def on_show(icon, item):
        window.show()
        window.restore()

    def on_hide(icon, item):
        window.hide()

    def on_exit(icon, item):
        global _should_exit
        _should_exit = True
        try:
            window.destroy()
        except:
            pass
        icon.stop()

    # Create a simple icon if logo not found
    icon_path = Path(_project_root) / "static" / "favicon.ico"
    if icon_path.exists():
        icon_img = Image.open(icon_path)
    else:
        # Create a default solid color icon if missing
        icon_img = Image.new('RGB', (64, 64), color=(182, 240, 89))
        
    menu = pystray.Menu(
        item('显示窗口', on_show, default=True),
        item('隐藏到托盘', on_hide),
        pystray.Menu.SEPARATOR,
        item('彻底退出', on_exit)
    )
    
    icon = pystray.Icon("openGuiclaw", icon_img, "openGuiclaw AI 助手", menu)
    return icon


if __name__ == "__main__":
    port = find_free_port()

    # Start the backend watchdog instead of the thread
    watchdog_thread = threading.Thread(target=backend_watchdog, args=(port,), daemon=True)
    watchdog_thread.start()

    # Create the window immediately with a loading screen HTML
    loading_html = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>OpenGuiclaw Loading</title>
        <style>
            :root {
                --noble-black-400: #939aa9;
                --stem-green-500: #b6f059;
            }
            body {
                background: #010205;
                color: #ffffff;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                font-family: 'Inter', system-ui, -apple-system, sans-serif;
                overflow: hidden;
                gap: 20px;
            }
            .spinner {
                width: 40px;
                height: 40px;
                border: 3px solid rgba(182, 240, 89, 0.1);
                border-top-color: var(--stem-green-500);
                border-radius: 50%;
                animation: spin 1s cubic-bezier(0.4, 0, 0.2, 1) infinite;
            }
            @keyframes spin { to { transform: rotate(360deg); } }
            h2 { font-weight: 600; font-size: 20px; margin: 0; color: white; }
            p { color: var(--noble-black-400); font-size: 13px; margin: 0; margin-top: 8px; }
        </style>
    </head>
    <body>
        <div class="spinner"></div>
        <div style="text-align: center;">
            <h2>正在初始化 AI 核心服务</h2>
            <p>程序启动中，请稍候...</p>
        </div>
    </body>
    </html>
    """
    
    # Initialize API before window creation
    app_api = Api()

    window = webview.create_window(
        title="openGuiclaw AI 助手",
        html=loading_html,
        width=1200,
        height=850,
        min_size=(900, 600),
        text_select=True,
        frameless=False,  # <--- FALSE: 借由原生 Windows 窗口管理器获取完美无卡顿调整体验
        background_color='#010205',
        js_api=app_api
    )
    # Link window reference back into Api after creation
    app_api._window = window

    # 绑定窗口关闭事件，阻止退出并隐藏到托盘
    def on_closing():
        global _should_exit
        if not _should_exit:
            window.hide()
            return False  # 阻止关闭事件
        return True # 允许彻底退出

    window.events.closing += on_closing

    # 启动异步线程修改原生标题栏颜色为暗黑专属色
    threading.Thread(target=apply_native_dark_titlebar, args=("openGuiclaw AI 助手",), daemon=True).start()

    def wait_and_load():
        if not wait_for_tcp(port, timeout=60.0):
            import tkinter.messagebox as mb
            mb.showerror("启动失败", "OpenGuiclaw 服务启动超时。")
            os._exit(1)
        window.load_url(f"http://127.0.0.1:{port}")

    threading.Thread(target=wait_and_load, daemon=True).start()

    # Start tray icon in a separate thread
    icon = create_tray_icon(window)
    threading.Thread(target=icon.run, daemon=True).start()

    try:
        webview.start(debug=False)
    finally:
        # 彻底退出逻辑：先通知守护狗停止，再强杀后端进程
        _should_exit = True
        _exit_event.set()  # 通知 watchdog 线程退出循环

        # pystray icon.stop() 有时会阻塞，在 daemon 线程里执行
        threading.Thread(target=lambda: icon.stop(), daemon=True).start()

        if _backend_proc:
            try:
                logging.info("Terminating backend process...")
                _backend_proc.terminate()
                _backend_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                logging.warning("Backend process didn't terminate, killing...")
                _backend_proc.kill()
            except Exception as e:
                logging.error(f"Error terminating backend: {e}")
        
        logging.info("Exiting OpenGuiclaw...")
        os._exit(0)
