@echo off
REM CTP MdApi 行情服务·崩溃自重启双进程（5003=simnow 6.7.11.1，5004=citic 6.5.1_CP）
REM 自重入：不带参数=拉起两个子窗口；带 profile 参数=运行该 profile 的重启循环
cd /d %~dp0
set PY=C:\Users\wang\AppData\Local\Programs\Python\Python313\python.exe
if "%~1"=="simnow" goto run_simnow
if "%~1"=="citic" goto run_citic
start "ctp-md-simnow" /min cmd /c ""%~f0" simnow"
start "ctp-md-citic"  /min cmd /c ""%~f0" citic"
exit /b 0

:run_simnow
"%PY%" ctp_md\run_worker.py --profiles simnow --port 5003
echo [simnow] exited, restart in 10s
timeout /t 10 /nobreak >nul
goto run_simnow

:run_citic
"%PY%" ctp_md\run_worker.py --profiles citic --port 5004
echo [citic] exited, restart in 10s
timeout /t 10 /nobreak >nul
goto run_citic
