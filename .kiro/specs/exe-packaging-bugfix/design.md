# exe-packaging-bugfix 修复设计文档

## Overview

本文档覆盖 openGuiclaw PyInstaller 打包流程中发现的 8 个 bug。这些问题分为三类：
- **打包配置错误**（Bug 1、8）：`build_exe.bat` 打包了不该打包的目录，或打包策略需要确认
- **路径解析错误**（Bug 2、3、6）：npm 包名解析、全局包检测、frozen 后相对路径失效
- **运行时初始化缺失**（Bug 4、5、7）：硬等待启动、data 子目录未创建、config.json 不存在

修复策略：以 `bootstrap.py` 为核心改动点，集中处理所有运行时初始化逻辑；`server.py` 统一切换为基于 `APP_BASE_DIR` 的绝对路径；`run_gui.py` 改为健康检查轮询；`build_exe.bat` 移除 `data/` 打包并确认静态资源策略。

---

## Glossary

- **Bug_Condition (C)**：触发 bug 的输入条件集合
- **Property (P)**：对满足 C(X) 的输入，修复后函数应产生的正确行为
- **Preservation**：对不满足 C(X) 的输入，修复前后行为必须完全一致
- **frozen**：`getattr(sys, "frozen", False)` 为 True，即 PyInstaller 打包后运行状态
- **APP_BASE_DIR**：程序运行时的"家目录"——frozen 时为 exe 所在目录，开发时为项目根目录
- **_MEIPASS**：PyInstaller 解压只读临时目录，frozen 时 `sys._MEIPASS` 指向此处
- **scoped 包**：npm 包名以 `@scope/` 开头，如 `@pixiv/three-vrm`
- **bootstrap.run()**：`run_gui.py` 和 `server.py` 启动时调用的统一初始化入口

---

## Bug Details

### Bug 1：data/ 目录被打包进 PyInstaller

**Fault Condition**

`build_exe.bat` 中存在 `--add-data "data;data"` 参数，导致运行时数据目录被嵌入只读的 `_MEIPASS` 临时目录。

```
FUNCTION isBugCondition_1(build_config)
  INPUT: build_config — build_exe.bat 的 PyInstaller 参数列表
  OUTPUT: boolean

  RETURN "--add-data \"data;data\"" IN build_config
END FUNCTION
```

**Examples**

- 打包时 `data/sessions/` 含历史会话 → 安装包体积虚增，且用户数据被覆盖
- frozen 后写 `data/memory/` → 实际写入 `_MEIPASS/data/memory/`（只读），抛 PermissionError
- 安装包含 `data/token_usage.db` → 用户 token 统计从打包时的旧数据开始，而非空库

---

### Bug 2：scoped npm 包名解析错误

**Fault Condition**

`check_npm_deps()` 对 scoped 包（`@scope/pkg@ver`）的版本号剥离逻辑有误：

```
FUNCTION isBugCondition_2(pkg_string)
  INPUT: pkg_string — npm-requirements.txt 中的一行，如 "@scope/package@1.0.0"
  OUTPUT: boolean

  IF pkg_string STARTS_WITH "@" THEN
    -- 当前代码：pkg_name = pkg_string（未剥离版本号）
    -- 正确逻辑：pkg_name = "@scope/package"（剥离 @ver 后缀）
    RETURN current_code_does_NOT_strip_version(pkg_string)
  END IF
  RETURN false
END FUNCTION
```

**Examples**

- `@pixiv/three-vrm@2.1.0` → 当前解析为 `@pixiv/three-vrm@2.1.0`，与已安装的 `three-vrm` 目录名不匹配 → 每次启动都重装
- `agent-browser@0.16.3` → 正确解析为 `agent-browser`（不受此 bug 影响）
- `@scope/pkg`（无版本号）→ 正确解析为 `@scope/pkg`（不受此 bug 影响）

---

### Bug 3：npm 全局包检测用路径字符串解析不可靠

**Fault Condition**

