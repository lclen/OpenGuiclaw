"""
launcher.py — openGuiclaw 轻量启动器

职责：
1. 检测系统 Python 3.10+，若无则自动安装（winget 优先，失败则下载官方包）
2. 在 %USERPROFILE%\.openguiclaw\venv 创建/复用 venv
3. 比较 requirements.txt hash，按需 pip install（阿里云镜像）
4. 用 venv python 启动 run_gui.py
5. 全程显示 tkinter 进度窗口，不黑屏卡死

frozen 模式（launcher.exe）：sys.frozen = True，__file__ 不可用，用 sys.executable
开发模式（python launcher.py）：直接运行，行为相同
"""

import hashlib
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext

# ─────────────────────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────────────────────
PYTHON_MIN = (3, 10)
PYTHON_TARGET = "3.11"
PYTHON_DOWNLOAD_URL = "https://registry.npmmirror.com/-/binary/python/3.11.9/python-3.11.9-amd64.exe"
PYTHON_DOWNLOAD_FALLBACK = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
PIP_MIRROR = "https://mirrors.aliyun.com/pypi/simple/"
PIP_TRUSTED_HOST = "mirrors.aliyun.com"
VENV_DIR = Path(os.environ.get("USERPROFILE", "~")).expanduser() / ".openguiclaw" / "venv"
HASH_FILE = Path(os.environ.get("USERPROFILE", "~")).expanduser() / ".openguiclaw" / "requirements.hash"


def get_app_dir() -> Path:
    """返回安装目录（launcher.exe 所在目录 或 launcher.py 所在目录）"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


# ─────────────────────────────────────────────────────────────────────────────
# 进度窗口
# ─────────────────────────────────────────────────────────────────────────────
class ProgressWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("openGuiclaw 启动中...")
        self.root.geometry("560x320")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._allow_close = False
        self._closed = False

        # 居中
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 560) // 2
        y = (self.root.winfo_screenheight() - 320) // 2
        self.root.geometry(f"560x320+{x}+{y}")

        tk.Label(self.root, text="openGuiclaw 正在初始化环境，请稍候...",
                 font=("Microsoft YaHei", 11)).pack(pady=(16, 4))

        self.status_var = tk.StringVar(value="正在检测 Python 环境...")
        tk.Label(self.root, textvariable=self.status_var,
                 font=("Microsoft YaHei", 9), fg="#555").pack()

        self.log = scrolledtext.ScrolledText(self.root, height=10, font=("Consolas", 8),
                                             state="disabled", bg="#1e1e1e", fg="#d4d4d4")
        self.log.pack(fill="both", expand=True, padx=12, pady=8)

    def _on_close(self):
        if self._allow_close:
            self._closed = True
            self.root.destroy()

    def set_status(self, text: str):
        """线程安全：通过 after() 调度到主线程"""
        if not self._closed:
            self.root.after(0, lambda: self.status_var.set(text))

    def append_log(self, text: str):
        """线程安全：通过 after() 调度到主线程"""
        if self._closed:
            return
        def _do():
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(0, _do)

    def close(self):
        if not self._closed:
            self._closed = True
            self._allow_close = True
            self.root.after(0, self.root.destroy)

    def run_in_thread(self, fn):
        """在后台线程运行 fn，主线程跑 tkinter 事件循环"""
        t = threading.Thread(target=fn, daemon=True)
        t.start()
        self.root.mainloop()
        t.join()


# ─────────────────────────────────────────────────────────────────────────────
# Python 检测与安装
# ─────────────────────────────────────────────────────────────────────────────
def _check_python_cmd(cmd: list[str]) -> tuple[bool, str]:
    """检测某个命令是否是合格的 Python 3.10+，返回 (ok, version_str)"""
    try:
        r = subprocess.run(
            cmd + ["-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            ver_str = r.stdout.strip()
            parts = ver_str.split(".")
            major, minor = int(parts[0]), int(parts[1])
            if (major, minor) >= PYTHON_MIN:
                return True, ver_str
    except Exception:
        pass
    return False, ""


def find_python() -> list[str] | None:
    """返回可用的 Python 命令列表，如 ['python'] 或 ['py', '-3.11']，找不到返回 None"""
    candidates = [
        ["py", f"-{PYTHON_TARGET}"],
        ["py", "-3.10"],
        ["python"],
        ["python3"],
        [f"python{PYTHON_TARGET}"],
    ]
    for cmd in candidates:
        ok, ver = _check_python_cmd(cmd)
        if ok:
            return cmd
    return None


def _refresh_path():
    """刷新当前进程的 PATH（读取注册表）"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as k:
            sys_path, _ = winreg.QueryValueEx(k, "Path")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
            try:
                user_path, _ = winreg.QueryValueEx(k, "Path")
            except FileNotFoundError:
                user_path = ""
        os.environ["PATH"] = sys_path + ";" + user_path + ";" + os.environ.get("PATH", "")
    except Exception:
        pass


