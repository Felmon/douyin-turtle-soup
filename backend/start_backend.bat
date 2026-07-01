@echo off
title CCcat 海龟汤 - 后端服务

echo ===================================
echo   CCcat 海龟汤 后端服务
echo ===================================
echo.

:: ── 设置路径 ──
set "ROOT_DIR=%~dp0.."
set "VENV_DIR=%ROOT_DIR%\venv"
set "BACKEND_DIR=%~dp0"

:: ── 检查/创建 venv ──
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [1/5] 创建虚拟环境...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ❌ 创建虚拟环境失败，请确保已安装 Python 3.10+
        pause
        exit /b 1
    )
    echo ✅ 虚拟环境已创建
) else (
    echo [1/5] 虚拟环境已存在，跳过
)

:: ── 安装依赖 ──
echo [2/5] 安装 Python 依赖...
call "%VENV_DIR%\Scripts\pip.exe" install -r "%BACKEND_DIR%\requirements.txt" -q
if errorlevel 1 (
    echo ⚠️ 部分依赖安装失败，请检查网络连接
)
echo ✅ Python 依赖安装完成

:: ── 安装 Node.js 依赖 ──
echo [3/5] 安装 Node.js 依赖...
cd /d "%BACKEND_DIR%"
if not exist "node_modules" (
    call npm init -y >nul 2>nul
)
call npm install ws express edge-tts 2>nul
echo ✅ Node.js 依赖安装完成

:: ── 启动服务 ──
echo.
echo [4/5] 启动后端服务...
echo.
echo   Qwen 分类服务:   http://localhost:3009
echo   WS 游戏服务:     ws://localhost:3010
echo   弹幕中继服务:    http://localhost:9876
echo   TTS 语音服务:    http://localhost:3006
echo.

:: 启动 Qwen Server
start "Qwen Server" cmd /k "title Qwen Server && "%VENV_DIR%\Scripts\python.exe" "%BACKEND_DIR%\qwen_server.py""
timeout /t 3 /nobreak >nul

:: 启动 Game Server
start "Game Server" cmd /k "title Game Server && "%VENV_DIR%\Scripts\python.exe" "%BACKEND_DIR%\game_server.py""
timeout /t 2 /nobreak >nul

:: 启动 Barrage Relay
start "Barrage Relay" cmd /k "title Barrage Relay && node "%BACKEND_DIR%\barrage-relay.mjs""
timeout /t 2 /nobreak >nul

:: 启动 TTS Relay
start "TTS Relay" cmd /k "title TTS Relay && node "%BACKEND_DIR%\tts-relay.cjs""
timeout /t 1 /nobreak >nul

echo.
echo [5/5] ✅ 所有后端服务已启动!
echo.
echo   服务端口一览:
echo   ┌──────────────────────┬──────┬────────────┐
echo   │ Qwen 分类服务        │ 3009 │ qwen_server.py │
echo   │ WS 游戏服务          │ 3010 │ game_server.py │
echo   │ 弹幕中继服务         │ 9876 │ barrage-relay.mjs│
echo   │ TTS 语音服务         │ 3006 │ tts-relay.cjs   │
echo   └──────────────────────┴──────┴────────────┘
echo.
echo   按任意键停止所有服务...
pause >nul

:: 停止所有服务
echo 正在停止服务...
taskkill /f /fi "WINDOWTITLE eq Qwen Server" >nul 2>nul
taskkill /f /fi "WINDOWTITLE eq Game Server" >nul 2>nul
taskkill /f /fi "WINDOWTITLE eq Barrage Relay" >nul 2>nul
taskkill /f /fi "WINDOWTITLE eq TTS Relay" >nul 2>nul
echo ✅ 服务已停止