`npm ls -g --depth=0 --parseable` 在 Windows 上输出反斜杠路径，当路径含空格时 `.split("/")[-1]` 取到的是路径片段而非包名。

```
FUNCTION isBugCondition_3(env)
  INPUT: env — 运行环境描述
  OUTPUT: boolean

  RETURN env.os == "Windows"
         AND env.npm_global_path CONTAINS " "  -- 如 "C:\Program Files\..."
         AND detection_method == "parse_npm_ls_output"
END FUNCTION
```

**Examples**

- npm global 路径为 `C:\Users\My Name\.openGuiclaw\npm-global\node_modules\agent-browser`
  → `split("/")[-1]` 在反斜杠路径上取到 `C:\Users\My Name\.openGuiclaw\npm-global\node_modules\agent-browser`（整行）→ 匹配失败
- 路径无空格时偶然正确，但仍依赖字符串解析，不稳定

---

### Bug 4：run_gui.py 用 time.sleep(2) 硬等待 uvicorn

**Fault Condition**

```
FUNCTION isBugCondition_4(machine)
  INPUT: machine — 运行机器的性能描述
  OUTPUT: boolean

  RETURN machine.startup_time_seconds > 2
         OR machine.is_low_end == true
END FUNCTION
```

**Examples**

- 低配机器（HDD + 4GB RAM）uvicorn 启动需 4 秒 → webview 在 2 秒时打开空白页
- 高配机器 0.5 秒启动 → 浪费 1.5 秒无谓等待
- uvicorn 因端口冲突启动失败 → sleep 结束后 webview 打开连接拒绝页，无错误提示

---

### Bug 5：data/ 子目录不完整，bootstrap 未创建所有必要目录

**Fault Condition**

`_system_daily_selfcheck` 只检查 5 个目录（`data`, `data/sessions`, `data/memory`, `data/scheduler`, `data/diary`），漏掉 `journals/`, `identities/`, `identity/`, `plans/`, `consolidation/`。`bootstrap.run()` 完全没有创建 data 子目录的逻辑。

```
FUNCTION isBugCondition_5(runtime_state)
  INPUT: runtime_state — 程序首次运行时的文件系统状态
  OUTPUT: boolean

  missing_dirs = REQUIRED_DATA_DIRS - EXISTING_DIRS(runtime_state)
  RETURN len(missing_dirs) > 0
         AND bootstrap_does_NOT_create_dirs == true
END FUNCTION
```

**Examples**

- 首次运行，`data/journals/` 不存在 → `journal.py` 写日志时抛 FileNotFoundError
- `data/consolidation/` 不存在 → `daily_consolidator.py` 失败
- `data/identity/` 不存在 → identity_manager 读写失败

---

### Bug 6：server.py 全部使用相对路径，frozen 后 CWD 不确定

**Fault Condition**

```
FUNCTION isBugCondition_6(runtime_state)
  INPUT: runtime_state — 程序运行时状态
  OUTPUT: boolean

  RETURN getattr(sys, "frozen", False) == true
         AND os.getcwd() != exe_parent_directory
         AND server_uses_relative_paths == true
END FUNCTION
```

**Examples**

- frozen 后 CWD 可能是 `_MEIPASS` 或用户桌面 → `StaticFiles(directory="static")` 找不到文件 → 404
- `Agent(config_path="config.json")` → 读取 `_MEIPASS/config.json`（不存在）→ FileNotFoundError
- `PluginManager(plugins_dir="plugins")` → 找不到插件目录 → 所有插件加载失败
- `os.makedirs("data/screenshots")` → 在 `_MEIPASS` 下创建（只读）→ PermissionError

---

### Bug 7：config.json 首次运行不存在

**Fault Condition**

```
FUNCTION isBugCondition_7(runtime_state)
  INPUT: runtime_state — 程序运行时文件系统状态
  OUTPUT: boolean

  RETURN NOT EXISTS(APP_BASE_DIR / "config.json")
         AND EXISTS(APP_BASE_DIR / "config.json.example")
END FUNCTION
```

**Examples**

