# CTP / SimNow 交易接口文档

> 面向程序化交易合规接入的**期货仿真（SimNow/CTP）**接口。真实下单、撤单、查询均
> 经云端 trading 桥（Flask，`:5002`）转发到中信期货 SimNow 仿真柜台。
>
- **环境**：SimNow 仿真柜台（账号 `274467`，仿真资金，无真实风险）。
- **隔离**：CTP SWIG 原生层（仅 cp313）在**独立子进程 worker** 中运行；原生崩溃只杀
  子进程，绝不拖垮 Flask 主服务。
- **合规**：本通道为**非看穿式 / 仿真**（`ctp_sim`，`audit_only`）。正式看穿式
  （AppID/AuthCode/RelayAPPID/终端 IP/MAC）为 `ctp_live` 预留，待向期货公司报备后启用。
- **调用方**：quant-agent `tools/trading_adapter.py` 会先过本地合规风控门再调这些接口。

## 基础信息

| 项 | 值 |
|---|---|
| Base URL | `http://100.99.204.126:5002`（云端 winclaw）|
| 内容类型 | `application/json` |
| 报单/撤单超时 | 60s（子进程：登录→结算→请求→等回报）|
| 账户/持仓缓存 | 20s，`?force=1` 跳过缓存强制重登重查 |

## 接口清单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 服务健康（含 simnow 组件状态）|
| GET | `/api/ctp/account` | 账户权益/可用/保证金/冻结 |
| GET | `/api/ctp/positions` | 当前持仓 |
| POST | `/api/ctp/order` | 报单（限价）|
| POST | `/api/ctp/cancel` | 撤单 |
| GET | `/api/ctp/instruments` | 品种全部可交易合约月份 |
| GET | `/api/ctp/main-contract` | 按持仓量(OI)判定的主力合约 + 行情 |

---

## 1. 健康检查

`GET /health`

返回各组件状态。`components.simnow.status`：`standby`（空闲，按需触发）/
`logined` / `disabled`（`simnow.enabled=false`）。

## 2. 查询账户

`GET /api/ctp/account[?force=1]`

```json
{
  "status": "logined",
  "investor": "274467",
  "trading_day": "20260901",
  "account": {
    "account_id": "274467",
    "balance": 21002561.61,
    "available": 20813532.63,
    "margin": 0.0,
    "frozen_margin": 0.0,
    "position_pnl": 0.0,
    "close_pnl": 3719.99,
    "commission": 1158.39,
    "currency": "CNY"
  }
}
```

## 3. 查询持仓

`GET /api/ctp/positions[?force=1]`

```json
{
  "status": "logined",
  "count": 1,
  "positions": [
    {"symbol": "IC2609", "direction": "", "volume": 2,
     "avg_price": 3117080.0, "float_pnl": 760.0}
  ]
}
```

## 4. 报单

`POST /api/ctp/order`

**请求体**

| 字段 | 必填 | 说明 |
|---|---|---|
| `instrument_id` | 是 | 合约代码，如 `IC2609`（具体月份，非主力连续）|
| `exchange_id` | 推荐 | 交易所，如 `CFFEX` / `SHFE` / `DCE` / `CZCE` / `INE` |
| `direction` | 是 | `0` 买 / `1` 卖 |
| `offset_flag` | 是 | `0` 开仓 / `1` 平仓 / `3` 平今 / `4` 平昨 |
| `price` | 限价必填 | 限价（`price_type=2` 时必须 > 0，且为 tick 整数倍）|
| `volume` | 是 | 手数（正整数，受合规门 `max_qty` 约束）|
| `price_type` | 否 | `2` 限价（默认）/ `1` 市价 |
| `hedge_flag` | 否 | `1` 投机（默认）|

**请求示例**

```bash
curl -X POST http://100.99.204.126:5002/api/ctp/order \
  -H "Content-Type: application/json" \
  -d '{"instrument_id":"IC2609","exchange_id":"CFFEX",
       "direction":"0","offset_flag":"0","price":7800.0,"volume":1}'
```

**返回（关键字段在 `action_result`）**

```json
{
  "ok": true,
  "action": "order",
  "status": "accepted",
  "trading_day": "20260901",
  "front_id": 1,
  "session_id": 2042240634,
  "action_result": {
    "ok": true,
    "status": "accepted",
    "order_ref": "44479018",
    "order_sys_id": "442669",
    "front_id": 1,
    "session_id": 1912980454,
    "exchange_id": "CFFEX",
    "order_status": "3",
    "volume_traded": 0
  },
  "order_events": [ {"order_ref": "...", "status": "a", "status_msg": "报单已提交", "...": "..."} ],
  "trade_events": [ {"order_ref": "...", "price": 7802.0, "volume": 2, "...": "..."} ]
}
```

**`action_result.status` 取值**

