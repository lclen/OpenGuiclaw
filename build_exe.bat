@echo off
echo Building openGuiclaw executable...

:: 读取版本号
set /p APP_VERSION=<VERSION
set APP_VERSION=%APP_VERSION: =%
echo 当前版本: %APP_VERSION%

:: 确保 pyinstaller 已经安装
pip install pyinstaller

echo 正在清理旧的构建文件...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

:: 执行 PyInstaller
:: 注意：static/models/ 下只有 Avatar Sample B.vrm（14.72MB）会随安装包内置
:: 其他大体积 VRM 模型文件需用户自行放置到安装目录的 static/models/ 下
:: data/ 目录为运行时生成，不打包进安装包
pyinstaller --noconfirm --onedir --windowed ^
  --icon="static/favicon.ico" ^
  --hidden-import="skills.autogui" ^
  --hidden-import="skills.basic" ^
  --hidden-import="skills.file_manager" ^
  --hidden-import="skills.office_tools" ^
  --hidden-import="skills.system_tools" ^
  --hidden-import="skills.web_reader" ^
  --hidden-import="skills.web_search" ^
  --hidden-import="plugins.browser" ^
  --hidden-import="plugins.mcp_gateway" ^
  --hidden-import="plugins.plan_handler" ^
  --hidden-import="plugins.sandbox_repl" ^
  --hidden-import="plugins.scheduled" ^
  --hidden-import="plugins.skill_creator" ^
  --hidden-import="plugins.system" ^
  --hidden-import="plugins.weather" ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data "plugins;plugins" ^
  --add-data "skills;skills" ^
  --add-data "core;core" ^
  --add-data "bin-node;bin-node" ^
  --add-data "config.json.example;." ^
  --add-data "PERSONA.md;." ^
  --add-data "npm-requirements.txt;." ^
  --name "openGuiclaw" ^
  run_gui.py

echo Build complete!
echo 请检查 dist/openGuiclaw 目录。

:: 用 Inno Setup 编译安装包（需要 iscc 在 PATH 中）
where iscc >nul 2>&1
if %errorlevel% == 0 (
  echo 正在编译安装包...
  iscc /DAppVersion=%APP_VERSION% installer.iss
  echo 安装包已生成至 output\openGuiclaw_Setup_%APP_VERSION%.exe
) else (
  echo [跳过] 未找到 iscc，请手动运行 Inno Setup 编译 installer.iss
  echo 提示：编译时传入版本号参数：iscc /DAppVersion=%APP_VERSION% installer.iss
)
pause