- 安装后首次运行 → `config.json` 不存在 → `Agent(config_path="config.json")` 抛 FileNotFoundError → 程序崩溃
- 用户删除 `config.json` 后重启 → 同上，应自动从 example 恢复

---

### Bug 8：static/vrm/ 子目录打包策略需确认

**Fault Condition**

`--add-data "static;static"` 在 Windows PyInstaller 中使用分号分隔，语义为"将 static 目录递归打包到输出的 static 目录"，理论上能包含 `vrm/` 子目录。但 `static/models/` 下的 VRM 模型文件（通常 50-200MB/个）若被打包会导致安装包体积爆炸。

```
FUNCTION isBugCondition_8(build_config)
  INPUT: build_config — build_exe.bat 配置
  OUTPUT: boolean

  RETURN static_models_dir_size > THRESHOLD_MB
         AND "--add-data \"static;static\"" IN build_config
         AND no_exclusion_for_models == true
END FUNCTION
```

**Examples**

- `static/models/` 含 3 个 VRM 文件共 300MB → 安装包从 ~50MB 膨胀到 ~350MB
- `static/vrm/animation/` 含动画文件 → 同样问题
- `static/libs/` 含 Three.js 等前端库（通常 < 5MB）→ 应该打包，无问题


---

## Expected Behavior

### Preservation Requirements

**不得改变的行为：**
- 开发模式（非 frozen）下，所有路径解析行为与修复前完全一致
- 普通 npm 包名（非 scoped）的解析和检测逻辑不变（Requirements 3.3、3.4）
- `templates/`、`static/js/`、`static/libs/`、`plugins/`、`skills/` 等只读资源仍正确打包（Requirements 3.6）
- 安装包安装完成后首次运行能正常初始化（Requirements 3.7）
- 程序正常运行时 `data/sessions/`、`data/memory/` 读写行为不变（Requirements 3.1、3.2）
- 高配机器上 uvicorn 快速启动后 webview 正常打开（Requirements 3.5）

**Scope：**
所有不涉及 frozen 状态路径解析、npm scoped 包、data 目录初始化的代码路径，修复后行为完全不变。

---

## Hypothesized Root Cause

**Bug 1**：`build_exe.bat` 最初是从模板复制的，`--add-data "data;data"` 是为了方便开发时测试而加入，后来忘记移除。

**Bug 2**：`check_npm_deps()` 中对 scoped 包的特判逻辑写反了：
```python
# 当前（错误）
pkg_name = pkg.split("@")[0] if not pkg.startswith("@") else pkg
#                                                              ^^^^ 保留了完整字符串含版本号
# 正确
pkg_name = pkg if not pkg.startswith("@") else "@" + pkg[1:].split("@")[0]
```

**Bug 3**：`npm ls --parseable` 输出的是完整文件系统路径，在 Windows 上是反斜杠。当前代码先 `replace("\\", "/")` 再 `split("/")[-1]`，理论上能取到最后一段。但 npm global 路径末尾是 `node_modules/<pkg-name>`，取 `[-1]` 应该是包名。实际问题在于：scoped 包的目录结构是 `node_modules/@scope/pkg`，`split("/")[-1]` 只取到 `pkg`，丢失了 `@scope/` 前缀，导致 `@scope/pkg` 永远匹配不上。更可靠的方案是直接扫描 `node_modules` 目录。

**Bug 4**：`time.sleep(2)` 是经验值，没有实际检测服务是否就绪。

**Bug 5**：`_system_daily_selfcheck` 的目录列表是手动维护的，随着项目增加新目录时没有同步更新。`bootstrap.run()` 设计时只关注依赖安装，没有考虑数据目录初始化。

**Bug 6**：`server.py` 作为 FastAPI 应用，开发时通过 `uvicorn core.server:app` 从项目根目录启动，CWD 始终是项目根，相对路径工作正常。打包后没有人测试过 frozen 状态下的路径行为。

**Bug 7**：`config.json` 在 `.gitignore` 中，打包时只有 `config.json.example`，没有自动复制的逻辑。

