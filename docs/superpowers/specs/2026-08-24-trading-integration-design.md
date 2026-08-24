# Trading 架构整合设计文档

> 状态：待审核 | 日期：2026-08-24 | 作者：Mavis

## 一、背景与目标

### 现状

五个量化项目各自独立运行，代码间已有部分交叉依赖但未形成闭环：

- **trading**（实盘运行时）：Webhook→飞书→IB/OKX 下单，kanban 看板，策略机器人
- **quant**（数据服务）：FastAPI :8005，TDX/IB/OKX/TV 多源行情
- **quant-research**（策略研究）：协整/卡尔曼对冲/风控/回测
- **quant-agent**（AI 编排）：CrewAI 多 Agent，已有 quant-core 和 quant-research adapter
- **quant-edge-pro**（产品蓝图）：PRD/UX 规格文档为主，代码是原型

### 核心缺口

1. **实盘下单无风控** — `orders/place_order_func.py` 362行零次风险检查，OKX 路径同样缺失
2. **Agent 下单链路断裂** — `quant-agent/tools/quant_core_adapter.py` 的 `place_order` 调 quant-core HTTP `/api/order`，而非 trading 的真实下单路径
3. **策略信号未闭环** — quant-research 的协整/配对分析结果未自动喂给 trading 下单器
4. **下单入口散落** — trading 内至少 6 处独立调用 `place_order`，无统一订单追踪

### 整合目标

以 trading 为实盘基座，将 quant-research 的风控能力、quant-agent 的 AI 编排能力、quant-edge-pro 的产品规格"焊入"一条完整链路：

```
quant-agent → 信号 API → trading 风控闸门 → 人确认 → IB/OKX 下单
```

---

## 二、架构设计

```
┌─ quant-agent (macOS) ─────────────────────────────────────────┐
│  CrewAI: Researcher → FundManager → TradingAgent              │
│  ┌──────────────────────┐  ┌──────────────────────────────┐   │
│  │ quant_research_      │  │ 🆕 trading_adapter.py        │   │
│  │ adapter (已有)        │  │  submit_signal() → HTTP POST │   │
│  │ get_spread_analysis()│  │  check_signal_status()       │   │
│  └──────────────────────┘  └──────────────┬───────────────┘   │
└───────────────────────────────────────────┼───────────────────┘
                                            │ HTTP POST /api/signals
                                            ▼
┌─ trading Flask :5002 (winclaw) ───────────────────────────────┐
│  webhook_bridge.py                                            │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 🆕 POST /api/signals           → SignalHandler          │  │
│  │ 🆕 POST /api/signals/{id}/confirm → 执行下单             │  │
│  │ 🆕 GET  /api/signals/{id}      → 查询状态                │  │
│  └─────────────────────────────────────────────────────────┘  │
│                           │                                    │
│  ┌────────────────────────▼────────────────────────────────┐  │
│  │ 🆕 RiskGate (下单前强制风控)                              │  │
│  │  · DailyLossBreaker     — 单日亏损熔断 5%               │  │
│  │  · ExposureLimit        — 杠杆上限 3x                   │  │
│  │  · CorrelationBreaker   — 相关性 <0.7 拒绝              │  │
│  │  · ZScoreGuard          — Z-Score 三级告警              │  │
│  │  · MaxPositionsGuard    — 同时持仓上限                   │  │
│  └────────────────────────┬────────────────────────────────┘  │
│                           │ pass                               │
│  ┌────────────────────────▼────────────────────────────────┐  │
│  │ 🆕 OrderManager (统一订单入口)                            │  │
│  │  · 取代现有 6 处散落的 place_order 调用                   │  │
│  │  · 订单追踪 (pending→submitted→filled/cancelled)         │  │
│  │  · 超时取消 / 重试                                       │  │
│  └────────────────────────┬────────────────────────────────┘  │
│                           │                                    │
│           ┌───────────────┼───────────────┐                    │
│           ▼               ▼               ▼                    │
│      IB Gateway       OKX live        OKX sim                  │
│      (winclaw)        (API)           (API)                    │
└───────────────────────────────────────────────────────────────┘
```

### 设计原则

- **RiskGate 是下单路径唯一强制闸门** — 所有 `place_order` 必须先过 RiskGate
- **信号和下单解耦** — Agent 只负责生成信号，不下单；确认权在人
- **OrderManager 统一所有下单入口** — 现有散落的 place_order 逐步归并
- **advisory 模式保持兼容** — 现有 webhook/TradingView 路径只加风控日志，不拦截
- **本地可测** — 风控逻辑、信号 API、Agent adapter 均不依赖真实 IB 连接

---

## 三、模块设计

### 3.1 RiskGate — 风控闸门

**文件**：`trading/orders/risk_gate.py`（新增）

**规则来源**：

