# Webhook 设计

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    TradingView / 飞书                           │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTP POST
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                   webhook_bridge.py (Flask)                     │
│                         Port: 5002                              │
├─────────────────────────────────────────────────────────────────┤
│  /tv-webhook      → TradingView 信号                           │
│  /feishu-webhook  → 飞书命令                                   │
│  /health          → 健康检查                                  │
└──────┬──────────────┬──────────────┬───────────────┬─────────────┘
       │              │              │               │
       ▼              ▼              ▼               ▼
┌────────────┐ ┌──────────┐ ┌───────────┐ ┌────────────┐ ┌──────────┐
│ nl_parser  │ │ place_   │ │ exec_     │ │  Feishu    │ │ IB KR    │
│ (命令解析) │ │ order    │ │ details   │ │ Notifier   │ │ Gateway  │
│            │ │ (下单)   │ │ (回调)    │ │ (推送)     │ │          │
└────────────┘ └──────────┘ └───────────┘ └────────────┘ └──────────┘
```

## 核心组件

### webhook_bridge.py (主服务)
- Flask 应用，端口 5002
- 接收 TV/飞书 HTTP 请求
- 路由到对应 handler

### nl_parser.py (命令解析)
- 正则匹配自然语言
- 提取 action/symbol/quantity
- 品种分类 (FUT/CASH/CMDTY/CFD/CRYPTO)

### orders/place_order_func.py (下单)
- 构造 IB 合约
- 提交市价/限价单
- 返回订单结果

## 接口

### HTTP Endpoints

| Endpoint | Method | 说明 |
|----------|--------|------|
| `/tv-webhook` | POST | TradingView 信号 |
| `/feishu-webhook` | POST | 飞书命令 |
| `/health` | GET | 健康检查 |

### Webhook 格式 (TradingView)
```json
{
  "symbol": "GC",
  "action": "BUY",
  "quantity": 1,
  "exchange": "COMEX",
  "sec_type": "FUT"
}
```

### NL 命令示例
| 命令 | 解析结果 |
|------|----------|
| `买入1手GC` | BUY, qty=1, symbol=GC |
| `卖空2手NQ` | SELL, qty=2, symbol=NQ |
| `平仓GC` | CLOSE, symbol=GC |
| `查看持仓` | QUERY |

## 关键函数

```python
# 后台下单
_submit_order_in_background(ib, symbol, action, quantity, **kwargs)

# 成交回调
_on_exec_details(trade, fill)  # 推送飞书通知

# NL 解析
parse_trading_command(message) -> {action, symbol, quantity, sec_type, exchange}
```

## 配置

```python
# IB 连接
IB_HOST = "127.0.0.1"
IB_PORT = 4001 (local) / 4002 (remote)
CLIENT_ID = 0

# 服务
WEBHOOK_PORT = 5002
FEISHU_CONVERSATION_ID = "..."
```