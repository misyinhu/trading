# Webhook Epic - TradingView/飞书 执行桥接

## 1. 目标

构建 TradingView Webhook + 飞书命令 到 IBKR 执行的双向桥接服务。

## 2. 范围

**包含**:
- TradingView Webhook 接收端
- 飞书消息命令解析
- 自然语言下单 (NL parser)
- 后台异步订单执行
- 成交实时通知 (execDetails 回调)
- Feishu 告警推送

**不包含**:
- 复杂策略下单 (限价单、止损单)
- 多账户管理

## 3. 核心功能

| 功能 | 说明 |
|------|------|
| TradingView Webhook | 接收 TV 发来的交易信号 |
| 飞书命令解析 | 自然语言: "买入1手GC" |
| 后台下单 | ThreadPoolExecutor 异步执行 |
| 成交推送 | execDetails 回调实时通知 |
| 查询命令 | /持仓 /账户 /订单 |

## 4. 支持品种

| 类型 | sec_type | 交易所 | 示例 |
|------|----------|--------|------|
| 期货 | FUT | COMEX/CME | GC, MGC, NQ |
| 外汇 | CASH | IDEALPRO | USDJPY, EURUSD |
| 商品 | CMDTY | SMART | XAUUSD, XAGUSD |
| CFD | CFD | SMART | GOLD CFD |
| 加密 | CRYPTO | PAXOS | BTC |

## 5. 成功标准

- [x] TradingView Webhook 端点 (`/tv-webhook`)
- [x] 飞书消息 Webhook (`/feishu-webhook`)
- [x] NL 命令解析 (nl_parser.py)
- [x] 后台异步下单
- [x] 成交实时推送飞书
- [x] 健康检查端点 (`/health`)

## 6. 风险

- IB 连接不稳定导致下单失败
- 飞书 API 限流
- 网络延迟

---

## TDD 权威来源

**US/AC 表格已迁移至 SPEC.md**，作为 TDD 唯一权威来源。

- 详细 AC 定义: `SPEC.md` → AC Tables
- 测试执行: `qa/run_daily_tests.py`
