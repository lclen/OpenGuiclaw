# exe-packaging-bugfix 实现任务列表

## Tasks

- [x] 1. 修复 build_exe.bat 打包配置（Bug 1、Bug 8）
  - [x] 1.1 移除 `--add-data "data;data"` 这一行
  - [x] 1.2 确认 `--add-data "static;static"` 保持不变（内置 Avatar Sample B.vrm，14.72MB）
  - [x] 1.3 在注释中说明其他大体积模型文件需用户自行放置到 static/models/

- [x] 2. 重构 core/bootstrap.py（Bug 2、3、5、6、7）
  - [x] 2.1 新增 `get_app_base_dir() -> Path` 函数：frozen 时返回 exe 所在目录，开发时返回项目根目录
  - [x] 2.2 修改 `setup_node_env()`：调用 `get_app_base_dir()` 并设置 `APP_BASE_DIR` 环境变量；frozen 时从 `sys._MEIPASS/bin-node` 取 node，开发时从 `app_base/bin-node` 取
  - [x] 2.3 新增 `ensure_data_dirs()` 函数：在 APP_BASE_DIR 下创建所有必要子目录（data, sessions, memory, diary, journals, identities, identity, plans, scheduler, screenshots, consolidation），使用 `mkdir(parents=True, exist_ok=True)`
  - [x] 2.4 新增 `ensure_config()` 函数：config.json 不存在时从 config.json.example 复制，两者都不存在时打印 WARN
  - [x] 2.5 提取 `_parse_pkg_name(pkg: str) -> str` 函数修复 scoped 包名解析：`@scope/pkg@ver` → `@scope/pkg`，`pkg@ver` → `pkg`
  - [x] 2.6 提取 `_is_npm_pkg_installed(pkg_name: str, npm_global_prefix: str) -> bool` 函数：通过扫描 node_modules 目录判断，scoped 包检查 `node_modules/@scope/pkg/` 目录
  - [x] 2.7 重构 `check_npm_deps()` 使用上述两个新函数，移除 `npm ls --parseable` 解析逻辑
  - [x] 2.8 修改 `run()` 调用顺序：setup_node_env → ensure_data_dirs → ensure_config → print_environment_diagnostics → check_python_deps → check_npm_deps

- [x] 3. 修复 run_gui.py 启动等待逻辑（Bug 4）
  - [x] 3.1 新增 `wait_for_server(port: int, timeout: float = 30.0, interval: float = 0.5) -> bool` 函数，轮询 `/api/health` 返回 200
  - [x] 3.2 替换 `time.sleep(2)` 为 `wait_for_server(port)` 调用
  - [x] 3.3 超时时用 tkinter.messagebox 弹出错误提示并 `os._exit(1)`

- [x] 4. 修复 server.py 相对路径问题（Bug 6）
  - [x] 4.1 在文件顶部 import 区域后添加 `_APP_BASE = Path(os.environ.get("APP_BASE_DIR", Path(__file__).resolve().parent.parent))`
  - [x] 4.2 将模块级 `StaticFiles`、`Jinja2Templates`、`os.makedirs` 改为基于 `_APP_BASE` 的绝对路径
  - [x] 4.3 将 lifespan 内 `config_path`、`data_dir`、`plugins_dir` 改为绝对路径
  - [x] 4.4 将 `_system_daily_selfcheck` 内 required_dirs 列表改为绝对路径
  - [x] 4.5 将 `_system_memory_consolidate` 内 `Path("data/sessions")` 和 `Path("data/scheduler")` 改为绝对路径
  - [x] 4.6 将 `/api/config` 路由内 `open("config.json", ...)` 改为绝对路径

- [x] 5. 编写 property-based 测试（tests/test_bootstrap_packaging.py）
  - [x] 5.1 `test_parse_pkg_name_scoped`：`"@pixiv/three-vrm@2.1.0"` → `"@pixiv/three-vrm"`
  - [x] 5.2 `test_parse_pkg_name_scoped_no_version`：`"@scope/pkg"` → `"@scope/pkg"`
  - [x] 5.3 `test_parse_pkg_name_plain`：`"agent-browser@0.16.3"` → `"agent-browser"`
  - [x] 5.4 `test_parse_pkg_name_plain_no_version`：`"agent-browser"` → `"agent-browser"`
  - [x] 5.5 `test_is_npm_pkg_installed_plain`：创建临时 node_modules/pkg/ 目录，断言返回 True
  - [x] 5.6 `test_is_npm_pkg_installed_scoped`：创建临时 node_modules/@scope/pkg/ 目录，断言返回 True
  - [x] 5.7 `test_is_npm_pkg_installed_missing`：不创建目录，断言返回 False
  - [x] 5.8 `test_ensure_data_dirs_creates_all`：在临时目录下调用，断言所有 11 个子目录存在且可写
  - [x] 5.9 `test_ensure_data_dirs_idempotent`：调用两次，断言无异常
  - [x] 5.10 `test_ensure_config_copies_example`：只有 example 存在时，断言 config.json 被创建且内容一致
  - [x] 5.11 `test_ensure_config_no_overwrite`：config.json 已存在时，断言内容不被覆盖
  - [x] 5.12 `test_get_app_base_dir_dev`：非 frozen 状态，断言返回项目根目录（包含 core/ 子目录）
  - [x] 5.13 PBT：生成随机非 scoped 包名字符串，验证 `_parse_pkg_name` 结果不含 `@` 且不含版本号分隔符
  - [x] 5.14 PBT：多次调用 `ensure_data_dirs()`，验证幂等性（无异常，目录始终存在）
