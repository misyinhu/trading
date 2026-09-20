$ErrorActionPreference = "Stop"
$port = 5006
$env:TIME_STOP_MODE = "audit"   # off | audit(feishu only) | enforce(auto reduce-only close)
$env:TIME_STOP_WARN_SEC = "7200"   # 2h warn
$env:TIME_STOP_STOP_SEC = "10800"  # 3h time stop
$env:PYTHONIOENCODING = "utf-8"
$existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $oldPid = $existing[0].OwningProcess
    Write-Host "live_gateway already listening on $port (PID $oldPid); stopping for restart"
    Stop-Process -Id $oldPid -Force
    Start-Sleep -Seconds 2
}
Set-Location C:\projects\trading
Start-Process -FilePath "C:\Users\wang\AppData\Local\Programs\Python\Python313\python.exe" `
  -ArgumentList "live_gateway\live_gateway_app.py" `
  -WorkingDirectory "C:\projects\trading" `
  -RedirectStandardOutput "C:\tmp\live_gateway.out" `
  -RedirectStandardError "C:\tmp\live_gateway.err" `
  -WindowStyle Hidden
Start-Sleep -Seconds 3
$listen = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listen) {
    Write-Host "live_gateway started on $port (PID $($listen[0].OwningProcess))"
} else {
    Write-Host "live_gateway failed to listen on $port; check C:\tmp\live_gateway.err"
    exit 1
}
