"""
Bootstrap: 启动前自动检查并安装所有依赖，初始化运行时目录和配置。

- 设置 APP_BASE_DIR 环境变量（frozen 时为 exe 所在目录，开发时为项目根目录）
- 创建所有必要的 data/ 子目录
- config.json 不存在时从 config.json.example 自动复制
- Python 依赖：读取 requirements.txt，用 pip 安装缺失的包
- npm 全局包：读取 npm-requirements.txt，用 npm install -g 安装缺失的包
"""

import os
import subprocess
import sys
from pathlib import Path

_already_run = False  # 防止 uvicorn reload 时重复执行

# 所有必要的 data 子目录（与实际运行时一致）
_REQUIRED_DATA_DIRS = [
    "data",
    "data/sessions",
    "data/memory",
    "data/diary",
    "data/journals",
    "data/identities",
    "data/identity",
    "data/plans",
    "data/scheduler",
    "data/screenshots",
    "data/consolidation",
]


def get_app_base_dir() -> Path:
    """
    返回程序的"家目录"：
    - frozen（PyInstaller）：exe 所在目录（可写）
    - 开发模式：项目根目录（bootstrap.py 的上两级）
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def setup_node_env() -> None:
    """将内置便携版 Node.js 路径前推至 PATH 顶部，同时设置 npm global 目录为用户目录下的隔离路径"""
    app_base = get_app_base_dir()
    os.environ["APP_BASE_DIR"] = str(app_base)

    # frozen 时 bin-node 在 _MEIPASS 里（只读资源），开发时在项目根
    if getattr(sys, "frozen", False):
        node_bin = Path(sys._MEIPASS) / "bin-node"  # type: ignore
    else:
        node_bin = app_base / "bin-node"

    if node_bin.exists():
        # 将 bin-node 置顶
        os.environ["PATH"] = f"{node_bin}{os.pathsep}{os.environ.get('PATH', '')}"

    # 隔离用户级 NPM 安装目录（解决装在 Program Files 下被 UAC 拦截的问题）
    user_app_dir = Path(os.environ.get("USERPROFILE", "~")).expanduser() / ".openguiclaw"
    npm_global = user_app_dir / "npm-global"
    npm_global.mkdir(parents=True, exist_ok=True)

    os.environ["NPM_CONFIG_PREFIX"] = str(npm_global)
    # 将 npm global bin 也加到 PATH，这样能直接执行 npx 和全局安装的命令
    os.environ["PATH"] = f"{npm_global}{os.pathsep}{os.environ.get('PATH', '')}"


def ensure_data_dirs() -> None:
    """在 APP_BASE_DIR 下创建所有必要的 data 子目录。幂等操作，可多次调用。"""
    base = get_app_base_dir()
    for rel in _REQUIRED_DATA_DIRS:
        target = base / rel
        target.mkdir(parents=True, exist_ok=True)
    print("[Bootstrap] [OK] data 子目录已就绪")


def ensure_config() -> None:
    """config.json 不存在时，从 config.json.example 自动复制。
    frozen 模式下 example 可能在 _MEIPASS（只读资源），也可能在 exe 旁边。
    """
    base = get_app_base_dir()
    config = base / "config.json"

    if config.exists():
        return

    # 优先找 exe 旁边的 example，frozen 时再从 _MEIPASS 找
    example = base / "config.json.example"
    if not example.exists() and getattr(sys, "frozen", False):
        meipass_example = Path(sys._MEIPASS) / "config.json.example"  # type: ignore
        if meipass_example.exists():
            example = meipass_example

    if example.exists():
        import shutil
        shutil.copy2(example, config)
        print("[Bootstrap] [OK] 已从 config.json.example 创建 config.json，请填写 API Key")
    else:
        print("[Bootstrap] [WARN] config.json 和 config.json.example 均不存在，请手动创建配置文件")


def _parse_pkg_name(pkg: str) -> str:
    """从 'pkg@ver' 或 '@scope/pkg@ver' 中提取包名（不含版本号）。

    Examples:
        "@pixiv/three-vrm@2.1.0" -> "@pixiv/three-vrm"
        "@scope/pkg"              -> "@scope/pkg"
        "agent-browser@0.16.3"   -> "agent-browser"
        "agent-browser"           -> "agent-browser"
    """
    if pkg.startswith("@"):
        # scoped: "@scope/pkg@ver" → "@scope/pkg"
        rest = pkg[1:]           # "scope/pkg@ver"
        name_part = rest.split("@")[0]  # "scope/pkg"
        return "@" + name_part
    else:
        return pkg.split("@")[0]


def _is_npm_pkg_installed(pkg_name: str, npm_global_prefix: str) -> bool:
    """通过扫描 node_modules 目录判断包是否已安装（替代 npm ls 解析，更可靠）。

    Args:
        pkg_name: 不含版本号的包名，如 "agent-browser" 或 "@scope/pkg"
        npm_global_prefix: NPM_CONFIG_PREFIX 路径
    """
    node_modules = Path(npm_global_prefix) / "node_modules"
    if not node_modules.exists():
        return False

    if pkg_name.startswith("@"):
        # scoped: "@scope/pkg" → node_modules/@scope/pkg/
        rest = pkg_name[1:]  # "scope/pkg"
        if "/" not in rest:
            return False
        scope, name = rest.split("/", 1)
        return (node_modules / f"@{scope}" / name).is_dir()
    else:
        return (node_modules / pkg_name).is_dir()


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """在 Windows 上必须 shell=True 才能找到 npm/npx 等命令。"""
    return subprocess.run(cmd, capture_output=True, text=True, shell=True, env=os.environ.copy(), **kwargs)


def _get_venv_python() -> str | None:
    """返回 venv 内的 python.exe 路径（若存在）。
    venv 路径：%USERPROFILE%\.openguiclaw\venv（与 launcher.py 保持一致）
    """
    venv_dir = Path(os.environ.get("USERPROFILE", "~")).expanduser() / ".openguiclaw" / "venv"
    venv_python = venv_dir / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return None


def check_python_deps(requirements_file: str = "requirements.txt") -> None:
    """安装 Python 依赖。
    - 开发模式：使用当前 sys.executable（通常已在 venv 中）
    - launcher 启动（run_gui.py 由 venv python 运行）：sys.executable 已是 venv python，直接用
    - 兜底：尝试找 ~/.openguiclaw/venv/Scripts/python.exe
    """
    base = get_app_base_dir()
    req_path = base / requirements_file
    if not req_path.exists():
        return

    # 优先使用当前 python（launcher 已切换到 venv python）
    pip_python = sys.executable

    # 若当前 python 不在 venv 中，尝试找 venv python
    venv_python = _get_venv_python()
    if venv_python and venv_python != sys.executable:
        pip_python = venv_python

    print("[Bootstrap] 检查 Python 依赖...")
    result = _run([pip_python, "-m", "pip", "install", "-r", str(req_path),
                   "-i", "https://mirrors.aliyun.com/pypi/simple/",
                   "--trusted-host", "mirrors.aliyun.com",
                   "--quiet"])
    if result.returncode != 0:
        print(f"[Bootstrap] [WARN] pip install 出现问题:\n{result.stderr.strip()}")
    else:
        print("[Bootstrap] [OK] Python 依赖已就绪")


def check_npm_deps(npm_requirements_file: str = "npm-requirements.txt") -> None:
    base = get_app_base_dir()
    req_path = base / npm_requirements_file
    if not req_path.exists():
        return

    packages = []
    for line in req_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        packages.append(line)

    if not packages:
        return

    print("[Bootstrap] 检查 npm 全局包...")

    npm_global_prefix = os.environ.get("NPM_CONFIG_PREFIX", "")

    missing = []
    for pkg in packages:
        pkg_name = _parse_pkg_name(pkg)
        if not _is_npm_pkg_installed(pkg_name, npm_global_prefix):
            missing.append(pkg)

    if not missing:
        print("[Bootstrap] [OK] npm 全局包已就绪")
        return

    for pkg in missing:
        print(f"[Bootstrap] 安装 npm 包: {pkg} ...")
        result = _run(["npm", "install", "-g", pkg, "--registry=https://registry.npmmirror.com"])
        if result.returncode != 0:
            print(f"[Bootstrap] [WARN] 安装 {pkg} 失败:\n{result.stderr.strip()}")
        else:
            print(f"[Bootstrap] [OK] {pkg} 安装成功")


def print_environment_diagnostics() -> None:
    """输出当前环境变量和重要配置目录，供故障排查用"""
    import shutil
    print("=" * 50)
    print("[环境诊断] OpenGuiclaw 启动预检")
    print("=" * 50)

    # Python 路径
    print(f" - [Python] Executable: {sys.executable}")

    # APP_BASE_DIR
    print(f" - [App Base] APP_BASE_DIR: {os.environ.get('APP_BASE_DIR', '未设置')}")

    # 查找并确认 Node 有效性
    node_exe = shutil.which("node")
    npm_exe = shutil.which("npm")
    print(f" - [Node.js] node path: {node_exe if node_exe else '未找到'}")
    print(f" - [Node.js] npm path: {npm_exe if npm_exe else '未找到'}")

    # 打印沙盒依赖存放点
    npm_global = os.environ.get("NPM_CONFIG_PREFIX", "")
    print(f" - [沙盒隔离] NPM 全局包路径: {npm_global}")
    print("=" * 50)


def run(skip_python: bool = False, skip_npm: bool = False) -> None:
    """执行全部依赖检查与初始化。内置防重复执行保护，多次调用只跑一次。"""
    global _already_run
    if _already_run:
        return
    _already_run = True

    setup_node_env()            # 1. 设置 APP_BASE_DIR 和 PATH
    ensure_data_dirs()          # 2. 创建 data 子目录
    ensure_config()             # 3. 确保 config.json 存在
    print_environment_diagnostics()

    if not skip_python:
        check_python_deps()
    if not skip_npm:
        check_npm_deps()
