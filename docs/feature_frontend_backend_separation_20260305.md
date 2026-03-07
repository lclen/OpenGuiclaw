# openGuiclaw 前后端进程分离与重启加速 (2026-03-05)

## 1. 背景与问题根因

EXE 打包后，原始方案使用 `os.execv` 替换进程来实现"重启"。但该方式在 pywebview 环境下会**连同窗口一起被杀死**，导致整个应用闪退。

根本原因：**后端（uvicorn/FastAPI）与前端（pywebview 窗口）运行在同一 Python 进程中**，无法独立重启其中一方。

---

## 2. 已实施方案：进程级分离（最小化改动）

> 不引入 Tauri / Electron，复用现有 `launcher.py + run_gui.py + pywebview` 技术栈，改动点极少，风险极低。

### 2.1 架构变化

| 模块 | 优化前 | 优化后 |
|---|---|---|
| `run_gui.py` | 在同一进程内以线程启动 uvicorn | 通过 `subprocess.Popen` 拉起**独立后端子进程** |
| `core/server.py` | `os.execv` 重启（EXE 下失败） | `os._exit(0)` 干净退出，由 watchdog 重新拉起 |
| 重启流程 | 进程替换（失效） | 前端 → `/api/system/restart` → 后端退出 → watchdog 重启 |

### 2.2 重启全链路

```
用户点击"应用并重启"
    │
    ▼
前端 fetch POST /api/system/restart
    │ (0.15s 后)
    ▼
后端 os._exit(0)  ← server.py
    │ (0.1s 后)
    ▼
run_gui.py watchdog 检测到子进程退出
    │
    ▼
重新 subprocess.Popen 拉起后端进程
    │
    ▼
前端每 200ms 轮询 /api/health
    │ (后端就绪后)
    ▼
遮罩提示"服务就绪" → 200ms 后 window.location.reload()
```

---

## 3. 重启加速优化（2026-03-05 本次新增）

在进程分离方案基础上，针对三个固定延迟点做了精确优化：

### 3.1 后端退出延迟压缩 — `core/server.py`

```python
# 优化前：等待 1 秒再退出
def _do_restart():
    time.sleep(1)   # ← 白白浪费 1 秒
    os._exit(0)

# 优化后：只需让 HTTP 响应来得及 flush
def _do_restart():
    time.sleep(0.15)  # ← 节省 ~850ms
    os._exit(0)
```

**原理**：HTTP 响应发送到客户端只需要几毫秒，原来的 1 秒等待完全没有必要。

### 3.2 Watchdog 重启间隔压缩 — `run_gui.py`

```python
# 优化前：检测到退出后等 1 秒再重启
logging.info("Backend subsystem exited. Restarting in 1 second...")
time.sleep(1)          # ← 又白白浪费 1 秒

# 优化后：子进程已退就立刻重启
logging.info("Backend subsystem exited. Restarting shortly...")
time.sleep(0.1)        # ← 节省 ~900ms
```

**原理**：watchdog 等待是为了让旧进程资源彻底释放，但进程退出后 OS 会立即回收资源，0.1s 缓冲完全充裕。

### 3.3 前端感知延迟压缩 — `static/js/app-logic.js`

```javascript
// 优化前：每 1 秒轮询一次，平均额外等 ~500ms
const poll = setInterval(async () => { ... }, 1000);

// 优化后：每 200ms 轮询一次，平均额外等 ~100ms
// 同时加入 300ms 的初始等待，确保旧进程已退出后再开始轮询
await new Promise(r => setTimeout(r, 300));
const poll = setInterval(async () => {
    const r = await fetch('/api/health', { cache: 'no-store' });
    if (r.ok) {
        clearInterval(poll);
        // 更新遮罩文字后 200ms 再 reload，避免白屏闪烁
        const statusDiv = modal?.querySelector?.('div[style*="font-size:11px"]');
        if (statusDiv) statusDiv.textContent = '服务就绪，正在加载界面...';
        setTimeout(() => window.location.reload(true), 200);
    }
}, 200);
```

**原理**：轮询间隔越小，从"后端实际就绪"到"前端感知到就绪"之间的空窗期越短。1000ms 间隔平均空窗 500ms，200ms 间隔平均空窗仅 100ms。

---

## 4. 优化效果汇总

