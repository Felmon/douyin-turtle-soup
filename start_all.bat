@echo off
title CCcat 海龟汤 🐢 一键启动
chcp 65001 >nul

echo ===========================================
echo         CCcat 海龟汤 🐢 一键启动
echo ===========================================
echo.

REM 检查 exe
if exist "dist\CCcat海龟汤.exe" (
    echo [启动] 后端服务 exe...
    start "CCcat海龟汤" "dist\CCcat海龟汤.exe"
    timeout /t 3 /nobreak >nul
) else (
    echo [启动] Python 后端服务...
    if not exist "venv\Scripts\python.exe" (
        python -m venv venv
        call venv\Scripts\pip install -r backend\requirements.txt
    )
    start "Qwen/Game" cmd /k "title CCcat后端 && call venv\Scripts\python.exe backend\server.py"
    timeout /t 3 /nobreak >nul
)

REM 启动前端
echo [启动] 前端开发服务器...
cd /d "%~dp0meoo_frontend"
if not exist "node_modules" (
    echo   安装前端依赖...
    call npm install --silent
)
start "Frontend" cmd /k "title CCcat前端 && npm run dev"
cd /d "%~dp0"

echo.
echo ===========================================
echo    ✅ 服务启动完毕!
echo.
echo    后端 API: http://localhost:3010/health
echo    前端界面: http://localhost:3015
echo    游戏 WS:  ws://localhost:3010/ws
echo.
echo    按任意键关闭所有服务...
echo ===========================================
pause >nul

REM 关闭
taskkill /fi "WINDOWTITLE eq CCcat后端" /f >nul 2>nul
taskkill /fi "WINDOWTITLE eq CCcat前端" /f >nul 2>nul
taskkill /f /im "CCcat海龟汤.exe" >nul 2>nul
echo 服务已关闭。
