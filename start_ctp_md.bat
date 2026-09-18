@echo off
REM CTP MdApi 行情服务（独立进程，Python 3.13 + SWIG cp313）
cd /d %~dp0
set PY=C:\Users\wang\AppData\Local\Programs\Python\Python313\python.exe
"%PY%" ctp_md\run_worker.py --port 5003