| 来源 | 规则 | 级别 |
|------|------|------|
| `quant-research/src/engine/risk_manager.py` | check_correlation、check_zscore、check_drawdown | 核心逻辑 |
| `quant-edge-pro/docs/00-expert-feedback.md` | 相关性熔断(<0.7)、三层 Z-Score(±3.0/±4.0) | 阈值规格 |
| `crypto_divergence/risk.py` | size_position() 按止损定仓、日亏损5%、杠杆3x | 加密货币专用 |

**五条规则**：

```python
class RiskGate:
    def __init__(self, config: RiskConfig):
        self.rules = [
            DailyLossBreaker(max_loss_pct=0.05),
            ExposureLimit(max_leverage=3.0),
            CorrelationBreaker(min_corr=0.7),
            ZScoreGuard(warn=3.0, critical=4.0),
            MaxPositionsGuard(max_open=3),
        ]
    
    def pre_check(self, ctx: OrderContext) -> RiskResult:
        """信号阶段预检 — Agent 提交信号时调用"""
        ...
    
    def final_check(self, ctx: OrderContext) -> RiskResult:
        """下单前最终校验 — 执行下单时调用"""
        ...
```

**两种模式**：

| 模式 | pre_check | final_check | 适用路径 |
|------|-----------|-------------|----------|
| `strict` | 全量规则，违规拦截 | 全量规则，违规拦截 | Agent 信号路径、OKX 策略 |
| `advisory` | — | 仅日志+飞书通知 | 现有 webhook/TradingView 路径 |

**接口**：

```python
@dataclass
class OrderContext:
    symbol: str
    action: str          # BUY/SELL
    quantity: float
    exchange: str        # IB/OKX
    zscore: Optional[float] = None
    correlation: Optional[float] = None
    hedge_ratio: Optional[float] = None
    equity: float = 0.0
    day_pnl: float = 0.0
    strategy: str = ""

@dataclass  
class RiskResult:
    allowed: bool
    reason: str = ""
    warnings: list = field(default_factory=list)
    severity: str = "normal"  # normal/warning/critical
```

### 3.2 信号 API

**载体**：`webhook_bridge.py` 注册新端点，`notify/signal_handler.py` 处理逻辑

**端点**：

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/signals` | Agent 提交交易信号 |
| POST | `/api/signals/<id>/confirm` | 人确认/拒绝执行 |
| GET | `/api/signals/<id>` | 查询信号状态 |

**POST /api/signals 请求体**：

```json
{
    "source": "quant-agent",
    "symbol": "FUL8.SHF",
    "direction": "long",
    "quantity": 1,
    "hedge_ratio": 0.68,
    "zscore": 2.1,
    "reason": "Z-Score突破+2.0上轨，协整强度82分",
    "strategy": "fu-lu-spread"
}
```

**信号生命周期**：

```
Agent POST → pending → RiskGate.pre_check() → reviewed → 飞书推送
                                                            │
                                            ┌───────────────┘
                                            ▼
                                    人回复"确认"
                                            │
                                            ▼
                                   RiskGate.final_check()
                                            │
                                            ▼
                                   OrderManager.place()
                                            │
                                            ▼
                                    executed → filled
```

**存储**：`trading/data/signals.jsonl`（追加写入，一行一个 JSON），24 小时过期自动 `expired`。

**飞书消息格式**：

```
🤖 [quant-agent] 交易信号

标的：FUL8.SHF → LUL8.INE
方向：做多价差（空 FU 多 LU）
Z-Score：+2.1（上轨突破）
协整强度：82分
对冲比率：0.68
建议仓位：1手

📊 风控预检：✅ 通过

回复「确认」执行 或「拒绝」放弃
```

### 3.3 Agent trading_adapter

**文件**：`quant-agent/tools/trading_adapter.py`（新增）

取代现有 `quant_core_adapter.py` 的 `place_order`/`close_position`（保留行情查询功能）。

```python
TRADING_URL = os.environ.get("TRADING_URL", "http://100.99.204.126:5002")

@tool("提交交易信号")
def submit_signal(direction, symbol, quantity, reason,
                  zscore=None, hedge_ratio=None):
    resp = requests.post(
        f"{TRADING_URL}/api/signals",
        json={...}, timeout=30
    )
    return json.dumps(resp.json())

@tool("查询信号状态")  
def check_signal(signal_id):
    resp = requests.get(
        f"{TRADING_URL}/api/signals/{signal_id}", timeout=15
    )
    return json.dumps(resp.json())
