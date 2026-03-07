# 设计文档：venv 环境打包方案

## 架构概览

```
安装包 (openGuiclaw_Setup_x.x.x.exe)
├── launcher.exe          ← 轻量启动器（PyInstaller，< 5MB）
├── 项目源码/              ← 所有 .py 文件、templates、static 等
├── requirements.txt
├── config.json.example
└── PERSONA.md

用户目录
└── %USERPROFILE%\.openguiclaw\
    └── venv\             ← 首次启动时自动创建
        └── Scripts\
            ├── python.exe
            └── pip.exe
```

## 启动流程

```
launcher.exe 启动
    │
    ├─ 检测 venv 是否存在？
    │   ├─ 否 → 查找系统 Python 3.10+
    │   │       ├─ 找不到 → 弹窗提示安装 Python，打开下载页，退出
    │   │       └─ 找到 → 创建 venv
    │   └─ 是 → 继续
    │
    ├─ 检测依赖是否最新？（比较 requirements.txt hash）
    │   └─ 需要更新 → 显示进度窗口，运行 pip install -r requirements.txt
    │
    └─ 用 venv/Scripts/python.exe 运行 run_gui.py
```

## 核心组件

### 1. launcher.py（新建）

```
openGuiclaw/
└── launcher.py    ← 新文件，替代 run_gui.py 作为 PyInstaller 入口
```

职责：
- 定位 venv（`~/.openguiclaw/venv`）
- 检测并创建 venv
- 检测依赖变更并安装
- 用 subprocess 启动 `venv/python run_gui.py`
- 显示启动进度（tkinter 简单窗口）

### 2. build_exe.bat 修改

- PyInstaller 入口改为 `launcher.py`
- `--onefile` 模式（单文件 exe，更小）
- 不再需要 `--add-data` 打包所有依赖
- 只需打包 launcher 本身需要的标准库

### 3. installer.iss 修改

- `[Files]` 打包项目源码（不含 dist/）
- 安装后运行 launcher.exe 触发首次 venv 初始化
- 卸载时询问是否删除 `~/.openguiclaw/venv`

### 4. bootstrap.py 修改

- `check_python_deps()` 在 venv 环境下正常运行（不再跳过 frozen）
- `get_app_base_dir()` 逻辑不变

## venv 路径设计

| 路径 | 说明 |
|------|------|
| `%USERPROFILE%\.openguiclaw\venv` | Python venv |
| `%USERPROFILE%\.openguiclaw\npm-global` | npm 全局包（已有） |
| `{安装目录}\` | 项目源码、config、data |

## 依赖变更检测

在 `%USERPROFILE%\.openguiclaw\` 下保存 `requirements.hash` 文件，记录上次安装时 requirements.txt 的 MD5。每次启动比较，不一致则重新 pip install。

## 进度显示方案

使用 tkinter（Python 标准库，launcher 可用）显示一个简单的安装进度窗口：
- "正在初始化环境，请稍候..."
- pip install 输出实时显示
- 完成后自动关闭

## 兼容性

- `python run_gui.py`（开发模式）：完全不变
- `launcher.exe`（生产模式）：通过 subprocess 调用 venv python
- `sys.frozen` 标志：launcher.exe 是 frozen，但 run_gui.py 不是
