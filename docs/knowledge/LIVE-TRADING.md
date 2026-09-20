# 实盘交易配置手册

> 从 Paper 到实盘：IB + OKX 双通道切换清单。
> 最后更新：2026-08-25

---

## 一、核心切换原则

**IB 实盘切换是 IB Gateway/TWS 的配置操作，不需要改代码。**
**OKX 实盘切换只需改一个配置项。**

系统设计为：IB 和 OKX 的 live/sim 切换都在配置层完成，代码本身不变。

---

## 二、IB 实盘交易（Interactive Brokers）

### 2.1 切换步骤

IB 实盘不需要改代码，只需要在 **IB Gateway / TWS** 里操作：

```
Paper 账户 (DUH583159)  →  实盘账户
IB Gateway 保持端口 4002 不变
Flask clientId=999 不变
代码完全不动
```

**操作步骤：**

1. 打开 IB Gateway（或 TWS）
2. 右上角账户下拉 → **切换账户**
3. 选择你的实盘账户（不是 paper 的 DUH583159）
4. 确认连接状态 → IB Gateway 里显示实盘账户

> ⚠️ **同一 IB Gateway 同时只能登录一个账户**，不能 paper 和 live 同时连。

### 2.2 代码层配置

IB 连接配置在 `config/settings.yaml`：

```yaml
# 当前环境
current: winclaw

# IB 连接
# IB Gateway 端口：4002（winclaw），4001（osclaw）
# clientId=999 由 client/ib_connection.py 硬编码，不可改
```

关键文件：`client/ib_connection.py`：

```python
self._client_id: int = 999   # 固定，不能改
self._host = get_ibkr_host()  # 从 settings.yaml 读取，当前 127.0.0.1
self._port = get_ibkr_port()  # 从 settings.yaml 读取，当前 4002
```

### 2.3 切换验证

```bash
# 确认 IB 连接指向实盘账户
curl http://localhost:5002/health/full

# 查看返回的 account 信息（如果 API 支持）
# 实盘账户会显示真实 BuyingPower / NetLiq
```

### 2.4 注意事项

| 事项 | 说明 |
|------|------|
| clientId | Flask IB worker 固定用 999，IB Gateway 里显示为连接的用户 |
| 同时只能一个账户 | IB Gateway 不能同时连 paper + live，需要退出重连 |
| paper 订单簿 | 实盘账户没有 paper 订单，两个账户的持仓/订单完全独立 |
| 飞书通知 | 信号链路不变，实盘下单后会推飞书通知 |

---

## 三、OKX 实盘交易

### 3.1 配置切换（唯一改动）

文件：`config/settings.yaml`

```yaml
# OKX 交易配置
okx:
  flag: live    # ← 改这里：sim → live
  pairs:
    - symbol: "DOGE-USDT"
      min_size: 1
    - symbol: "ETH-USDT"
      min_size: 10
    - symbol: "BTC-USDT"
      min_size: 10
```

### 3.2 密钥配置（secrets.toml）

实盘和模拟盘两套密钥都在 `.streamlit/secrets.toml` 里：

```toml
# .streamlit/secrets.toml

# === 实盘密钥（live）===
OKX_LIVE_API_KEY = "your-live-api-key"
OKX_LIVE_SECRET_KEY = "your-live-secret-key"
OKX_LIVE_PASSPHRASE = "your-live-passphrase"

# === 模拟盘密钥（sim）===
OKX_SIM_API_KEY = "your-sim-api-key"
OKX_SIM_SECRET_KEY = "your-sim-secret-key"
OKX_SIM_PASSPHRASE = "your-sim-passphrase"
```

系统根据 `okx.flag` 自动选择用哪套密钥，**不需要手动改 secrets.toml**。

### 3.3 网络代理

OKX SDK 需要代理（winclaw 上使用 127.0.0.1:7890），已在 `okx_trader.py` 里自动配置：

```python
# okx_trader.py 第 50-58 行
proxies = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}
```

如果代理变了，改这里：`okx_client/okx_trader.py`

### 3.4 切换验证

```bash
# 重启 Flask 使配置生效
ssh wang@100.99.204.126
taskkill /F /IM python.exe
start /B cmd /c "C:\Users\wang\AppData\Local\Programs\Python\Python312\python.exe C:\projects\trading\notify\webhook_bridge.py"

# 发一笔小额测试单
curl -X POST http://localhost:5002/feishu-webhook \
  -H "Content-Type: application/json" \
  -d '{"text": "买入 DOGE-USDT 1"}
```

### 3.5 OKX flag 读取链路

```
config/settings.yaml  →  okx.flag: live/sim
        ↓
config/env_config.py  →  读取 yaml 并暴露
        ↓
okx_client/okx_trader.py  →  OKXTrader(flag=flag)
        ↓
secrets.toml  →  根据 flag 选 LIVE_xxx 或 SIM_xxx 密钥
```

---

## 四、IB + OKX 同时实盘

同时开两个通道实盘，只需要在各自界面切换：

```
IB  →  IB Gateway 切到实盘账户
OKX →  settings.yaml flag: live
```

两地持仓独立，互不影响。

---

## 五、风控不变

实盘和 paper 共用同一套 RiskGate：

```yaml
risk_gate:
  max_daily_loss_pct: 0.05    # 日亏 ≥ 5% → 拒绝
  max_leverage: 3.0            # 杠杆 > 3x → 拒绝
  max_open_positions: 3       # 持仓 ≥ 3 → 拒绝
```

实盘下单同样经过风控闸门，不存在绕过。

---

## 六、部署生效流程

改完配置后：

```bash
# 1. scp 传配置（如果改了代码）
scp webhook_bridge.py wang@100.99.204.126:/tmp/

# 2. SSH 进 winclaw
ssh wang@100.99.204.126

# 3. 杀旧进程
taskkill /F /IM python.exe

# 4. 重启 Flask
start /B cmd /c "C:\Users\wang\AppData\Local\Programs\Python\Python312\python.exe C:\projects\trading\notify\webhook_bridge.py"

# 5. 验证
curl http://localhost:5002/health
```

---

## 七、当前状态（2026-08-25）

| 通道 | 状态 | 配置 |
|------|------|------|
| IB | **Paper** | IB Gateway 连 DUH583159 |
| OKX | **Sim** | `okx.flag = sim` |

切换实盘只需要：
1. IB Gateway 切换账户 → IB 实盘
2. settings.yaml `flag: live` → OKX 实盘
