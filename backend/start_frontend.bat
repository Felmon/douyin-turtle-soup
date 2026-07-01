@echo off
echo ===================================
echo   CCcat 海龟汤 前端开发服务
echo ===================================
echo.
cd /d "%~dp0\frontend"
echo 安装依赖...
call npm install
echo.
echo 启动 Next.js 开发服务器...
call npm run dev
pause
