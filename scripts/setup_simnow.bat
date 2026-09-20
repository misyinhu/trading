@echo off
:: setup_simnow.bat — SimNow / CTP 环境配置脚本（winclaw 用）
:: 用法: 双击运行 或 cmd /c setup_simnow.bat
:: 必须以管理员权限运行

echo [SimNow Setup] 开始配置内盘期货 SimNow 环境...
echo.

:: ── 1. 检查 Python 版本 ────────────────────────────────────────
echo [Step 1] 检查 Python 版本...
python --version >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Python 未找到，请安装 Python 3.8~3.11
    echo        VN.py CTP 暂不支持 Python 3.12
    echo        下载: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "delims=. tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [INFO] 当前 Python: %PYVER%

:: Python 3.12 检测（vnpy_ctp 暂不支持）
echo %PYVER% | findstr /C:"3.12" >nul
if not errorlevel 1 (
    echo [WARN] 检测到 Python 3.12
    echo        vnpy_ctp 需要 Python 3.8~3.11
    echo        如需使用 SimNow，请安装 Python 3.11 并使用其 pip
    echo        示例: py -3.11 -m pip install vnpy_ctp
    echo.
)

:: ── 2. 安装 vnpy_ctp ───────────────────────────────────────────
echo [Step 2] 安装 vnpy_ctp...
python -m pip install vnpy_ctp --quiet
if errorlevel 1 (
    echo [FAIL] vnpy_ctp 安装失败，尝试指定版本:
    echo        pip install vnpy_ctp==1.3.2
    echo        或从 https://pypi.org/project/vnpy_ctp/ 下载 whl
    echo.
) else (
    echo [PASS] vnpy_ctp 安装完成
)
echo.

:: ── 3. 下载 SimNow CTP DLL（如果不存在） ───────────────────────
echo [Step 3] 检查 CTP 动态链接库...
set DLL_DIR=%USERPROFILE%\.vnpy\ctp
if not exist "%DLL_DIR%" mkdir "%DLL_DIR%"

:: SimNow 官方下载地址（模拟用户可从 simnow.com.cn 下载）
:: 手动下载并放到 %DLL_DIR% 目录
if exist "%DLL_DIR%\mduserapi.dll" (
    echo [PASS] mduserapi.dll 已存在
) else (
    echo [WARN] mduserapi.dll 未找到
    echo        请从 SimNow 官网下载 CTP API 并解压到:
    echo        %DLL_DIR%
    echo        下载地址: https://www.simnow.com.cn (搜索 "CTP API")
)
echo.

:: ── 4. 添加账户凭证 ────────────────────────────────────────────
echo [Step 4] 配置 SimNow 账户...
set SECRETS=%~dp0..\.streamlit\secrets.toml
if not exist "%SECRETS%" (
    echo [INFO] 创建 secrets.toml...
    echo # SimNow 凭证 > "%SECRETS%"
    echo SIMNOW_SIM_USER = "" >> "%SECRETS%"
    echo SIMNOW_PASSWORD = "" >> "%SECRETS%"
)

:: ── 5. 验证连通性 ───────────────────────────────────────────────
echo [Step 5] 验证 SimNow 连通性（ping 服务器）...
ping -n 1 -w 1000 218.80.240.6 >nul 2>&1
if errorlevel 1 (
    echo [WARN] 无法 ping 通 SimNow 服务器 218.80.240.6
    echo        请检查网络和代理设置
) else (
    echo [PASS] SimNow 服务器可达
)
echo.

:: ── 完成 ───────────────────────────────────────────────────────
echo ============================================================
echo [完成] SimNow 环境配置完成
echo.
echo 接下来请:
echo   1. 编辑 secrets.toml，填入 SimNow 账号密码
echo      SIMNOW_SIM_USER     = "misyinhu"
echo      SIMNOW_SIM_PASSWORD = "你的密码"
echo.
echo   2. 重启 Flask:
echo      taskkill /F /IM python.exe
echo      start /B cmd /c "C:\Users\wang\AppData\Local\Programs\Python\Python312\python.exe C:\projects\trading\notify\webhook_bridge.py"
echo.
echo   3. 测试: curl http://localhost:5002/health
echo ============================================================
pause