```

### 3.4 OrderManager — 统一订单入口

**文件**：`trading/orders/order_manager.py`（新增）

```python
class OrderManager:
    def place(self, ctx: OrderContext, gate_mode="advisory") -> OrderResult:
        """统一订单入口"""
        # 1. RiskGate.final_check(ctx, mode=gate_mode)
        # 2. 根据 ctx.exchange 路由到 ib_place() 或 okx_place()
        # 3. 记录订单日志
        # 4. 飞书通知执行结果
        # 5. 返回 OrderResult
    
    def cancel(self, order_id): ...
    def get_status(self, order_id): ...
    def get_open_orders(self): ...
```

**现有下单路径归并**：

| 文件 | 现有调用 | 改为 | gate_mode |
|------|---------|------|-----------|
| `webhook_bridge.py` (3处) | `place_order(ib, symbol, ...)` | `OrderManager.place(ctx)` | `advisory` |
| `okx_client/grid_bot.py` | 直接调 OKX SDK | `OrderManager.place(ctx)` | `strict` |
| `okx_client/macd_strategy.py` | 直接调 OKX SDK | `OrderManager.place(ctx)` | `strict` |
| `signal_handler.py` (新增) | — | `OrderManager.place(ctx)` | `strict` |

---

## 四、文件清单

### 新增文件

```
trading/
├── orders/
│   ├── risk_gate.py              # 风控闸门（5条规则）
│   └── order_manager.py          # 统一订单入口
├── notify/
│   └── signal_handler.py         # /api/signals 端点 + 飞书交互
├── data/
│   └── signals.jsonl             # 信号存储（运行时生成）
└── tests/
    ├── test_risk_gate.py          # 风控规则单元测试
    └── test_signal_api.py         # 信号 API 集成测试

quant-agent/
└── tools/
    └── trading_adapter.py         # submit_signal / check_signal
```

### 修改文件

```
trading/
├── orders/
│   └── place_order_func.py       # _place_order_impl() 接入 RiskGate + OrderManager
├── notify/
│   └── webhook_bridge.py         # 注册 3 个新端点，3处下单改走 OrderManager
├── okx_client/
│   ├── grid_bot.py               # 下单改走 OrderManager
│   └── macd_strategy.py          # 下单改走 OrderManager
└── config/
    └── settings.yaml             # 新增 risk_gate / order_manager 配置段

quant-agent/
└── tools/
    └── __init__.py               # 导出 trading_adapter 的 submit_signal/check_signal
```

---

## 五、实施步骤

| 步 | 内容 | 本地可测 | 产出 |
|----|------|---------|------|
| 1 | `risk_gate.py` + 单元测试 | ✅ | 5条规则独立跑通，Mock IB/OKX |
| 2 | RiskGate 接入 `place_order_func.py` + `okx_client` | ✅ | 现有 webhook 测试不变，风控日志可观测 |
| 3 | `order_manager.py` + 归并 6 处下单调用 | ✅ | 单一下单入口，所有测试通过 |
| 4 | `signal_handler.py` + `/api/signals` 三个端点 | ✅ | curl 可测完整信号流程 |
| 5 | `trading_adapter.py`（quant-agent 端） | ✅ | Agent 能 POST 信号到 trading |
| 6 | 飞书交互（确认/拒绝回调） | ⚠️ 需飞书 | webhook_bridge 已有飞书基础设施 |
| 7 | deploy to winclaw + IB 实盘验证 | ❌ 需 winclaw | 端到端一条链路跑通 |

---

## 六、测试策略

### 本地测试（macOS）

- **RiskGate 单元测试**：覆盖 5 条规则的 allowed/blocked 分支，Mock 账户状态
- **信号 API 集成测试**：用 Flask test client 测 POST/GET/confirm 全流程
- **OrderManager 测试**：Mock IB/OKX 连接，验证路由和重试逻辑
- **Agent adapter 测试**：Mock trading Flask 服务，验证请求格式

### winclaw 实盘测试

- 先 OKX sim 环境验证完整链路（不涉及真实资金）
- 再 IB paper trading 环境验证
- 最后切实盘

---

## 七、风险与缓解

| 风险 | 缓解 |
|------|------|
| 风控规则误拦截正常交易 | `advisory` 模式先跑日志观察 1 周再切 `strict` |
| OrderManager 重构破坏现有 webhook 路径 | 分步归并，每步验证 webhook_bridge 测试不变 |
| 飞书确认延迟导致信号过期 | 信号 24 小时过期自动失效，final_check 下单前再验 |
| winclaw 部署兼容性 | deploy-to-remote.sh 已覆盖 Windows 路径，新增文件在脚本内 |

---

## 八、未纳入本期范围

以下缺口已知但不纳入第一期：

- 跨交易所统一头寸/保证金视图（需设计 AccountAggregator）
- 回测参数→实盘配置自动化（cf-index-monitor 参数手动搬运）
- quant-edge-pro 的高密度 UI/全键盘交互（需前端重写）
- 策略 Marketplace 和 SaaS 分层（quant-edge-pro spec 远期规划）