**Bug 8**：`--add-data "static;static"` 确实能递归包含 `vrm/` 子目录，语法本身没有问题。真正的风险是 `static/models/` 下的大体积 VRM 模型文件被无意识地打包进安装包。

---

## Correctness Properties

Property 1: Fault Condition - data/ 不被打包，运行时动态创建

_For any_ frozen 状态下的首次运行，bootstrap 的 `ensure_data_dirs()` SHALL 在 `APP_BASE_DIR/data/` 下创建所有必要子目录，且这些目录对程序可写。

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Fault Condition - scoped npm 包名正确解析

_For any_ npm 包字符串 `pkg_string`，`_parse_pkg_name(pkg_string)` SHALL 返回不含版本号的完整包名（含 `@scope/` 前缀）。

**Validates: Requirements 2.4, 2.5**

Property 3: Fault Condition - npm 全局包检测通过目录扫描

_For any_ 运行环境（含路径有空格的 Windows），`_is_npm_pkg_installed(pkg_name)` SHALL 通过扫描 `node_modules` 目录正确判断包是否已安装。

**Validates: Requirements 2.6, 2.7**

Property 4: Fault Condition - uvicorn 就绪后才打开 webview

_For any_ 机器性能，`run_gui.py` SHALL 在 `/api/health` 返回 200 后才调用 `webview.create_window()`，超时（30 秒）时给出明确错误提示。

**Validates: Requirements 2.8, 2.9, 2.10**

Property 5: Fault Condition - 所有必要 data 子目录在启动时存在

_For any_ 首次运行状态，`ensure_data_dirs()` 执行后，所有必要子目录 SHALL 存在且可写。

**Validates: Requirements 2.2**

Property 6: Fault Condition - server.py 使用绝对路径

_For any_ frozen 状态，`server.py` 中所有文件系统操作 SHALL 基于 `APP_BASE_DIR` 的绝对路径，不依赖 CWD。

**Validates: Requirements 2.2, 3.6, 3.7**

Property 7: Fault Condition - config.json 首次运行自动创建

_For any_ `config.json` 不存在的运行状态，`ensure_config()` SHALL 从 `config.json.example` 复制生成 `config.json`，程序正常启动。

**Validates: Requirements 3.7**

Property 8: Preservation - 非 frozen 开发模式行为不变

_For any_ 非 frozen 运行状态（`sys.frozen` 为 False），所有修改后的函数 SHALL 产生与修复前完全相同的行为。

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**


---

## Fix Implementation

### 修改文件清单

#### 1. build_exe.bat

**具体修改：**

1. **移除 `--add-data "data;data"`**：data 目录由 bootstrap 在运行时创建，不打包。

2. **VRM 模型文件策略**：`static/models/` 下的 `.vrm` 文件通常 50-200MB/个，不应打包进安装包。推荐策略：
   - 将 `static/models/` 加入 `.gitignore` 和打包排除列表
   - 用户首次运行后手动放置或通过应用内"模型商店"下载
   - `build_exe.bat` 改为只打包 `static` 下除 `models/` 之外的内容

3. **static 子目录打包**：`--add-data "static;static"` 在 Windows PyInstaller 中使用分号，能递归包含所有子目录（含 `vrm/`），语法正确，无需修改。

```bat
:: 移除这一行
:: --add-data "data;data" ^

:: 新增：排除大体积模型文件，单独打包 static 的其他部分
:: 方案A（推荐）：整体打包 static，但在文档中说明 models/ 应在安装后手动放置
--add-data "static;static" ^
:: 方案B：如果 models/ 确实为空或很小，保持现状即可
```

---

#### 2. core/bootstrap.py — 主要改动

**新增 `get_app_base_dir()` 函数：**

```python
def get_app_base_dir() -> Path:
    """
    返回程序的"家目录"：
    - frozen（PyInstaller）：exe 所在目录（可写）
    - 开发模式：项目根目录（bootstrap.py 的上两级）
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent
```

**修改 `setup_node_env()`，增加 APP_BASE_DIR 环境变量：**

