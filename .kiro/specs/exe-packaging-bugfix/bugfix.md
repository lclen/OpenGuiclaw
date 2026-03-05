# Bugfix Requirements Document

## Introduction

本文档描述 openGuiclaw 项目 PyInstaller + Inno Setup 打包流程中发现的四个 bug。这些问题影响打包产物的正确性、安装包体积、npm 依赖检测的可靠性以及打包后程序的启动稳定性。

---

## Bug Analysis

### Current Behavior (Defect)

**Bug 1：data/ 目录被打包进 PyInstaller**

1.1 WHEN `build_exe.bat` 执行 PyInstaller 打包时 THEN 系统将 `data/` 目录（含 sessions、memory、diary、journals、identities、plans、scheduler、screenshots、token_usage.db）通过 `--add-data "data;data"` 打包进可执行文件

1.2 WHEN 打包后的程序运行并尝试向 `data/` 子目录写入数据时 THEN 系统写入 PyInstaller 的 `_MEIPASS` 只读临时目录，导致数据丢失

1.3 WHEN 构建安装包时 THEN 系统将运行时生成的数据目录打包进安装包，导致安装包体积虚增

**Bug 2：scoped npm 包名解析错误**

1.4 WHEN `bootstrap.py` 的 `check_npm_deps()` 处理形如 `@scope/package@1.0.0` 的 scoped 包时 THEN 系统将含版本号的完整字符串（如 `@scope/package@1.0.0`）当作包名进行匹配，导致永远匹配不上已安装的包

1.5 WHEN scoped 包名解析失败时 THEN 系统每次启动都重复执行 npm install，造成不必要的等待

**Bug 3：npm 全局包检测使用 `npm ls` 解析路径字符串不可靠**

1.6 WHEN `bootstrap.py` 检测全局 npm 包是否已安装时 THEN 系统使用 `npm ls -g --depth=0 --parseable` 并解析输出的路径字符串

1.7 WHEN 运行环境为 Windows 且路径包含反斜杠或空格时 THEN 系统路径字符串解析出错，导致已安装的包被误判为未安装

**Bug 4：`run_gui.py` 用 `time.sleep(2)` 硬等待 uvicorn 启动**

1.8 WHEN `run_gui.py` 启动 uvicorn 后调用 `time.sleep(2)` 等待服务就绪时 THEN 系统在低配机器上 2 秒内 uvicorn 可能尚未完成启动

1.9 WHEN uvicorn 未就绪时 webview 已尝试打开页面 THEN 系统显示空白页或连接失败

---

### Expected Behavior (Correct)

**Bug 1 修复**

2.1 WHEN `build_exe.bat` 执行 PyInstaller 打包时 THEN 系统 SHALL 不将 `data/` 目录通过 `--add-data` 打包进可执行文件

2.2 WHEN 打包后的程序首次运行时 THEN 系统 SHALL 在用户数据目录（或程序工作目录）下动态创建所需的 `data/` 子目录（sessions、memory、diary、journals、identities、plans、scheduler、screenshots）

2.3 WHEN 构建安装包时 THEN 系统 SHALL 不包含运行时生成的数据目录，安装包体积正常

**Bug 2 修复**

2.4 WHEN `check_npm_deps()` 处理形如 `@scope/package@1.0.0` 的 scoped 包时 THEN 系统 SHALL 正确解析出包名 `@scope/package`，去除版本号后缀

2.5 WHEN scoped 包已安装时 THEN 系统 SHALL 正确识别并跳过安装，不重复执行 npm install

**Bug 3 修复**

2.6 WHEN 检测全局 npm 包是否已安装时 THEN 系统 SHALL 通过直接扫描 node_modules 目录的方式判断包是否存在，而非解析 `npm ls` 的路径字符串输出

2.7 WHEN 运行环境为 Windows 且路径包含反斜杠或空格时 THEN 系统 SHALL 正确识别已安装的全局 npm 包

**Bug 4 修复**

2.8 WHEN `run_gui.py` 启动 uvicorn 后等待服务就绪时 THEN 系统 SHALL 通过轮询 HTTP 健康检查端点（如 `GET /`）确认服务已启动，而非固定 sleep

2.9 WHEN uvicorn 在超时时间内成功响应时 THEN 系统 SHALL 立即打开 webview，无需等待剩余时间

2.10 WHEN uvicorn 在超时时间内未能响应时 THEN 系统 SHALL 给出明确的启动失败提示

---

### Unchanged Behavior (Regression Prevention)

3.1 WHEN 程序正常运行并读写 `data/sessions/` 下的会话文件时 THEN 系统 SHALL CONTINUE TO 正确持久化和加载会话历史

3.2 WHEN 程序正常运行并读写 `data/memory/` 下的记忆文件时 THEN 系统 SHALL CONTINUE TO 正确存取长期记忆

3.3 WHEN `check_npm_deps()` 处理不含 scope 的普通包名（如 `package@1.0.0`）时 THEN 系统 SHALL CONTINUE TO 正确解析包名并检测安装状态

3.4 WHEN npm 依赖均已安装时 THEN 系统 SHALL CONTINUE TO 跳过安装步骤，正常启动

3.5 WHEN 在高配机器上运行时 THEN 系统 SHALL CONTINUE TO 正常启动 uvicorn 并打开 webview

3.6 WHEN PyInstaller 打包时需要包含静态资源（templates/、static/、PERSONA.md 等）时 THEN 系统 SHALL CONTINUE TO 正确打包这些资源

3.7 WHEN 安装包安装完成后首次运行时 THEN 系统 SHALL CONTINUE TO 正常完成初始化流程并进入可用状态
