import os
import sys
import threading
import time
import socket
import logging

# Ensure project root is on Python path
sys.path.insert(0, os.path.dirname(__file__))

# 提前执行自检与 Node 环境变量修改
from core import bootstrap
bootstrap.run()

import uvicorn
import webview
import httpx
from core.server import app

def find_free_port(start_port: int = 8010) -> int:
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
        port += 1
    return start_port

def start_server(port: int):
    # 禁用 uvicorn 的 access logs 防止刷屏
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")

def wait_for_server(port: int, timeout: float = 30.0, interval: float = 0.5) -> bool:
    """轮询 /api/health，返回 True 表示服务就绪，False 表示超时。"""
    url = f"http://127.0.0.1:{port}/api/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=1.0)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False

if __name__ == "__main__":
    # 使用无界面的 Uvicorn 后端
    port = find_free_port()
    
    server_thread = threading.Thread(target=start_server, args=(port,), daemon=True)
    server_thread.start()
    
    # 轮询等待 uvicorn 就绪，替代硬编码的 time.sleep(2)
    if not wait_for_server(port):
        import tkinter.messagebox as mb
        mb.showerror("启动失败", "OpenGuiclaw 服务在 30 秒内未能启动，请检查日志。")
        os._exit(1)
    
    window = webview.create_window(
        title="OpenGuiclaw AI 助手",
        url=f"http://127.0.0.1:{port}",
        width=1200,
        height=800,
        min_size=(900, 600),
        text_select=True,
    )
    
    # WebView 接管主线程
    webview.start(private_mode=False)
    
    # 窗口关闭后，强行退出程序
    os._exit(0)
