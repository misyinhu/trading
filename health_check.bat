@echo off
REM =============================================================================
REM winclaw 自检自愈脚本 — 定期检查服务健康，异常时自动重启
REM 用法: health_check.bat
REM 建议: Windows 任务计划程序 每5分钟运行一次
REM 注意: Flask 由 Windows Task Scheduler 托管，SSH 断开不影响
REM =============================================================================

set HEALTH_URL=http://localhost:5002/health
set MAX_RETRIES=3
set RETRY_DELAY=10

echo [%date% %time%] Trading Health Check

REM 检查服务是否响应
curl -s -o NUL -w "%%{http_code}" %HEALTH_URL% > health_status.txt
set /p STATUS=<health_status.txt

if "%STATUS%"=="200" (
    echo [%date% %time%] [PASS] Health OK (HTTP 200)
    del health_status.txt
    exit /b 0
)

echo [%date% %time%] [WARN] Health check returned HTTP %STATUS%
del health_status.txt

REM 重试逻辑
set RETRY=0
:retry_loop
set /a RETRY+=1
timeout /t %RETRY_DELAY% /nobreak > NUL
curl -s -o NUL -w "%%{http_code}" %HEALTH_URL% > health_status.txt
set /p STATUS=<health_status.txt

if "%STATUS%"=="200" (
    echo [%date% %time%] [PASS] Health recovered on retry %RETRY%
    del health_status.txt
    exit /b 0
)

if %RETRY% LSS %MAX_RETRIES% goto retry_loop

REM 3次重试仍失败 → 自动重启
echo [%date% %time%] [FAIL] Health check failed after %MAX_RETRIES% retries. Restarting...

REM 杀掉旧 Flask 进程（按窗口标题精确匹配，不误杀其他 python）
taskkill /F /FI "WINDOWTITLE eq TradingBridge*" 2>NUL
timeout /t 3 /nobreak > NUL

REM 重启 Flask — 关键：start "" cmd /c 在独立会话启动，SSH 断开不影响
cd /d C:\projects\trading
set PYTHON=C:\Users\wang\AppData\Local\Programs\Python\Python313\python.exe

REM start "" 启动无关联的新窗口，/c 执行完自动退出cmd，python 进程留在后台
REM 添加 WINDOWTITLE=TradingBridge 供后续 taskkill 精确匹配
start "TradingBridge" cmd /c "title TradingBridge && %PYTHON% notify\webhook_bridge.py >> webhook.log 2>&1"

timeout /t 10 /nobreak > NUL

REM 验证重启后健康
curl -s -o NUL -w "%%{http_code}" %HEALTH_URL% > health_status.txt
set /p STATUS=<health_status.txt

if "%STATUS%"=="200" (
    echo [%date% %time%] [PASS] Service restarted successfully
) else (
    echo [%date% %time%] [FAIL] Restart failed. Manual intervention required.
)
del health_status.txt
