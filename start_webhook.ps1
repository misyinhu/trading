$env:HTTP_PROXY = "http://127.0.0.1:7890"
$env:HTTPS_PROXY = "http://127.0.0.1:7890"
# 必须使用 Python 3.13：CTP SWIG 原生绑定为 cp313（_thosttraderapi.cp313-win_amd64.pyd），
# 3.12 下无法加载，/api/ctp/* 会报 "No module named '_thosttraderapi'"。
$p = Start-Process -FilePath "C:\Users\wang\AppData\Local\Programs\Python\Python313\python.exe" -ArgumentList "C:\projects\trading\notify\webhook_bridge.py" -WorkingDirectory "C:\projects\trading\notify" -WindowStyle Hidden -PassThru
Start-Sleep 3
if ($p.HasExited) {
    Write-Host "Failed to start, exit code:" $p.ExitCode
} else {
    Write-Host "Started successfully, PID:" $p.Id
}