| 优化点 | 优化前 | 优化后 | 节省 |
|---|---|---|---|
| 后端退出延迟 | 1000ms | 150ms | **~850ms** |
| Watchdog 重启间隔 | 1000ms | 100ms | **~900ms** |
| 前端轮询间隔（平均感知延迟） | ~500ms | ~100ms | **~400ms** |
| **合计固定节省** | — | — | **约 2.15 秒** |

> **说明**：后端 Agent 初始化（加载记忆库、数据库、向量索引等）的耗时无法通过本方案消除，该部分取决于 `data/` 目录大小。以上优化消除的是**全部不必要的等待时间**，让「后端实际就绪」到「页面完成刷新」之间的间隙最小化。

---

## 5. 改动文件清单

| 文件 | 改动内容 |
|---|---|
| [`core/server.py`](file:///d:/openGuiclaw/core/server.py) | `/api/system/restart` 的 `sleep(1)` → `sleep(0.15)` |
| [`run_gui.py`](file:///d:/openGuiclaw/run_gui.py) | watchdog 的 `sleep(1)` → `sleep(0.1)` |
| [`static/js/app-logic.js`](file:///d:/openGuiclaw/static/js/app-logic.js) | 轮询间隔 1000ms → 200ms；加 300ms 初始等待；更新遮罩状态文字选择器 |
| [`plugins/browser.py`](file:///d:/openGuiclaw/plugins/browser.py) | 增加 `stdin=subprocess.DEVNULL` 和 `CREATE_NO_WINDOW` 保护；优化 `browser_open` 验证逻辑 |
| [`plugins/system.py`](file:///d:/openGuiclaw/plugins/system.py) | 为 `execute_command` 增加 Subprocess 安全加固 |
| [`core/agent.py`](file:///d:/openGuiclaw/core/agent.py) | 为远程技能动态执行增加 Subprocess 安全加固 |

---

## 6. EXE 环境兼容性修复 (Subprocess 挂起)

在 PyInstaller 打包的 `--noconsole` (EXE) 环境下，子进程可能会因为缺失有效的 `stdin` 句柄而导致死锁挂起。

### 6.1 修复原理
为所有底层 `subprocess` 调用强制注入以下配置：
- `stdin=subprocess.DEVNULL`：硬性切断输入读取，防止子进程等待控制台输入导致主线程死锁。
- `creationflags=subprocess.CREATE_NO_WINDOW`：防止在 GUI 环境下弹出黑色 CMD 窗口，提升系统兼容性。

### 6.2 受益插件
- **Browser Plugin**: 彻底解决了 `browser_open` 命令在 EXE 下偶发超时（45秒）的 Bug。
- **System Plugin**: 确保 AI 执行 `pip`, `npm`, `git` 等命令时拥有极致的鲁棒性。

---

## 7. 调试效率提升

前后端进程分离后，开发者的调试流程得到了极大简化：

1. **无需反复打包**：由于 `run_gui.py` 运行时前端（pywebview）和后端（uvicorn）已经解耦，大部分修改（`core/`, `static/`, `templates/`）只需运行 `python run_gui.py` 即可。
2. **热重启后端**：在 UI 界面点击“应用并重启”时，**只会重启后端子进程**，前端窗口保持不动。这意味着你可以立刻看到逻辑修改的效果，而不需要重新打开 GUI 窗口。
3. **独立后端测试**：你可以通过常规浏览器直接访问 `http://127.0.0.1:8011` 来调试前端代码，利用 Chrome/Edge 的原生 F12 工具（比 pywebview 的调试器更强大）。

---

## 8. 关于 IDE 中的 Pyre2 静态检查错误

在 VS Code 中可能看到大量 `Could not find import of 'openai'` 等 Pyre2 报错，这些**均为误报**。

**原因**：Pyre2 静态分析器不知道项目使用的是 `d:\miniconda3\envs\langchain\` 这个 Conda 环境，导致找不到已安装的包。  
**验证**：`pip show openai` 可确认已安装（`openai==2.16.0`），且代码通过了 `python -m py_compile` 编译验证。

修复方式（可选）：在项目根目录添加 `.pyre_configuration`，指定 `site_package_search_strategy` 或切换到 Pylance 作为语言服务器。

---

*功能实现日期：2026-03-05*  
*文档编写日期：2026-03-05*
