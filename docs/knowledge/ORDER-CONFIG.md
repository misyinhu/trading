# Trading 下单配置手册

> 目标：一个新配对从"IB 里有合约"到"scanner 扫出信号、人确认后自动下单"的全链路配置指南。
>
> 最后更新：2026-08-25

---

## 一、配置层次全景

交易系统有 5 个必须配置的点，少了任何一个都会在下单时失败：

```
新配对 → [① exchange_mapper] → [② futures_set] → [③ strategy_registry]
              → [④ /api/quote]  → [⑤ pairs_scanner]
```

| # | 文件 | 作用 | 如果缺失 |
|---|------|------|---------|
| ① | `orders/exchange_mapper.py` | 告知系统标的在哪个交易所 | IB 找不到合约 |
| ② | `orders/place_order_func.py` | 告知系统是期货而非股票 | 期货被当作 STK → Error 162 |
| ③ | `orders/strategy_registry.py` | 策略注册 + 多腿展开 | 单腿执行，spread 配比错 |
| ④ | `notify/webhook_bridge.py` | /api/quote 支持查询该合约 | scanner 拉不到历史数据 |
| ⑤ | `scripts/pairs_scanner.py` | PAIRS 列表加入新配对 | scanner 扫不到 |

---

## 二、完整配置步骤

### Step 1：确认 IB 合约存在

先用脚本验证标的在 IB 上可查：

```python
# 在 winclaw 上运行
import ib_insync
ib_insync.util.patchAsyncio()
from ib_insync import IB, Contract

ib = IB()
ib.connect('127.0.0.1', 4002, clientId=990, timeout=10)

# 查询合约
con = Contract(symbol='HSTECH', secType='FUT', exchange='HKFE', currency='HKD')
details = ib.reqContractDetails(con)
print(f"{len(details)} contracts found")
for d in details[:3]:
    c = d.contract
    print(f"  conId={c.conId} symbol={c.symbol} exchange={c.exchange} "
          f"exp={c.lastTradeDateOrContractMonth} mult={c.multiplier}")

# 拉历史数据
bars = ib.reqHistoricalData(con, endDateTime='',
    durationStr='10 D', barSizeSetting='1 day',
    whatToShow='TRADES', useRTH=False, formatDate=1)
print(f"Bars: {len(bars)}")

ib.disconnect()
```

**必须同时确认三点：**
1. `reqContractDetails` 返回合约
2. 合约的 `exchange` 值（如 HKFE, NYMEX, CME）
3. `reqHistoricalData` 返回数据（不是空列表）

> **关键**：不同品种的 `exchange` 必须完全匹配 IB 返回的值，否则 `reqContractDetails` 返回空。

---

### Step 2：加入 exchange_mapper（①）

文件：`orders/exchange_mapper.py`

在 `DEFAULT_FUTURES_EXCHANGES` 字典中加入：

```python
# 港股期货 (HKFE)
'HSI': 'HKFE', 'HSTECH': 'HKFE', 'MHI': 'HKFE',
```

格式：`'SYMBOL': 'EXCHANGE_CODE'`

如果品种不在表里，会 fallback 到 `CME`，导致 IB 找不到合约。

---

### Step 3：加入 futures_set（②）

文件：`orders/place_order_func.py`

找到 `futures_set`，加入新期货 symbol：

```python
futures_set = {
    # 贵金属
    'GC', 'SI', 'HG', 'MGC', 'PL', 'PA',
    # 能源
    'CL', 'NG', 'QM', 'RB', 'HO', 'MCL',
    # 股指
    'ES', 'NQ', 'MNQ', 'MES', 'RTY', 'YM', 'MYM',
    # 农产品
    'ZC', 'ZW', 'ZS', 'ZM', 'ZL', 'KC', 'CT', 'SB', 'CC',
    # 港指
    'HSI', 'HSTECH', 'MHI',   # ← 新增
}
```

**为什么需要这个集合？** IB 下单时如果 secType 设为 "FUT" 但 symbol 不在 `futures_set` 里，系统会改用 "STK" 类型下单，导致 Error 162（不能做空/不合法的合约）。

---

### Step 4：更新 /api/quote 的交易所过滤（④）

文件：`notify/webhook_bridge.py` 第 1862 行附近

`/api/quote` 在选合约时用 `exchange in ('NYMEX', 'CME', 'CBOT', 'COMEX', 'NYBOT')` 过滤。

如果新合约在 **HKFE**，需要加入：

```python
candidates = [d.contract for d in details
             if d.contract.exchange in ('NYMEX', 'CME', 'CBOT',
                                          'COMEX', 'NYBOT', 'HKFE')  # ← 加 HKFE
             and d.contract.lastTradeDateOrContractMonth
             and d.contract.lastTradeDateOrContractMonth >= '202609']
```

> **注意**：`reqContractDetails` 会返回同一品种的多个到期月合约，系统选最近到期（`lastTradeDateOrContractMonth >= 202609`）。如果当月合约已到期，这个过滤会自动跳到下月合约。

---

### Step 5：加入 strategy_registry（③）

文件：`orders/strategy_registry.py`

**通用配对策略 `pairs-spread`** 已支持动态多腿展开，新增配对只需在 `pairs_scanner.py` 的 `PAIRS` 列表里定义，不需要单独注册新策略（除非配比逻辑特殊）。

如果是完全不同的配对类型（如 calendar spread 跨月价差），才需要新增策略处理分支：

