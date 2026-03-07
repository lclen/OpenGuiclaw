# OpenGuiclaw 桌面化集成完成说明

本次更新全面提升了 OpenGuiclaw 的桌面原生体验，实现了沉浸式窗口、系统托盘以及准确的上下文监控。

## 主要改进

### 1. 原生级丝滑沉浸式窗口 (Native DWM Titlebar)
- **拒绝卡顿的底层调用**：放弃了以往在 Windows 上体验极其卡顿的网页内嵌仿制边框（`frameless=True`）。采用底层 `ctypes` 调用 Windows 桌面窗口管理器 (DWM) API 来实现真·原生边框。
- **自定义深色注入**：通过强行注入 `DWMWA_USE_IMMERSIVE_DARK_MODE` 和 `DWMWA_CAPTION_COLOR`内存指令，将 Windows 原生边框的背景色和文字色改写为与软件界面一致的 `#010205` 深邃黑。
- **完美的 120Hz 缩放体验**：由于使用系统原生边框，窗口的拖拽、边缘拉伸、最大/最小化均由系统硬件加速接管，彻底告别粘滞感，实现 120Hz 下最极致流畅的操作手感！

### 2. 系统托盘集成
- **后台运行**：点击窗口关闭按钮时，软件将自动隐藏至右下角系统托盘，保持后台运行。
- **托盘菜单**：右键托盘图标可选择 "显示主窗口" 或 "彻底退程序"。
- **状态通知**：程序启动及状态切换更符合标准桌面软件逻辑。

### 3. 可视化上下文占用 (Context Used)
- **真实数据对接**：前端右下角圆圈现在实时显示来自后端的 `estimated_tokens`，不再是简单的字符估算。
- **动态更新**：在流式输出结束时自动同步最新的 Token 占用情况。

### 4. 依赖项全面审计
- **完善 `requirements.txt`**：补全了 `pystray`, `Pillow`, `requests`, `beautifulsoup4`, `python-docx` 等所有功能模块所需的 Python 库。

## 验证与测试

### 运行方式
确保在 `langchain` 环境下，直接运行：
```powershell
python .\run_gui.py
```

### 预期效果
1. 启动后，窗口顶部会出现深色/主题色的自定义拖拽区。
2. 双击标题栏或点击最大化按钮可切换窗口大小。
3. 点击关闭按钮后，窗口消失，但可以在任务栏右下角找到绿色小图标（托盘图标）。
4. 右键托盘图标点击 "Exit" 即可完全退出。

## 打包为 .exe 建议

如果你希望将程序打包为独立可执行文件，建议使用以下 PyInstaller 命令：

```powershell
pyinstaller --noconfirm --onedir --windowed --name "OpenGuiclaw" --add-data "static;static" --add-data "templates;templates" --add-data "bin-node;bin-node" --add-data "config.json.example;." --icon "static/favicon.ico" --collect-all webview --collect-all pystray run_gui.py
```

> [!NOTE]
> 打包前请确保已安装 `pyinstaller`。打包后的 `dist/OpenGuiclaw` 目录即为完整的绿色版软件。
