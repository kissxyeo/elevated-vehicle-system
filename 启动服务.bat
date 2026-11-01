@echo off
chcp 65001 >nul
title 高架车辆智能识别系统 - 服务运行中
echo ==========================================
echo   高架车辆智能识别系统
echo   访问地址: http://127.0.0.1:5000
echo   账号: admin / 密码: gaojia123
echo ==========================================
echo.
echo 服务正在启动，请稍候...
echo.

cd /d "%~dp0"
".venv312\Scripts\python.exe" app.py

if errorlevel 1 (
    echo.
    echo 服务启动失败！
    pause
)
