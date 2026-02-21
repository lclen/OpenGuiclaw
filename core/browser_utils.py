import socket
import subprocess
import time

def ensure_chrome_running(port: int = 9222):
    """
    检查指定端口上的 CDP 调试器是否已经启动。
    如果没有启动，则以完全脱离当前终端的方式（后台进程组）拉起新的 Chrome。
    未来可以在这里接入对于配置文件的读取，以便用户通过界面来自定义 Chrome 路径。
    """
    port_open = False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex(('127.0.0.1', port)) == 0:
            port_open = True
            
    if not port_open:
        # TODO: 未来从类似 ConfigManager 中读取真正的路径
        chrome_cmd = rf'"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port={port} --user-data-dir="D:\chrome_debug"'
        try:
            # 使用完全脱离当前终端的方式运行（非常重要，防止挂起主线程阻塞！）
            creation_flags = 0x00000008 | 0x00000200 # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(
                chrome_cmd, 
                shell=True, 
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags
            )
            time.sleep(2) # 缓冲时间
        except Exception:
            pass # 静默容错，抛给上层业务应用去实际报错
