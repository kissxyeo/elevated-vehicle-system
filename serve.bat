@echo off
chcp 65001 >nul
cd /d %~dp0

:loop
".venv312\Scripts\python.exe" app.py >> server.out.log 2>> server.err.log
timeout /t 5 /nobreak >nul
goto loop
