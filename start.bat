@echo off
setlocal
cd /d "%~dp0"
title 鼠鼠大王工具箱

set "PY=.venv\Scripts\python.exe"
set "PYW=.venv\Scripts\pythonw.exe"

rem ---- 健康检查：虚拟环境 ----
if not exist "%PY%" (
    echo [错误] 未找到虚拟环境 .venv，请先初始化：
    echo     python -m venv .venv
    echo     .venv\Scripts\python -m pip install -e ".[dev]"
    echo.
    pause
    exit /b 1
)

rem ---- 健康检查：项目已安装 ----
"%PY%" -c "import deltaforcebox" >nul 2>&1
if errorlevel 1 (
    echo [错误] 项目尚未安装，请先执行：
    echo     .venv\Scripts\python -m pip install -e ".[dev]"
    echo.
    pause
    exit /b 1
)

rem ---- 无控制台窗口启动 GUI ----
start "" "%PYW%" -m deltaforcebox.main
exit /b 0