```python
def setup_node_env() -> None:
    app_base = get_app_base_dir()
    os.environ["APP_BASE_DIR"] = str(app_base)

    # frozen 时 bin-node 在 _MEIPASS 里（只读资源），开发时在项目根
    if getattr(sys, "frozen", False):
        node_bin = Path(sys._MEIPASS) / "bin-node"
    else:
        node_bin = app_base / "bin-node"

    if node_bin.exists():
        os.environ["PATH"] = f"{node_bin}{os.pathsep}{os.environ.get('PATH', '')}"

    # 其余 npm global 隔离逻辑不变...
```

**新增 `ensure_data_dirs()` 函数：**

```python
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

def ensure_data_dirs() -> None:
    """在 APP_BASE_DIR 下创建所有必要的 data 子目录。"""
    base = get_app_base_dir()
    for rel in _REQUIRED_DATA_DIRS:
        target = base / rel
        target.mkdir(parents=True, exist_ok=True)
    print("[Bootstrap] [OK] data 子目录已就绪")
```

**新增 `ensure_config()` 函数：**

```python
def ensure_config() -> None:
    """config.json 不存在时，从 config.json.example 自动复制。"""
    base = get_app_base_dir()
    config = base / "config.json"
    example = base / "config.json.example"

    if config.exists():
        return

    if example.exists():
        import shutil
        shutil.copy2(example, config)
        print("[Bootstrap] [OK] 已从 config.json.example 创建 config.json，请填写 API Key")
    else:
        print("[Bootstrap] [WARN] config.json 和 config.json.example 均不存在，请手动创建配置文件")
```

**修复 `check_npm_deps()` 中的两处 bug：**

```python
def _parse_pkg_name(pkg: str) -> str:
    """从 'pkg@ver' 或 '@scope/pkg@ver' 中提取包名。"""
    if pkg.startswith("@"):
        # scoped: "@scope/pkg@ver" → "@scope/pkg"
        rest = pkg[1:]  # "scope/pkg@ver"
        name_part = rest.split("@")[0]  # "scope/pkg"
        return "@" + name_part
    else:
        return pkg.split("@")[0]

def _is_npm_pkg_installed(pkg_name: str, npm_global_prefix: str) -> bool:
    """通过扫描 node_modules 目录判断包是否已安装（替代 npm ls 解析）。"""
    node_modules = Path(npm_global_prefix) / "node_modules"
    if not node_modules.exists():
        return False

    if pkg_name.startswith("@"):
        # scoped: "@scope/pkg" → node_modules/@scope/pkg/
        scope, name = pkg_name[1:].split("/", 1)
        return (node_modules / f"@{scope}" / name).is_dir()
    else:
        return (node_modules / pkg_name).is_dir()
```

**修改 `run()` 调用顺序：**

```python
def run(skip_python=False, skip_npm=False) -> None:
    global _already_run
    if _already_run:
        return
    _already_run = True

    setup_node_env()       # 1. 设置 APP_BASE_DIR 和 PATH
    ensure_data_dirs()     # 2. 创建 data 子目录
    ensure_config()        # 3. 确保 config.json 存在
    print_environment_diagnostics()

    if not skip_python:
        check_python_deps()
    if not skip_npm:
        check_npm_deps()
```

---

#### 3. run_gui.py — 轮询替代 sleep

```python
import httpx  # 已在 requirements.txt 中

def wait_for_server(port: int, timeout: float = 30.0, interval: float = 0.5) -> bool:
    """轮询 /api/health，返回 True 表示服务就绪，False 表示超时。"""
    url = f"http://127.0.0.1:{port}/api/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=1.0)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False

# 替换原来的 time.sleep(2)
if not wait_for_server(port):
    import tkinter.messagebox as mb
    mb.showerror("启动失败", f"OpenGuiclaw 服务在 30 秒内未能启动，请检查日志。")
    os._exit(1)
```

---

#### 4. server.py — 统一使用绝对路径

在文件顶部（import 之后，app 定义之前）添加：

