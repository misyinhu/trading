@echo off
cd C:\projects\trading
echo Stopping old bridge on :5002 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5002" ^| findstr LISTENING') do taskkill /F /PID %%a
timeout /t 2 /nobreak >nul
echo Starting bridge ...
start /B python notify\webhook_bridge.py > webhook.log 2>&1
echo Done. Bridge on http://0.0.0.0:5002
