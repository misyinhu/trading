Stop-ScheduledTask -TaskName SimWatcher5007 -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*sim_watcher_app*' }
foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName SimWatcher5007
Write-Output "RESTARTED"
