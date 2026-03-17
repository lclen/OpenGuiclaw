@echo off
chcp 65001 >nul
title OpenGuiclaw Web UI

echo ========================================
echo   OpenGuiclaw Web UI 启动器
echo ========================================
echo.

echo [1/2] 检查 Python 环境...
python --version
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

echo.
echo [2/2] 启动 Web 服务器...
echo 访问地址: http://127.0.0.1:8010
echo 按 Ctrl+C 停止服务
echo.

python -m uvicorn core.server:app --host 127.0.0.1 --port 8010 --reload

pause