```python
# 在 build_order_contexts() 中加入
elif spec.strategy_name == 'custom-spread':
    legs = signal.get('legs', [])
    contexts = []
    for leg in legs:
        sym = leg['symbol']
        action = leg.get('action', 'BUY').upper()
        qty = leg.get('quantity', 1.0)
        contexts.append(OrderContext(
            symbol=sym, action=action, quantity=qty,
            exchange=exchange_mapper.get_exchange_for_symbol(sym, 'FUT')
        ))
    return contexts
```

---

### Step 6：加入 pairs_scanner PAIRS 列表（⑤）

文件：`scripts/pairs_scanner.py`

在 `PAIRS` 列表末尾加入：

```python
# 港股指数
{
    "name": "HSTECH_HSI",
    "strategy": "pairs-spread",
    "legs": [
        {"symbol": "HSTECH", "ratio": 1.0},   # ratio > 0: long 时买
        {"symbol": "HSI",     "ratio": -1.0},  # ratio < 0: long 时卖
    ],
    "unit": "points",
    "description": "Hang Seng Tech vs Hang Seng Index",
    "type": "spread",    # spread = 直接相减, ratio = 相除
},
```

**`type` 说明：**
- `spread`：spread = leg1_price × ratio1 + leg2_price × ratio2 + ...
- `ratio`：`ratio = leg1_price / leg2_price`
- `crack`：3:2:1 之类的复杂 crack spread

**`ratio` 符号约定：**
- `ratio > 0` 的 leg：long 方向 → BUY，short 方向 → SELL
- `ratio < 0` 的 leg：long 方向 → SELL，short 方向 → BUY

---

## 三、信号提交格式

Scanner 提交信号到 `/api/signals`，payload 格式：

```json
{
  "source": "pairs-scanner",
  "strategy": "pairs-spread",
  "direction": "short",
  "symbol": "PL_PA_ratio",
  "quantity": 1.0,
  "zscore": 2.1,
  "legs": [
    {"symbol": "PL", "action": "SELL", "ratio": 1.0, "quantity": 1.0},
    {"symbol": "PA", "action": "BUY",  "ratio": -1.0, "quantity": 1.0}
  ],
  "reason": "[AUTO] PL_PA_ratio Z=2.10 → short spread=606.7",
  "pair_stats": {
    "zscore": 2.10,
    "mean": 466.55,
    "std": 54.11,
    "last": 606.7,
    "leg_prices": {"PL": 1881.2, "PA": 1344.5}
  }
}
```

**关键字段：**
- `strategy: "pairs-spread"` → 触发通用多腿处理
- `legs[]` → 每条腿的 action，展开为独立下单
- `zscore` → RiskGate ZScoreGuard 告警阈值（±3.0 告警，±4.0 熔断）

---

## 四、风控闸门（RiskGate）

配置文件：`config/settings.yaml` → `risk_gate` 段

```yaml
risk_gate:
  max_daily_loss_pct: 0.05    # 日亏 ≥ 5% → 拒绝
  max_leverage: 3.0           # 杠杆 > 3x → 拒绝
  min_correlation: 0.7         # 相关性 < 0.7 → 拒绝
  zscore_warn: 3.0            # Z-Score ±3.0 → 飞书告警（不拒绝）
  zscore_critical: 4.0        # Z-Score ±4.0 → 拒绝
  max_open_positions: 3       # 持仓数 ≥ 3 → 拒绝
```

**双模式：**
- `strict`：违规 → 拒绝下单（Agent 信号、OKX 策略）
- `advisory`：违规 → 仅日志+告警（TV webhook、feishu NL 下单）

---

## 五、半自动 vs 全自动

| 模式 | 触发方式 | 信号状态 | 需要人工 |
|------|---------|---------|---------|
| 半自动（默认） | 不带 `auto` 参数 | `reviewed` → 飞书推送 → 人回复「确认」| ✅ |
| 全自动 | 带 `auto=true` 且 source 在白名单 | `executed` 直接执行 | ❌ |

白名单：`AUTO_EXECUTE_WHITELIST = {"quant-agent", "smoke-test"}`

---

## 六、常见失败原因及排查

| 错误 | Error 现象 | 根因 | 修复 |
|------|-----------|------|------|
| Error 162 | 下单返回 Error 162 | `futures_set` 缺少该 symbol，被当作 STK | 加到 `futures_set` |
| Error 200 | contract not found | exchange 写错或不匹配 IB 返回值 | 确认 `exchange_mapper` 值 |
| hist_count=0 | /api/quote 返回空 | ① exchange 不在过滤列表 ② `ib.disconnect()` 断连接 ③ IB session 冲突 | 见本文 Step 4 |
| Error 326 | clientId already in use | 多个 IB 连接用同一 clientId | 只用 Flask clientId=999，其他进程用独立 clientId |
| 信号 review 但不下单 | 人确认后无响应 | RiskGate final_check 拒绝 | 检查 risk_gate 配置和当日亏损 |
| 多腿只下一条 | PAIRS 有两条腿但只成交一条 | `strategy_registry` 没有 `pairs-spread` 分支 | 确认 `build_order_contexts` 处理了 legs |

---

## 七、已验证的配对清单

| 配对 | 类型 | 交易所 | 状态 |
|------|------|--------|------|
| RB/CL (3:2 crack) | crack | NYMEX | ✅ |
| HO/CL (3:1 diesel) | crack | NYMEX | ✅ |
| GC/SI (ratio) | ratio | COMEX | ✅ |
| PL/PA (ratio) | ratio | NYMEX | ✅ 已实盘 |
| ZC/ZS (spread) | spread | CBOT | ✅ |
| ZL/ZS (spread) | spread | CBOT | ✅ |
| ES/NQ (spread) | spread | CME | ✅ |
| HSTECH/HSI | spread | HKFE | ✅ 配置完成 |
| MNQ/MYM | spread | CME/CBOT | ✅ |
