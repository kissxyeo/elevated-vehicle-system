@echo off
chcp 65001 >nul
cd /d %~dp0
if exist ".venv312\Scripts\python.exe" (
    start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:5000"
    ".venv312\Scripts\python.exe" app.py
) else (
    echo 未找到运行环境，请先按 README 安装依赖。
    pause
)
