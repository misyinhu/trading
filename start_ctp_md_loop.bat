@echo off
REM CTP MdApi 行情服务·崩溃自重启双进程（5003=simnow 6.7.11.1，5004=citic 6.5.1_CP）
cd /d %~dp0
set PY=C:\Users\wang\AppData\Local\Programs\Python\Python313\python.exe
start "ctp-md-simnow" /min cmd /c ":a & %PY% ctp_md\run_worker.py --profiles simnow --port 5003 & echo restart in 10s & timeout /t 10 & goto a"
start "ctp-md-citic"  /min cmd /c ":a & %PY% ctp_md\run_worker.py --profiles citic  --port 5004 & echo restart in 10s & timeout /t 10 & goto a"
