@echo off
REM LvsheProject 3.0 一键启动（CMD 版本）
REM 用法：双击或在命令行运行 start.bat

cd /d "%~dp0"

echo ========================================
echo   LvsheProject 3.0 启动
echo ========================================

REM 启动后端（新窗口）
start "LvsheProject Backend" cmd /k "cd /d %~dp0 && .venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001"

timeout /t 3 /nobreak >nul

REM 启动前端（新窗口）
start "LvsheProject Frontend" cmd /k "cd /d %~dp0\frontend-next && npm run dev"

echo.
echo ========================================
echo   启动完成！
echo ========================================
echo   前端访问: http://localhost:5173
echo   后端 API: http://127.0.0.1:8001
echo   API 文档: http://127.0.0.1:8001/docs
echo.
echo   后端和前端在新窗口运行，关闭窗口即可停止
echo.
pause
