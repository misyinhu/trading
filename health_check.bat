@echo off
REM =============================================================================
REM winclaw 自检自愈脚本 — 定期检查服务健康，异常时自动重启
REM 用法: health_check.bat
REM 建议: Windows 任务计划程序 每5分钟运行一次
REM =============================================================================

set HEALTH_URL=http://localhost:5002/health
set MAX_RETRIES=3
set RETRY_DELAY=10

echo [%date% %time%] Trading Health Check

REM 检查服务是否响应
curl -s -o NUL -w "%%{http_code}" %HEALTH_URL% > health_status.txt
set /p STATUS=<health_status.txt

if "%STATUS%"=="200" (
    echo [%date% %time%] ✅ Health OK (HTTP 200)
    del health_status.txt
    exit /b 0
)

echo [%date% %time%] ⚠️ Health check returned HTTP %STATUS%
del health_status.txt

REM 重试逻辑
set RETRY=0
:retry_loop
set /a RETRY+=1
timeout /t %RETRY_DELAY% /nobreak > NUL
curl -s -o NUL -w "%%{http_code}" %HEALTH_URL% > health_status.txt
set /p STATUS=<health_status.txt

if "%STATUS%"=="200" (
    echo [%date% %time%] ✅ Health recovered on retry %RETRY%
    del health_status.txt
    exit /b 0
)

if %RETRY% LSS %MAX_RETRIES% goto retry_loop

REM 3次重试仍失败 → 自动重启
echo [%date% %time%] ❌ Health check failed after %MAX_RETRIES% retries. Restarting...

REM 杀掉旧进程
taskkill /F /IM python.exe /FI "WINDOWTITLE eq webhook*" 2>NUL
timeout /t 5 /nobreak > NUL

REM 重启
cd /d C:\projects\trading
set PYTHON=C:\Users\wang\AppData\Local\Programs\Python\Python312\python.exe
start /B %PYTHON% notify\webhook_bridge.py > webhook.log 2>&1

timeout /t 10 /nobreak > NUL

REM 验证重启后健康
curl -s -o NUL -w "%%{http_code}" %HEALTH_URL% > health_status.txt
set /p STATUS=<health_status.txt

if "%STATUS%"=="200" (
    echo [%date% %time%] ✅ Service restarted successfully
) else (
    echo [%date% %time%] ❌ Restart failed. Manual intervention required.
)
del health_status.txt