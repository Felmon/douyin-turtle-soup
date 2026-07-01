@echo off
echo ===================================
echo   CCcat 海龟汤 一键启动
echo ===================================
echo.

echo [1/3] 启动后端...
start "Backend" cmd /k "cd /d %~dp0backend && python qwen_server.py"
timeout /t 8 /nobreak >nul
start "GameWS" cmd /k "cd /d %~dp0backend && python game_server.py"
timeout /t 3 /nobreak >nul

echo [2/3] 启动前端...
cd /d "%~dp0frontend"
if not exist "node_modules" (
    echo 安装依赖中...
    call npm install
)
start "Frontend" cmd /k "call npm run dev"

echo [3/3] 等待服务就绪...
timeout /t 5 /nobreak >nul
start http://localhost:3000

echo.
echo ✅ CCcat 海龟汤 已启动!
echo    前端: http://localhost:3000
echo    Qwen: http://localhost:3009
echo    游戏: ws://localhost:3010
echo.
pause