| status | 含义 |
|---|---|
| `accepted` | 已挂单（未成交，状态 3）|
| `partial` | 部分成交（状态 1）|
| `filled` | 全部成交（状态 0）|
| `canceled` | 已撤（状态 5，且非拒绝）|
| `rejected` | 被拒（`error` 含柜台错误原文）|

> 撤单/下单后若 6s 内无终态回报，返回当前状态（`order_events`/`trade_events` 仍含已收回报）。

## 5. 撤单

`POST /api/ctp/cancel`

可**只传 `order_ref` + `instrument_id`**：worker 会先 `ReqQryOrder` 查当日委托，
自动补全该挂单的 `FrontID/SessionID/OrderSysID` 再撤。

**方式 A（推荐，跨连接可靠）**：报单返回的三要素

```json
{"instrument_id":"IC2609","exchange_id":"CFFEX",
 "order_ref":"44530938","front_id":1,"session_id":1916388976}
```

**方式 B（只给 order_ref，自动查补）**

```json
{"instrument_id":"IC2609","exchange_id":"CFFEX","order_ref":"44530938"}
```

**方式 C（备选）**：交易所系统号

```json
{"instrument_id":"IC2609","exchange_id":"CFFEX","order_sys_id":"443747"}
```

> ⚠️ SimNow 跨连接用 `OrderSysID` 撤单偶发 `[25] 撤单找不到相应报单`；实现上优先用
> `FrontID + SessionID + OrderRef` 三要素，`OrderSysID` 仅作备选。

**返回**：`action_result.status` = `canceled`（成功）或错误；`order_events` 通常为
`["3","5"]`（未成交 → 已撤）。

## 6. 合约列表

`GET /api/ctp/instruments?product=IC&exchange=CFFEX`

返回该品种全部可交易月份（合约乘数、最小变动价位、到期日、是否可交易）。

## 7. 主力合约（按持仓量判定）

`GET /api/ctp/main-contract?product=IC&exchange=CFFEX`

研究/监控层用**主力连续**（如天勤 `KQ.m@CFFEX.IC`），但柜台报单必须用**具体月份**
（`IC2609`）。下单前先用本接口解析。

判定逻辑：查可交易月份 → 逐合约查行情深度 → **OpenInterest（持仓量）最大**者为主力；
行情缺失时回退“最近到期可交易”，并用 `main_by` 标注。

```json
{
  "ok": true,
  "product": "IC",
  "exchange": "CFFEX",
  "main_by": "open_interest",
  "main_contract": {"instrument_id": "IC2609", "open_interest": 149793,
                    "last_price": 7801.6, "lower_limit": 7098.0, "upper_limit": 8675.2,
                    "volume_multiple": 200, "price_tick": 0.2, "...": "..."},
  "front_contract": {"instrument_id": "IC2609", "...": "..."},
  "tradable_count": 4,
  "instruments": [
    {"instrument_id": "IC2609", "open_interest": 149793, "volume": 100753,
     "last_price": 7801.6, "lower_limit": 7098.0, "upper_limit": 8675.2},
    {"instrument_id": "IC2612", "open_interest": 92810,  "...": "..."}
  ]
}
```

返回的 `lower_limit`/`upper_limit`/`last_price` 可用于挂单价合理性校验。

---

## quant-agent 适配方法

`tools/trading_adapter.py`（均**先过合规风控门**，回报回写审计日志）：

| 方法 | 对应接口 |
|---|---|
| `main_ctp_instrument_id("IC", "CFFEX")` | 取主力合约代码（如 `"IC2609"`）|
| `resolve_ctp_main_contract("IC", "CFFEX")` | 完整主力结构（含各月 OI/行情）|
| `submit_ctp_order(instrument_id, exchange_id, direction, offset_flag, price, volume, ...)` | 报单 |
| `cancel_ctp_order(instrument_id, exchange_id, order_ref=..., front_id=..., session_id=...)` | 撤单 |

典型用法：

```python
from tools import trading_adapter as ta

iid = ta.main_ctp_instrument_id("IC", "CFFEX")     # "IC2609"
res = ta.submit_ctp_order(iid, "CFFEX",
                          direction="0", offset_flag="0",
                          price=7800.0, volume=1, strategy="ic_divergence")
```

## 合规风控门（quant-agent 侧）

- 通道 `ctp_sim`（内盘期货符号 `.SHF/.CFF/.DCE/.CZCE/.INE`）= `audit_only`：
  - **硬校验始终拦截**（fail-closed，任何模式）：合约白名单（`config/compliance.yaml`
    按品种 `product` 匹配）、最小变动价位 tick、单笔最大手数、kill switch。
  - **频率阈值**（1s/10s/60s/当日 报单/撤单笔数）在仿真通道只监测留痕+预警，不拦截。
- 已登记品种：上期所 `AU/AG/CU`；中金所 `IC/IF/IH/IM`（股指 tick 0.2、涨跌停 ±10%）。
  白名单外品种（如 `rb`）判 `unknown_contract` 拒单。

## 常见柜台错误

