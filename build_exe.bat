@echo off
chcp 65001 >nul
echo Building openGuiclaw launcher...

:: 读取版本号
set /p APP_VERSION=<VERSION
set APP_VERSION=%APP_VERSION: =%
echo 当前版本: %APP_VERSION%

:: 确保 pyinstaller 已经安装
pip install pyinstaller

echo 正在清理旧的构建文件...
if exist "build" rmdir /s /q "build"
if exist "dist\launcher" rmdir /s /q "dist\launcher"
if exist "dist\openGuiclaw" rmdir /s /q "dist\openGuiclaw"

:: ─────────────────────────────────────────────────────────────────────────────
:: 打包轻量启动器（仅含标准库，目标 < 10MB）
:: ─────────────────────────────────────────────────────────────────────────────
pyinstaller --noconfirm --onefile --windowed ^
  --icon="static/favicon.ico" ^
  --name "openGuiclaw" ^
  launcher.py

if %errorlevel% neq 0 (
  echo [ERROR] PyInstaller 打包失败
  pause
  exit /b 1
)

echo Launcher build complete!

:: ─────────────────────────────────────────────────────────────────────────────
:: 将项目源码复制到 dist\openGuiclaw\（安装包将打包此目录）
:: ─────────────────────────────────────────────────────────────────────────────
echo 正在整理发布目录 dist\openGuiclaw ...

:: 注意：--onefile 输出 dist\openGuiclaw.exe，先把它移走再建同名目录
if exist "dist\openGuiclaw.exe" (
  move /Y "dist\openGuiclaw.exe" "dist\_launcher_tmp.exe"
)
if not exist "dist\openGuiclaw" mkdir "dist\openGuiclaw"
if exist "dist\_launcher_tmp.exe" (
  move /Y "dist\_launcher_tmp.exe" "dist\openGuiclaw\openGuiclaw.exe"
)

:: 复制项目源码
xcopy /E /I /Y "core"      "dist\openGuiclaw\core"
xcopy /E /I /Y "skills"    "dist\openGuiclaw\skills"
xcopy /E /I /Y "plugins"   "dist\openGuiclaw\plugins"
xcopy /E /I /Y "templates" "dist\openGuiclaw\templates"
xcopy /E /I /Y "static"    "dist\openGuiclaw\static"
xcopy /E /I /Y "config"    "dist\openGuiclaw\config"
if exist "bin-node" xcopy /E /I /Y "bin-node" "dist\openGuiclaw\bin-node"

:: 复制根目录必要文件
copy /Y "run_gui.py"           "dist\openGuiclaw\run_gui.py"
copy /Y "main.py"              "dist\openGuiclaw\main.py"
copy /Y "requirements.txt"     "dist\openGuiclaw\requirements.txt"
copy /Y "config.json.example"  "dist\openGuiclaw\config.json.example"
copy /Y "PERSONA.md"           "dist\openGuiclaw\PERSONA.md"
if exist "npm-requirements.txt" copy /Y "npm-requirements.txt" "dist\openGuiclaw\npm-requirements.txt"
if exist "VERSION" copy /Y "VERSION" "dist\openGuiclaw\VERSION"

echo 发布目录整理完成。

:: ─────────────────────────────────────────────────────────────────────────────
:: 用 Inno Setup 编译安装包
:: ─────────────────────────────────────────────────────────────────────────────
where iscc >nul 2>&1
if %errorlevel% == 0 (
  echo 正在编译安装包...
  iscc /DAppVersion=%APP_VERSION% installer.iss
  if %errorlevel% == 0 (
    echo 安装包已生成至 output\openGuiclaw_Setup_%APP_VERSION%.exe
  ) else (
    echo [ERROR] Inno Setup 编译失败
  )
) else (
  echo [跳过] 未找到 iscc，请手动运行 Inno Setup 编译 installer.iss
  echo 提示：iscc /DAppVersion=%APP_VERSION% installer.iss
)
pause
