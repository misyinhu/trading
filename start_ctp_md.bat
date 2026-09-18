@echo off
REM CTP MdApi 行情服务（双进程：5003=simnow 6.7.11.1，5004=citic 6.5.1_CP；均 Python 3.13）
cd /d %~dp0
set PY=C:\Users\wang\AppData\Local\Programs\Python\Python313\python.exe
start "ctp-md-simnow" /min "%PY%" ctp_md\run_worker.py --profiles simnow --port 5003
start "ctp-md-citic"  /min "%PY%" ctp_md\run_worker.py --profiles citic  --port 5004