| 错误 | 含义 | 处理 |
|---|---|---|
| `26 ... 当前状态禁止此项操作` | 非交易时段 | 交易时段重试 |
| `50 ... 价格跌破跌停板` / 涨破涨停 | 价格越界 | 参考 `lower/upper_limit` 调价 |
| `[25] 撤单找不到相应报单` | sysid 跨连接撤单失败 | 改用 order_ref 三要素撤单 |

## 限制与后续

- 仿真环境；正式看穿式（`ctp_live`）AppID/AuthCode/RelayAPPID/终端信息待期货公司下发。
- 报单当前以限价为主；市价单 `price_type=1` 视柜台支持。
- 中金所股指日内/隔夜规则（如 14:55 前强平）在策略层控制，不在本接口。

---

# 掘金量化（gm）A 股模拟交易接口

> 掘金量化「我的掘金终端」提供平台内模拟撮合，覆盖 **A 股个股 + 期货**，不碰真实资金。
> 与 CTP 同风格、同样走子进程隔离，但 SDK 为 Python `gm`（需独立 venv，因其 pin
> `protobuf<4`，会与 streamlit 冲突）。依赖本地掘金终端运行（服务 `localhost:7001`）。

## 基础信息

| 项 | 值 |
|---|---|
| 接口前缀 | `/api/gm/*` |
| 运行环境 | 独立 venv `C:\projects\gm_env`（`gm==3.0.186`）|
| 终端服务 | 本地掘金终端 `localhost:7001`（终端须登录运行）|
| 凭证 | `.streamlit/secrets.toml`：`GM_TOKEN` / `GM_ACCOUNT`（模拟账户 UUID）/ `GM_SERV_ADDR` |
| 隔离 | gm 原生层在独立子进程 `run(mode=1)` 框架内，结果经临时文件 `GM_RESULT_FILE` 回传 |
| 缓存 | 账户/持仓 20s，`?force=1` 跳过 |

## 接口清单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/gm/account` | 模拟账户资金（净值/可用/持仓市值/冻结/盈亏）|
| GET | `/api/gm/positions` | 当前持仓 |
| POST | `/api/gm/order` | 下单（限价/市价，买/卖，开/平）|
| POST | `/api/gm/cancel` | 撤未成交委托（按 symbol，省略撤全部）|

## 1. 查询账户

`GET /api/gm/account[?force=1]`

```json
{
  "status": "logined", "channel": "gm",
  "account": {
    "account_id": "0080a3eb-a5df-11f1-a7e7-00163e022aa6",
    "balance": 1000000.0, "available": 1000000.0,
    "market_value": 0.0, "frozen": 0.0,
    "pnl": 0.0, "fpnl": 0.0, "currency": "CNY"
  }
}
```

## 2. 查询持仓

`GET /api/gm/positions[?force=1]` → `{"positions":[...],"count":N,"channel":"gm"}`。

## 3. 下单

`POST /api/gm/order`

| 字段 | 必填 | 说明 |
|---|---|---|
| `symbol` | 是 | 交易所代码，如 `SHSE.600000`（浦发银行）、`SZSE.000001`；期货如 `CFFEX.IC2609` |
| `side` | 是 | `1` 买 / `2` 卖 |
| `volume` | 是 | 数量（A 股股票 ≥100 股；期货为手数）|
| `order_type` | 否 | `1` 限价（默认）/ `2` 市价 |
| `position_effect` | 否 | `1` 开仓（默认）/ `2` 平仓（期货用；股票自动同净持仓方向）|
| `price` | 限价必填 | 限价（`order_type=1` 时给 >0）|

请求示例：

```bash
curl -X POST http://100.99.204.126:5002/api/gm/order \
  -H "Content-Type: application/json" \
  -d '{"symbol":"SHSE.600000","side":1,"volume":100,"order_type":1,"position_effect":1,"price":10.5}'
```

返回 `action_result` 含 `cl_ord_id` / `symbol` / `side` / `price` / `volume` /
`filled_volume` / `status` / `ord_rej_reason_detail`（被拒原因）。

## 4. 撤单

`POST /api/gm/cancel`，Body：`{"symbol":"SHSE.600000"}`（按标的撤该账户未成交委托；
省略 symbol 撤全部）。返回 `{"status":"cancel_submitted","cancelled":N}` 或
`"nothing_to_cancel"`。

## 注意事项

- 仅在 **A 股交易时段**（工作日 9:30–11:30 / 13:00–15:00）下单会真实进入模拟撮合；
  非交易时段远价单会被终端拒绝/不留存（已验证 `order_volume` 提交成功返回委托）。
- 掘金终端必须在 winclaw 上保持登录运行；终端服务地址默认 `localhost:7001`。
- gm SDK 裸调 `get_cash/order_volume`（不走 `run()` 框架）会在原生层阻塞退出，
  务必使用 `gmsim_worker.py` 的 `run(mode=1)` 回调模式。
- 部署见 `gm_client/README.md`（建 venv → `pip install gm` → 复制 worker → 配 secrets）。
