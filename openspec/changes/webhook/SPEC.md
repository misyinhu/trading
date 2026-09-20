# Webhook SPEC

## Scope
TradingView/飞书 → IBKR 执行桥接服务

## Endpoints
| Endpoint | Method | 说明 |
|----------|--------|------|
| `/tv-webhook` | POST | TradingView 信号 |
| `/feishu-webhook` | POST | 飞书命令 |
| `/health` | GET | 健康检查 |

## 核心功能
- NL 命令解析: 买入/卖出/平仓/查询
- 后台异步下单 (ThreadPoolExecutor)
- 成交实时推送飞书
- execDetails 回调

## 支持品种
| 类型 | sec_type | 交易所 | 示例 |
|------|----------|--------|------|
| 期货 | FUT | COMEX/CME | GC, MGC, NQ |
| 外汇 | CASH | IDEALPRO | USDJPY, EURUSD |
| 商品 | CMDTY | SMART | XAUUSD, XAGUSD |
| CFD | CFD | SMART | GOLD CFD |
| 加密 | CRYPTO | PAXOS | BTC |

## Tech Stack
- Flask (port 5002)
- ib_insync
- concurrent.futures

## 关键文件
- `notify/webhook_bridge.py` - 主服务
- `notify/nl_parser.py` - 命令解析
- `orders/place_order_func.py` - 下单逻辑
- `client/ib_connection.py` - IB 连接

---

## AC Tables (TDD 唯一权威来源)

### Health Check (WH)

| US | AC | 验收标准 | TC |
|----|----|---------|-----|
| WH1 | AC_WH_US1_1 | GET /health 返回 HTTP 200 | TC-WH-001 |
| WH1 | AC_WH_US1_2 | config 包含必需字段 | TC-WH-001 |

### TradingView Webhook (WH)

| US | AC | 验收标准 | TC |
|----|----|---------|-----|
| WH2 | AC_WH_US1_3 | POST /tv-webhook 执行买入信号 | TC-WH-101 |
| WH2 | AC_WH_US1_4 | POST /tv-webhook 执行卖出信号 | TC-WH-101 |
| WH2 | AC_WH_US1_5 | 期货品种下单成功 | TC-WH-102 |
| WH2 | AC_WH_US1_6 | 外汇品种下单成功 | TC-WH-102 |
| WH2 | AC_WH_US1_7 | 加密品种下单成功 | TC-WH-102 |

### Feishu NL Command (WH)

| US | AC | 验收标准 | TC |
|----|----|---------|-----|
| WH3 | AC_WH_US1_8 | 解析"买入1手GC" | TC-WH-201 |
| WH3 | AC_WH_US1_9 | 解析"卖出2手MGC" | TC-WH-201 |
| WH3 | AC_WH_US1_10 | 查询持仓命令 | TC-WH-201 |
| WH3 | AC_WH_US1_11 | 查询账户命令 | TC-WH-201 |
| WH3 | AC_WH_US1_12 | 未知命令显示帮助 | TC-WH-201 |

### Trade Notification (WH)

| US | AC | 验收标准 | TC |
|----|----|---------|-----|
| WH4 | AC_WH_US1_13 | 订单成交触发回调 | TC-WH-301 |
| WH4 | AC_WH_US1_14 | 成交信息推送到飞书 | TC-WH-301 |
| WH4 | AC_WH_US1_15 | 同一订单不重复推送 | TC-WH-301 |