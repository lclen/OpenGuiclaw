# OpenGuiclaw EXE 打包指南

## 概述

本文档说明如何将 OpenGuiclaw 项目打包为 Windows 可执行文件（.exe）以及生成安装包的完整流程。

## 前置要求

### 必需工具

1. **Python 3.10+**
   - 项目依赖已通过 `requirements.txt` 安装

2. **PyInstaller**
   - 打包脚本会自动安装
   - 或手动安装：`pip install pyinstaller`

3. **Inno Setup**（可选，用于生成安装包）
   - 下载地址：https://jrsoftware.org/isdl.php
   - 安装后确保 `iscc.exe` 在系统 PATH 中

### 版本号文件

在项目根目录创建 `VERSION` 文件，内容为版本号（如 `1.0.0`）

```
1.0.0
```

## 打包流程

### 1. 首次打包

```bash
# 在项目根目录执行
build_exe.bat
```

脚本会自动执行以下步骤：

1. 读取 `VERSION` 文件获取版本号
2. 安装 PyInstaller（如果未安装）
3. 清理旧的构建文件（`build/` 和 `dist/`）
4. 执行 PyInstaller 打包
5. 如果检测到 Inno Setup，自动生成安装包

### 2. 代码修改后重新打包

修改代码后，可以直接重新运行打包脚本：

```bash
build_exe.bat
```

脚本会自动清理旧构建并重新打包最新代码。

### 3. 推荐工作流程

```bash
# 1. 修改代码
# 2. 在开发环境测试
uv run uvicorn core.server:app --host 127.0.0.1 --port 8080

# 3. 更新版本号（如果需要）
echo 1.0.1 > VERSION

# 4. 重新打包
.\build_exe.bat

# 5. 测试打包后的程序
cd dist\openGuiclaw
openGuiclaw.exe
```

## 输出文件

### 打包后的程序

- **位置**：`dist/openGuiclaw/`
- **主程序**：`openGuiclaw.exe`
- **包含内容**：
  - 所有 Python 依赖库
  - `templates/` 模板文件
  - `static/` 静态资源（不含大体积 VRM 模型）
  - `plugins/` 和 `skills/` 模块
  - `bin-node/` Node.js 运行时
  - `config.json.example` 配置模板
  - `PERSONA.md` 默认人设

### 安装包

- **位置**：`output/openGuiclaw_Setup_<版本号>.exe`
- **功能**：
  - 自动安装到 `Program Files`
  - 创建桌面快捷方式（可选）
  - 添加到系统 PATH（可选）
  - 支持覆盖安装和卸载

## 打包配置说明

### PyInstaller 参数

```bat
pyinstaller --noconfirm --onedir --windowed ^
  --icon="static/favicon.ico" ^
  --hidden-import="skills.autogui" ^
  --hidden-import="skills.basic" ^
  ... （其他模块）
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data "plugins;plugins" ^
  --add-data "skills;skills" ^
  --add-data "core;core" ^
  --add-data "bin-node;bin-node" ^
  --add-data "config.json.example;." ^
  --add-data "PERSONA.md;." ^
  --name "openGuiclaw" ^
  run_gui.py
```

### 不打包的内容

以下内容不会被打包，会在首次运行时自动创建：

- `data/` 目录（运行时数据）
  - `sessions/` 会话历史
  - `memory/` 长期记忆
  - `diary/` AI 日记
  - `journals/` 对话日志
  - `identities/` 自定义人设
  - `plans/` 计划任务
  - `scheduler/` 定时任务
  - `screenshots/` 临时截图
  - `consolidation/` 记忆整合
  - `token_usage.db` Token 统计数据库

- `config.json` 配置文件
  - 首次运行时从 `config.json.example` 自动复制
  - 用户需手动填写 API Key

### VRM 模型文件策略

- **内置模型**：只有 `Avatar Sample B.vrm`（约 15MB）会被打包
- **大体积模型**：`static/models/` 下的其他 VRM 文件不打包
- **用户自定义**：用户可在安装后手动放置 VRM 模型到安装目录的 `static/models/` 下

## 新增模块时的注意事项

### 新增 Python 模块

如果在 `skills/` 或 `plugins/` 下新增模块，需要在 `build_exe.bat` 中添加 `--hidden-import` 参数：

```bat
--hidden-import="skills.new_module" ^
--hidden-import="plugins.new_plugin" ^
```

### 新增资源文件夹

如果新增需要打包的资源目录，添加 `--add-data` 参数：

```bat
--add-data "new_folder;new_folder" ^
```

注意：Windows 下使用分号 `;` 分隔源路径和目标路径。

### 新增依赖

- **Python 依赖**：更新 `requirements.txt` 后，在开发环境先安装测试
- **npm 依赖**：更新 `npm-requirements.txt` 后，bootstrap 会自动处理

## 常见问题

### 1. 打包后程序无法启动

**可能原因**：
- 缺少 `--hidden-import` 导致某些模块未被打包
- 路径问题（应使用 `APP_BASE_DIR` 绝对路径）

**解决方法**：
- 检查 `build/openGuiclaw/warn-openGuiclaw.txt` 查看警告信息
- 添加缺失模块的 `--hidden-import` 参数

### 2. 静态资源 404

**可能原因**：
- `server.py` 中使用了相对路径
- `static/` 目录未正确打包

**解决方法**：
- 确保 `server.py` 使用 `APP_BASE_DIR` 构建绝对路径
- 检查 `--add-data "static;static"` 参数存在

### 3. 首次运行提示配置文件不存在

**正常行为**：
- `bootstrap.py` 会自动从 `config.json.example` 复制生成 `config.json`
- 用户需手动编辑填写 API Key

### 4. Inno Setup 未找到

**提示信息**：
```
[跳过] 未找到 iscc，请手动运行 Inno Setup 编译 installer.iss
```

**解决方法**：
- 安装 Inno Setup 并将其添加到系统 PATH
- 或手动运行：`iscc /DAppVersion=1.0.0 installer.iss`

## 安装包功能

### 安装选项

1. **创建桌面快捷方式**
   - 在桌面创建 `openGuiclaw` 快捷方式

2. **添加到 PATH**
   - 将安装目录添加到用户环境变量
   - 可在命令行全局调用 `openGuiclaw.exe`

### 升级安装

- 支持覆盖安装同版本（修复/重装场景）
- 检测到旧版本时会提示是否先卸载
- 用户数据（`data/` 目录）不会被删除

### 卸载

卸载时会询问：
- 是否删除配置数据和会话历史（`~/.openguiclaw`）
- 自动从环境变量中移除安装路径

## 版本管理

### 更新版本号

编辑 `VERSION` 文件：

```
1.0.1
```

### 版本号规范

建议使用语义化版本号（Semantic Versioning）：

- **主版本号**：不兼容的 API 修改
- **次版本号**：向下兼容的功能性新增
- **修订号**：向下兼容的问题修正

示例：`1.2.3`

## 文档更新记录

- **创建时间**：2026-03-05
- **最后更新**：2026-03-05
- **适用版本**：1.0.0+
