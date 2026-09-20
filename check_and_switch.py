import ctypes, subprocess, time, os

RESULT = r"C:\tmp\switch_result.txt"
LOG = r"C:\projects\trading\webhook.log"
PY313 = r"C:\Users\wang\AppData\Local\Programs\Python\Python313\python.exe"
FLASK = r"C:\projects\trading\notify\webhook_bridge.py"

kernel32 = ctypes.windll.kernel32

with open(RESULT, "w") as f:
    # Kill python processes by PID
    for pid in [3872, 14044, 26368]:
        handle = kernel32.OpenProcess(0x0001, False, pid)
        if handle:
            kernel32.TerminateProcess(handle, 1)
            kernel32.CloseHandle(handle)
            f.write(f"Killed PID {pid}\n")
        else:
            f.write(f"PID {pid} not accessible\n")
    
    time.sleep(3)
    
    # Check which Python processes remain
    procs = subprocess.run(
        ["powershell", "-Command", "Get-Process python | Select-Object Id,Path | ConvertTo-Csv"],
        capture_output=True, text=True
    )
    f.write(f"Remaining processes:\n{procs.stdout}\n")
    
    # Start Flask with 313
    p = subprocess.Popen(
        [PY313, FLASK],
        cwd=r"C:\projects\trading",
        stdout=open(LOG, "a"),
        stderr=subprocess.STDOUT,
        close_fds=False
    )
    f.write(f"Started Flask PID: {p.pid}\n")

print("Script completed")
