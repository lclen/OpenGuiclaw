# 任务列表：venv 环境打包方案

## Task 1: 创建 launcher.py ✅
- [x] 新建 `launcher.py`，实现以下逻辑：
  - 定位 venv 路径（`~/.openguiclaw/venv`）
  - 检测系统 Python 3.10+（找不到则自动安装）
  - 自动安装 Python：winget 优先，失败则从 npmmirror 镜像下载官方安装包，再失败则弹窗提示
  - 创建 venv（如不存在）
  - 比较 requirements.txt hash，决定是否重新 pip install（阿里云镜像）
  - 显示 tkinter 进度窗口（安装依赖时）
  - 用 venv python 以 subprocess 启动 run_gui.py
- [x] 验证：直接运行 `python launcher.py` 能正常启动应用

## Task 2: 修改 build_exe.bat ✅
- [x] PyInstaller 入口改为 `launcher.py`
- [x] 改为 `--onefile` 模式
- [x] 移除所有 `--add-data` 的依赖库打包
- [x] 添加整理发布目录逻辑：将项目源码复制到 `dist\openGuiclaw\`
- [x] 保留 Inno Setup 编译步骤

## Task 3: 修改 installer.iss ✅
- [x] `[Files]` 打包 `dist\openGuiclaw\*`（含启动器 exe + 项目源码）
- [x] 添加 `[Run]` 段：安装完成后可选启动 launcher.exe 触发首次 venv 初始化
- [x] 修改卸载逻辑：分步询问是否删除 venv 和全部用户数据
- [x] 移除不支持的 `AllowDowngrade=yes` 指令

## Task 4: 修改 bootstrap.py ✅
- [x] `check_python_deps()` 移除 frozen 跳过逻辑
- [x] 新增 `_get_venv_python()` 函数，优先使用 venv 内的 pip
- [x] 兼容：launcher 启动（venv python）和开发模式（sys.executable）

## Task 5: 修改 run_gui.py ✅
- [x] 移除 `sys.frozen` 相关的特殊处理（launcher 负责环境准备）
- [x] 简化路径逻辑（统一用 `__file__` 相对路径）
- [x] 确保开发模式（直接 python run_gui.py）行为不变

## Task 6: 端到端测试
- [ ] 全新 Windows 环境测试（无 openGuiclaw 历史）
- [ ] 验证首次启动自动创建 venv 并安装依赖
- [ ] 验证用户手动 pip install 新库后插件可以使用
- [ ] 验证 requirements.txt 更新后下次启动自动重新安装
- [ ] 验证卸载流程
- [ ] 运行 `build_exe.bat` 验证打包成功，launcher.exe < 10MB
