@echo off
chcp 65001 >nul
title CCcat 海龟汤 - 生成 EXE

echo ===========================================
echo   CCcat 海龟汤 🐢 — 生成 EXE
echo ===========================================
echo.

cd /d "%~dp0"

REM 使用项目 venv 的 PyInstaller
set PYTHON=venv\Scripts\python.exe
set PYINSTALLER=venv\Scripts\pyinstaller.exe

echo [1/3] 检查环境...
if not exist "%PYTHON%" (
    echo ❌ Python venv 未找到，请先运行 start_all.bat
    pause
    exit /b 1
)

echo [2/3] 清理旧的构建...
if exist "dist\CCcat海龟汤" rmdir /s /q "dist\CCcat海龟汤"
if exist "build" rmdir /s /q "build"

echo [3/3] 打包 EXE（单文件模式）...
echo   这可能需要 1-2 分钟...

"%PYINSTALLER%" --onefile ^
    --name "CCcat海龟汤" ^
    --distpath "dist" ^
    --add-data "backend\data_soups.py;." ^
    --hidden-import uvicorn ^
    --hidden-import uvicorn.loggers ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import httpx ^
    --hidden-import openai ^
    --hidden-import pydantic ^
    --hidden-import dotenv
    --hidden-import websockets ^
    --clean ^
    backend\server.py

if %ERRORLEVEL% equ 0 (
    echo.
    echo ✅ 生成成功！
    echo    EXE 位置: dist\CCcat海龟汤.exe
    echo.
    echo 注意：首次运行需要：
    echo   1. 在 .env 中配置 LLM_API_KEY
    echo   2. Node.js 18+ 用于前端 dev server
    echo   3. 前端需在 meoo_frontend 目录运行 npm run dev
    echo.
) else (
    echo.
    echo ❌ 打包失败，请检查错误信息
)

pause