```python
# 从 bootstrap 获取 APP_BASE_DIR（bootstrap.run() 已在 run_gui.py 中提前调用）
_APP_BASE = Path(os.environ.get("APP_BASE_DIR", Path(__file__).resolve().parent.parent))
```

替换所有相对路径：

```python
# lifespan 内
config_path = str(_APP_BASE / "config.json")
agent = Agent(config_path=config_path, data_dir=str(_APP_BASE / "data"), auto_evolve=True)
plugin_manager = PluginManager(skill_manager=agent.skills, plugins_dir=str(_APP_BASE / "plugins"))

# app 挂载（模块级）
os.makedirs(_APP_BASE / "static", exist_ok=True)
os.makedirs(_APP_BASE / "templates", exist_ok=True)
os.makedirs(_APP_BASE / "data" / "screenshots", exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_APP_BASE / "static")), name="static")
app.mount("/screenshots", StaticFiles(directory=str(_APP_BASE / "data" / "screenshots")), name="screenshots")
templates = Jinja2Templates(directory=str(_APP_BASE / "templates"))

# _system_daily_selfcheck 内的目录检查
required_dirs = [str(_APP_BASE / d) for d in [
    "data", "data/sessions", "data/memory", "data/scheduler",
    "data/diary", "data/journals", "data/identities", "data/identity",
    "data/plans", "data/consolidation"
]]

# save_preferences 内
os.makedirs(_APP_BASE / "data", exist_ok=True)
```


---

## Testing Strategy

### Validation Approach

测试分两阶段：先在未修复代码上运行探索性测试，确认 bug 可复现并理解根因；再在修复后运行 fix checking 和 preservation checking。

---

### Exploratory Fault Condition Checking

**Goal**：在未修复代码上复现 bug，确认根因分析正确。

**Test Cases**：

1. **Bug 2 探索**：构造 `pkg = "@pixiv/three-vrm@2.1.0"`，调用当前 `check_npm_deps()` 中的解析逻辑，断言 `pkg_name == "@pixiv/three-vrm"`（将失败，实际返回 `"@pixiv/three-vrm@2.1.0"`）

2. **Bug 3 探索**：在 Windows 上，npm global prefix 含空格，调用当前 `check_npm_deps()` 检测已安装的 scoped 包，断言返回"已安装"（将失败，实际触发重装）

3. **Bug 4 探索**：在慢速机器上，启动 uvicorn 后立即（< 2 秒）请求 `/api/health`，断言返回 200（将失败，连接被拒绝）

4. **Bug 6 探索**：在 frozen 模拟环境中（设置 `sys.frozen = True`，CWD 改为临时目录），导入 `server.py`，断言 `StaticFiles` 挂载不抛异常（将失败）

**Expected Counterexamples**：
- `_parse_pkg_name("@pixiv/three-vrm@2.1.0")` 返回 `"@pixiv/three-vrm@2.1.0"` 而非 `"@pixiv/three-vrm"`
- `_is_npm_pkg_installed` 在含空格路径下返回 False（即使包已安装）
- `time.sleep(2)` 后 webview 打开空白页

---

### Fix Checking

**Goal**：验证对所有满足 bug 条件的输入，修复后函数产生正确行为。

```
FOR ALL pkg_string WHERE isBugCondition_2(pkg_string) DO
  result := _parse_pkg_name(pkg_string)
  ASSERT result == expected_pkg_name_without_version(pkg_string)
END FOR

FOR ALL env WHERE isBugCondition_3(env) DO
  result := _is_npm_pkg_installed(pkg_name, npm_global_prefix)
  ASSERT result == actual_directory_exists(pkg_name, npm_global_prefix)
END FOR

FOR ALL machine WHERE isBugCondition_4(machine) DO
  wait_for_server(port)
  ASSERT webview_opens_AFTER_health_check_returns_200
END FOR

FOR ALL runtime WHERE isBugCondition_5(runtime) DO
  ensure_data_dirs()
  FOR ALL dir IN REQUIRED_DATA_DIRS DO
    ASSERT os.path.isdir(APP_BASE_DIR / dir)
    ASSERT os.access(APP_BASE_DIR / dir, os.W_OK)
  END FOR
END FOR
```