def install_python_winget(win: ProgressWindow) -> bool:
    """尝试用 winget 静默安装 Python 3.11"""
    win.set_status("正在通过 winget 安装 Python 3.11...")
    win.append_log("[winget] winget install Python.Python.3.11 ...")
    try:
        r = subprocess.run(
            ["winget", "install", "Python.Python.3.11",
             "--accept-source-agreements", "--accept-package-agreements", "--silent"],
            capture_output=True, text=True, timeout=300
        )
        win.append_log(r.stdout[-2000:] if r.stdout else "")
        if r.returncode == 0:
            _refresh_path()
            return find_python() is not None
    except Exception as e:
        win.append_log(f"[winget] 失败: {e}")
    return False


def install_python_download(win: ProgressWindow) -> bool:
    """下载官方安装包静默安装 Python 3.11"""
    import tempfile
    import urllib.request

    win.set_status("正在下载 Python 3.11 安装包（使用镜像源）...")
    installer = Path(tempfile.gettempdir()) / "python-3.11.9-amd64.exe"
    downloaded = False

    for url in [PYTHON_DOWNLOAD_URL, PYTHON_DOWNLOAD_FALLBACK]:
        win.append_log(f"[下载] {url}")
        try:
            urllib.request.urlretrieve(url, installer)
            win.append_log("[下载] 完成")
            downloaded = True
            break
        except Exception as e:
            win.append_log(f"[下载] 失败: {e}")

    if not downloaded:
        return False

    win.set_status("正在安装 Python 3.11...")
    win.append_log("[安装] 静默安装中，请稍候...")
    try:
        # InstallAllUsers=0 避免需要管理员权限；PrependPath=1 自动加入 PATH
        r = subprocess.run(
            [str(installer), "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0"],
            timeout=300
        )
        installer.unlink(missing_ok=True)
        if r.returncode == 0:
            _refresh_path()
            return find_python() is not None
        else:
            win.append_log(f"[安装] 安装程序返回错误码: {r.returncode}")
    except Exception as e:
        win.append_log(f"[安装] 失败: {e}")
        installer.unlink(missing_ok=True)
    return False


def ensure_python(win: ProgressWindow) -> list[str]:
    """确保系统有可用的 Python 3.10+，返回命令列表"""
    cmd = find_python()
    if cmd:
        ok, ver = _check_python_cmd(cmd)
        win.append_log(f"[Python] 检测到 Python {ver} ({' '.join(cmd)})")
        return cmd

    win.append_log("[Python] 未检测到 Python 3.10+，开始自动安装...")

    if install_python_winget(win):
        cmd = find_python()
        if cmd:
            win.append_log("[Python] winget 安装成功")
            return cmd

    if install_python_download(win):
        cmd = find_python()
        if cmd:
            win.append_log("[Python] 下载安装成功")
            return cmd

    # 全部失败，抛出异常由 main() 统一处理
    raise RuntimeError(
        "无法自动安装 Python 3.10+。\n\n"
        "请手动安装后重新启动 openGuiclaw：\n"
        "https://www.python.org/downloads/\n\n"
        "（安装时请勾选 Add Python to PATH）"
    )


