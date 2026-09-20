@echo off
cd C:\projects\trading
start /B cmd /c "python notify\webhook_bridge.py > webhook.log 2>&1"