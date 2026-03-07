# 需求文档：venv 环境打包方案

## 背景

当前 openGuiclaw 使用 PyInstaller 将所有 Python 依赖打包进 exe，导致：
1. 用户无法在插件中 import 未打包的第三方库
2. AI 自主创建的插件无法使用新依赖
3. sandbox_repl 沙箱受限于打包的库集合
4. 安装包体积庞大（数百 MB）

## 目标

改为 venv 方案：安装时在用户目录创建独立 Python 虚拟环境，启动器 exe 激活 venv 后运行项目。

## 功能需求

### FR-1：轻量启动器 exe
- 用 PyInstaller 打包一个极小的启动器（仅含 Python 标准库）
- 启动器负责：查找/创建 venv → 安装依赖 → 启动 run_gui.py

### FR-2：自动安装 Python（无需用户手动操作）
- 检测系统 Python 3.10+（检查 `python`、`python3`、`py -3.10` 等命令）
- 若未找到，按以下顺序自动安装：
  1. 优先尝试 `winget install Python.Python.3.11`（静默安装）
  2. winget 失败则从官网下载 `python-3.11.9-amd64.exe` 静默安装
  3. 安装完成后刷新 PATH 环境变量
  4. 若仍失败，弹窗提示用户手动安装并打开下载页
- venv 路径：`%USERPROFILE%\.openguiclaw\venv`
- 使用系统 pip 创建 venv

### FR-3：依赖自动安装
- 读取安装目录下的 `requirements.txt`
- 首次运行或 requirements.txt 变更时自动 pip install
- 安装过程显示进度窗口（不能黑屏卡死）

### FR-4：venv 内可自由扩展
- 用户可以手动 `pip install` 新库到 venv
- AI 创建的插件可以在 venv 内安装依赖
- bootstrap.py 的 `check_python_deps` 在 venv 的 pip 下运行

### FR-5：Inno Setup 安装包适配
- installer.iss 安装完成后触发首次 venv 初始化
- 卸载时可选清除 venv 目录

### FR-6：开发模式兼容
- 非 frozen 模式（直接 `python run_gui.py`）行为不变
- 不影响现有开发工作流

## 非功能需求

- 首次启动（含 pip install）时间 < 3 分钟（国内镜像）
- 启动器 exe 体积 < 5 MB
- 支持 Windows 10/11 x64
- venv 路径不含中文，避免编码问题

## 约束

- 系统必须安装 Python 3.10+（安装包内不内置 Python）
- 使用阿里云 pip 镜像加速：`https://mirrors.aliyun.com/pypi/simple/`
