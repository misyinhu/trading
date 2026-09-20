# 配置项

## 敏感配置 (.streamlit/secrets.toml)

敏感配置存储在以下位置：

| 项目 | 路径 |
|------|------|
| trading 根目录 | `.streamlit/secrets.toml` |
| kanban | `kanban/.streamlit/secrets.toml` |

```toml
# .streamlit/secrets.toml 示例（支持 sim/live 两套密钥）
# live 实盘
OKX_LIVE_API_KEY = "your-live-api-key"
OKX_LIVE_SECRET_KEY = "your-live-secret-key"
OKX_LIVE_PASSPHRASE = "your-live-passphrase"

# sim 模拟盘
OKX_SIM_API_KEY = "your-sim-api-key"
OKX_SIM_SECRET_KEY = "your-sim-secret-key"
OKX_SIM_PASSPHRASE = "your-sim-passphrase"

TV_WEBHOOK_URL = ""
WEBHOOK_URL = ""
IB_HOST = "127.0.0.1"
IB_PORT = 4001
```

| 变量 | 说明 |
|------|------|
| `OKX_LIVE_API_KEY` | OKX 实盘 API 密钥 |
| `OKX_LIVE_SECRET_KEY` | OKX 实盘密钥 |
| `OKX_LIVE_PASSPHRASE` | OKX 实盘密码 |
| `OKX_SIM_API_KEY` | OKX 模拟盘 API 密钥 |
| `OKX_SIM_SECRET_KEY` | OKX 模拟盘密钥 |
| `OKX_SIM_PASSPHRASE` | OKX 模拟盘密码 |
| `WEBHOOK_URL` | 飞书 Webhook 地址 |
| `IB_HOST` | Interactive Brokers 主机 |
| `IB_PORT` | Interactive Brokers 端口 |
| `TV_WEBHOOK_URL` | TradingView Webhook 地址 |

## 配置读取

```python
from kanban.src.config import get_okx_flag, get_okx_api_key, get_okx_secret_key

flag = get_okx_flag()  # 返回 "sim" 或 "live"
api_key = get_okx_api_key()  # 根据 flag 自动选择 live/sim 密钥
```

## OKX 交易模式

在 `config/settings.yaml` 中配置：

```yaml
okx:
  flag: sim  # sim=模拟盘, live=实盘
  pairs:
    - symbol: "DOGE-USDT"
      min_size: 1
    - symbol: "ETH-USDT"
      min_size: 10
```

## 服务器部署

### winclaw (100.99.204.126)

**项目路径**: `C:/projects/trading`

**Python 路径**: `C:\Users\wang\AppData\Local\Programs\Python\Python312\python.exe`（不在系统 PATH）

**启动 Webhook**:

```bash
# 必须用完整 Python 路径
C:\Users\wang\AppData\Local\Programs\Python\Python312\python.exe C:\projects\trading\notify\webhook_bridge.py
# 后台: start /B cmd /c "..."
```

**自愈脚本**: `C:\projects\trading\health_check.bat`
- 每 5 分钟由 Windows Task Scheduler `TradingHealthCheck` 触发
- 执行 `scripts/smoke_test.py`，失败 3 次后自动 `taskkill /F /IM python.exe` 并重启

**烟雾测试**:
```bash
C:\Users\wang\AppData\Local\Programs\Python\Python312\python.exe C:\projects\trading\scripts\smoke_test.py
```
测试 4 项: `/health`, `/health/full`, `POST /api/signals`, `GET /api/signals/<id>`

**检查状态**:
```bash
# Flask 端口
netstat -ano | findstr 5002

# 日志尾部
powershell -Command "Get-Content C:\projects\trading\webhook.log -Tail 20"

# 计划任务
schtasks /query /tn TradingHealthCheck
```

**部署新文件（scp 直传）**:
```bash
# macOS → winclaw（因为 GitHub 在 winclaw 上被墙）
scp <local_file> wang@100.99.204.126:/tmp/trading_new/
ssh wang@100.99.204.126 "copy /Y C:\tmp\trading_new\<file> C:\projects\trading\<dest>"
```

### quant-core (100.99.204.126:8005)

另一台服务器，FastAPI 数据服务。TDX/IB/OKX/TV 多源行情。

## Webhook 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/health` | 5组件自检 (feishu/risk_gate/signal_api/order_manager/query_only) |
| GET | `/health/full` | 深度自检 (含 IB 连接状态) |
| POST | `/tv-webhook` | TradingView 警报 |
| POST | `/feishu-webhook` | 飞书命令+自然语言下单 |
| POST | `/api/signals` | Agent 提交交易信号 |
| POST | `/api/signals/<id>/confirm` | 人确认/拒绝信号 |
| GET | `/api/signals/<id>` | 查询信号状态 |

## 注意事项

- **secrets.toml 已加入 .gitignore**，不要提交到版本控制
- **API 密钥**: 通过 streamlit secrets 读取，不再硬编码在 yaml
- **okx.yaml 已废弃**: 敏感信息已迁移到 secrets.toml
- **Python**: 项目使用 Python 3.13+ 特有语法

## 快捷命令

```bash
# 安装依赖
pip install -r requirements.txt

# 代码检查
ruff check .

# 运行测试
pytest tests/

# 提交代码（本地）
git add -A
git commit -m "描述"
git push
```

## Webhook 测试

```bash
# ❌ 本地测试已禁用（无数据环节）
# 仅支持服务器测试

# 服务器测试
curl -X POST http://alerts.qiaoge.top/tv-webhook \
  -H "Content-Type: application/json" \
  -d '{"text": "账户"}'
```

支持的命令：`status`、`订单`、`持仓`、`账户`、`买入 DOGE-USDT 1` 等。

---

## SimNow 内盘期货配置

### secrets.toml

```toml
SIMNOW_SIM_USER = "misyinhu"
SIMNOW_SIM_PASSWORD = "你的SimNow密码"   # 需登录 SimNow 官网填写
```

### settings.yaml（simnow 段）

```yaml
simnow:
  flag: sim          # sim / live（live 需另配服务器地址）
  sim:
    md_server: tcp://218.80.240.6:20002
    td_server: tcp://218.80.240.6:20003
    broker_id: "9999"
    auth_code: "0000000000"
  live:
    md_server: tcp://180.168.146.187:10111
    td_server: tcp://180.168.146.187:10112
    broker_id: "9999"
    auth_code: "0000000000"
```

### 配置读取

```python
from kanban.src.config import (
    get_simnow_flag,          # "sim" / "live"
    get_simnow_md_server,
    get_simnow_td_server,
    get_simnow_broker_id,
    get_simnow_auth_code,
    get_simnow_user,
    get_simnow_password,
)
```

### CTP DLL（必须）

SimNow 需要从官网下载 CTP API DLL，放到以下任一目录：

- `C:\Users\wang\AppData\Local\Programs\Python\Python313\`
- `C:\projects\trading\`
- Python 根目录（`C:\Users\wang\AppData\Local\Programs\Python\Python313\`）

需要两个文件：
- `mduserapi.dll`（行情）
- `tradeuserapi.dll`（交易）

下载地址：`https://www.simnow.com.cn/` → 技术支持 → CTP API

### 连通性测试

```bash
ssh wang@100.99.204.126
C:\Users\wang\AppData\Local\Programs\Python\Python313\python.exe C:\projects\trading\scripts\test_simnow.py
```