---

### Preservation Checking

**Goal**：验证对不满足 bug 条件的输入，修复前后行为完全一致。

```
FOR ALL pkg_string WHERE NOT isBugCondition_2(pkg_string) DO
  -- 普通包名（非 scoped）
  ASSERT _parse_pkg_name_fixed(pkg_string) == _parse_pkg_name_original(pkg_string)
END FOR

FOR ALL runtime WHERE NOT getattr(sys, "frozen", False) DO
  -- 开发模式：所有路径解析结果不变
  ASSERT server_paths_fixed == server_paths_original
END FOR
```

**Testing Approach**：对 `_parse_pkg_name` 使用 property-based testing，生成大量随机普通包名字符串，验证修复前后结果一致。

---

### Unit Tests

- `test_parse_pkg_name_scoped`：`"@pixiv/three-vrm@2.1.0"` → `"@pixiv/three-vrm"`
- `test_parse_pkg_name_scoped_no_version`：`"@scope/pkg"` → `"@scope/pkg"`
- `test_parse_pkg_name_plain`：`"agent-browser@0.16.3"` → `"agent-browser"`
- `test_parse_pkg_name_plain_no_version`：`"agent-browser"` → `"agent-browser"`
- `test_is_npm_pkg_installed_scoped`：创建临时 `node_modules/@scope/pkg/` 目录，断言返回 True
- `test_is_npm_pkg_installed_missing`：不创建目录，断言返回 False
- `test_ensure_data_dirs`：在临时目录下调用，断言所有子目录存在且可写
- `test_ensure_config_copies_example`：只有 example 存在时，断言 config.json 被创建
- `test_ensure_config_no_overwrite`：config.json 已存在时，断言内容不被覆盖
- `test_get_app_base_dir_frozen`：mock `sys.frozen = True`，断言返回 exe 父目录
- `test_get_app_base_dir_dev`：非 frozen，断言返回项目根目录
- `test_wait_for_server_success`：mock httpx 返回 200，断言返回 True
- `test_wait_for_server_timeout`：mock httpx 始终失败，断言 30 秒后返回 False

### Property-Based Tests

- **Property 2 preservation**：生成随机非 scoped 包名字符串（不以 `@` 开头），验证 `_parse_pkg_name` 修复前后结果相同
- **Property 5 idempotency**：多次调用 `ensure_data_dirs()`，验证结果幂等（目录存在且无异常）
- **Property 6 path resolution**：生成随机 `APP_BASE_DIR` 路径，验证 `_APP_BASE / "data"` 始终是绝对路径

### Integration Tests

- **frozen 模拟启动测试**：设置 `APP_BASE_DIR` 环境变量指向临时目录，启动 `server.py`，验证 `/static/` 和 `/` 路由正常响应
- **首次运行完整流程**：在空临时目录下运行 `bootstrap.run()`，验证 data 子目录和 config.json 均被创建
- **npm 依赖检测集成**：在实际 npm 环境中，安装一个 scoped 包后调用 `check_npm_deps()`，验证不触发重装

---

## Regression Prevention

| 修改点 | 回归风险 | 防护措施 |
|--------|----------|----------|
| `setup_node_env()` 增加 `APP_BASE_DIR` | 开发模式路径变化 | 单测验证非 frozen 时返回项目根 |
| `server.py` 改绝对路径 | 开发模式 uvicorn 启动失败 | `_APP_BASE` fallback 到 `__file__` 父目录，与原行为一致 |
| `check_npm_deps()` 改目录扫描 | 普通包检测失效 | 单测覆盖普通包名的 preservation |
| `run_gui.py` 改轮询 | 高配机器启动变慢 | 轮询间隔 0.5s，就绪即返回，不引入额外延迟 |
| `ensure_data_dirs()` 创建目录 | 已有目录被覆盖 | 使用 `mkdir(exist_ok=True)`，幂等操作 |
