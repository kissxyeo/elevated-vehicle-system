@echo off
chcp 65001 >nul
schtasks /end /tn "ElevatedVehicleSystem" >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*elevated-vehicle-system*app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo 服务已停止
pause
