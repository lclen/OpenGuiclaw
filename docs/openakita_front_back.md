# OpenAkita 架构调查报告

根据对 `openakita` 项目的分析，它采用的是典型的 **Tauri + React/Vite (前端) + Python (后端)** 的前后端分离架构。

前端（使用 Tauri 打包的桌面程序或纯 Web 端）通过 HTTP API 与跑在本地固定端口（根据配置，默认是 `18900`）上的 Python 后端进行通信。

以下是关于前后端分离以及如何连接到打包后的 EXE 的具体实现细节：

## 1. 前后端通信端口与方式

*   **默认端口**：前端连接后端的默认基础 URL 在 Web 模式下可能是同源（相对路径）或是直接指向 `/api/...`，在 Tauri 桌面模式下，默认连接到 `http://127.0.0.1:18900`。
*   **通信协议**：标准的 HTTP REST API。
*   **核心逻辑所在文件**：`apps/setup-center/src/App.tsx` 中的 `safeFetch` 以及状态刷新机制 `refreshStatus` 等函数。

前端通过不断的轮询（Heartbeat）或发起 API 请求（如 `/api/health`）来确认后端是否存活并获取后端版本。

```typescript
// apps/setup-center/src/App.tsx 节选
const res = await fetch(`${effectiveBase}/api/health`, { signal: AbortSignal.timeout(3000) });
// 有效时，代表后端已连接成功
```

## 2. 前端如何启动并连接后端

在 Tauri 的桌面程序模式下，由于它是入口程序，它需要负责**管理 Python 后端的生命周期**。

### A. 后端启动流程 (Tauri Rust 侧)
Tauri 的 Rust 侧（`apps/setup-center/src-tauri/src/main.rs`）实现了一套完整的进程管理机制：
1.  **扫描当前状态**：在启动时，Rust 代码会扫描是否有已存在的端口占用以及状态文件（PID文件等）。
2.  **确定后端可执行文件**：
    它会尝试寻找两种模式的后端：
    *   **内嵌的 PyInstaller 独立打包后端 (EXE)**：优先查找打包好的后端，例如 Windows 下的 `openakita-server.exe`。
    *   **Venv 原生 Python 后端**：如果不使用独立打包的后端，它会回退到使用之前安装的虚拟环境（`venv`）中的 Python 解释器去运行对应模块。
    ```rust
    // src-tauri/src/main.rs 节选
    fn get_backend_executable(venv_dir: &str) -> (PathBuf, Vec<String>) {
        // 1. 优先: 内嵌的 PyInstaller 打包后端 (如 openakita-server.exe)
        // 2. 降级: venv python（开发模式 / 旧安装）
    }
    ```
3.  **Spawn (衍生) 进程部署**：通过 `std::process::Command` 启动 Python 后端，并将其挂载在后台。
    ```rust
    // src-tauri/src/main.rs 的 openakita_service_start 方法
    let mut cmd = Command::new(&backend_exe);
    // ... 清除可能造成干扰的系统 Python 环境变量以防止崩溃
    // ... 使用 detached 模式启动，隐藏控制台窗口
    let child = cmd.spawn().map_err(|e| format!("spawn openakita serve failed: {e}"))?;
    ```

### B. 如何连接到独立打包的 EXE 后端
Tauri 程序与后端的通信其实不关心后端是源码运行还是 EXE 程序运行。
*   当您通过 PyInstaller（或其他打包工具）将 Python 后端打包为独立 EXE 后，只需让 Tauri 的 `Command::new` 指向该 EXE 文件的路径，并传入对应的启动参数（如 `serve`）即可。
*   `openakita` 就是如此设计的：前端使用标准 Fetch；Tauri 则充当守护进程，负责带参拉起这个打包后的后端 EXE 控制台程序，并隐藏其窗口（`CREATE_NO_WINDOW`）。

## 3. 在当前项目中实现类似的架构

要在目前的 `openGuiclaw` 项目中实现类似机制：

1.  **Python 后端改造为纯 API 服务**：
    *   移除 Jinja2 模板直接渲染的依赖，所有的路由均返回 JSON。
    *   使用 `PyInstaller` 将这个 Flask/FastAPI 核心应用打包为一个独立的 `.exe`。
2.  **前端剥离并支持配置目标地址**：
    *   前端代码（HTML/JS/CSS 或使用现代框架重建）不要硬编码相对路径调用。
    *   增加一个“连接设置”界面，允许用户输入后端的 IP 和端口（例如 `http://127.0.0.1:8010`）。
3.  **开发一个简单的壳（如 Tauri 或 Electron）作为启动器（可选）**：
    *   如果您想提供一个包含所有内容的单一安装包：像 `openakita` 一样，写一个极简的客户端。用户双击客户端后，客户端调用操作系统的 API 偷偷在后台执行打包好的 `backend.exe`。
    *   如果您只需要纯粹的前后端分离：只需提供两份文件，一份是 `backend.exe`（命令行程序挂在 8010），另一份是静态资源文件夹。用户先运行 exe，再在浏览器中打开前端的 `index.html` 并填入 `127.0.0.1:8010` 即可连接。

## 总结

`openakita` 通过 **Tauri 的系统进程管理接口自动在后台启动独立的 PyInstaller 后端 EXE**，而它的界面部分本质上是一个基于 Vite 的纯前端 Web 应用。两者之间通过标准 HTTP 相互解耦，这使得只要遵守 API 契约，无论后端是跑在源码中还是打包成 EXE，前端都可以无缝连接。
