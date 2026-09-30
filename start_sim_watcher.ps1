$env:PYTHONIOENCODING = "utf-8"
Set-Location D:\projects\trading
if (-not (Test-Path data)) { New-Item -ItemType Directory data | Out-Null }
& C:\Users\Apple\AppData\Local\Programs\Python\Python312\python.exe live_gateway\sim_watcher_app.py *>> data\sim_watcher.log