# ─────────────────────────────────────────────────────────────────────────────
# venv 管理
# ─────────────────────────────────────────────────────────────────────────────
def ensure_venv(python_cmd: list[str], win: ProgressWindow) -> Path:
    """确保 venv 存在，返回 venv 内 python.exe 路径"""
    venv_python = VENV_DIR / "Scripts" / "python.exe"

    if VENV_DIR.exists() and not venv_python.exists():
        win.append_log("[venv] 检测到损坏的 venv，正在重建...")
        import shutil
        shutil.rmtree(VENV_DIR, ignore_errors=True)

    if not VENV_DIR.exists():
        win.set_status("正在创建 Python 虚拟环境...")
        win.append_log(f"[venv] 创建 venv: {VENV_DIR}")
        VENV_DIR.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            python_cmd + ["-m", "venv", str(VENV_DIR)],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            raise RuntimeError(f"无法创建虚拟环境：\n{r.stderr.strip()}")
        win.append_log("[venv] 创建成功")
    else:
        win.append_log(f"[venv] 复用已有 venv: {VENV_DIR}")

    return venv_python


# ─────────────────────────────────────────────────────────────────────────────
# 依赖安装
# ─────────────────────────────────────────────────────────────────────────────
def _req_hash(req_path: Path) -> str:
    return hashlib.md5(req_path.read_bytes()).hexdigest()


def ensure_deps(venv_python: Path, app_dir: Path, win: ProgressWindow):
    """比较 requirements.txt hash，按需重新 pip install"""
    req_path = app_dir / "requirements.txt"
    if not req_path.exists():
        win.append_log("[deps] requirements.txt 不存在，跳过")
        return

    current_hash = _req_hash(req_path)
    saved_hash = HASH_FILE.read_text(encoding="utf-8").strip() if HASH_FILE.exists() else ""

    # pip.exe 不存在说明 venv 刚创建或损坏，强制重装
    pip_exe = VENV_DIR / "Scripts" / "pip.exe"
    if current_hash == saved_hash and pip_exe.exists():
        win.append_log("[deps] 依赖已是最新，跳过安装")
        return

    win.set_status("正在安装 Python 依赖（首次可能需要几分钟）...")
    win.append_log(f"[deps] 安装依赖（镜像：{PIP_MIRROR}）...")

    # 先升级 pip 本身，避免旧版 pip 解析失败
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--upgrade", "pip",
         "-i", PIP_MIRROR, "--trusted-host", PIP_TRUSTED_HOST, "-q"],
        capture_output=True
    )

    proc = subprocess.Popen(
        [str(venv_python), "-m", "pip", "install", "-r", str(req_path),
         "-i", PIP_MIRROR, "--trusted-host", PIP_TRUSTED_HOST],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace"
    )
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            win.append_log(line)
    proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(
            "pip install 失败，请检查网络连接后重试。\n"
            f"日志文件：{app_dir / 'openguiclaw_startup.log'}"
        )

    HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    HASH_FILE.write_text(current_hash, encoding="utf-8")
    win.append_log("[deps] 依赖安装完成")


# ─────────────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────────────
def main():
    app_dir = get_app_dir()
    win = ProgressWindow()
    _error: list[str] = []  # 用列表在线程间传递错误信息

    def _run():
        try:
            # 1. 确保 Python
            python_cmd = ensure_python(win)

            # 2. 确保 venv
            venv_python = ensure_venv(python_cmd, win)

            # 3. 安装依赖
            ensure_deps(venv_python, app_dir, win)

            # 4. 启动 run_gui.py
            run_gui = app_dir / "run_gui.py"
            if not run_gui.exists():
                _error.append(f"找不到 run_gui.py：{run_gui}\n请确认安装目录完整。")
                win.close()
                return

            win.set_status("正在启动 openGuiclaw...")
            win.append_log(f"[launch] {venv_python} {run_gui}")
            win.close()

            subprocess.Popen(
                [str(venv_python), str(run_gui)],
                cwd=str(app_dir),
                env={**os.environ, "PYTHONPATH": str(app_dir)},
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except SystemExit:
            raise
        except Exception as e:
            _error.append(str(e))
            win.close()

    win.run_in_thread(_run)

    # tkinter 主循环结束后，在主线程弹错误框（此时 root 已销毁，用新 Tk）
    if _error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("启动失败", _error[0])
        root.destroy()
        sys.exit(1)


if __name__ == "__main__":
    main()
