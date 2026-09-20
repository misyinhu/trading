# 行情/交易系统架构与端口拓扑（权威文档）

> 最近更新：2026-09-19（5006 实盘网关与 5002 仿真桥解耦）。
> 事实源 = 各主机实测；与旧文档/注释冲突时以本文为准。
> 部署细节见 `winclaw-deploy-runbook.md`；CTP 行情见 `ctp-md-realtime-spec.md`（quant-agent 仓 `docs/`）；
> 报单契约见 `ctp-simnow-api.md` 与 `contracts/webhook_bridge.openapi.yaml`。

## 1. 顶层边界：三套钱，三条通道

| 通道 | 性质 | 唯一入口 | 资金 |
|---|---|---|---|
| **实盘（live）** | 真实资金，人工报/撤单，agent 不得自动下单 | **winclaw `:5006` live-gateway** | IB live U 账户 / CTP 投资者 821350082（中信标准协议） |
| **仿真（sim）** | 全部模拟账户，策略/页面自动执行 | 模拟桥 `:5002`（winclaw 本机，cxclaw 有冗余副本） | SimNow 274467 / 中信仿真 7108804861 / gm / OKX demo / IB paper |
| **行情（market data）** | 只读，无报单 | quant-core `:8005`、CTP md `:5003/5004`、data cabinet | — |

铁律：
- **`:5002` 是纯仿真桥**：`profile` 只接受 `simnow/citic`，传 `live` 返回 `400 bad_profile`（2026-09-19 收口，fail-closed，绝不静默回落仿真前置）。
- **`:5006` 是唯一实盘入口**：不代理 5002；CTP 请求由网关内子进程直连 `ctp_client/ctp_worker.py` 并在服务端强制 `CTP_PROFILE=live`，请求里伪造的 `profile/account` 一律剥离。
- 所有实盘写操作（报单/撤单）必须带头 `X-Real-Money: CONFIRM` + 过 quant-agent 侧实盘合规门（账户号二次确认 + REAL MONEY + kill switch + 净敞口 + 审计 + 飞书）。只读 GET 不需要该头。

## 2. 主机与进程拓扑

```
┌─────────────────────── winclaw (Windows, 100.99.204.126, Tailscale) ───────────────────────┐
│                                                                                            │
│  IB Gateway(TWS)                    CTP 交易前置                     CTP 行情前置             │
│   4001 live  (U8590961)             180.169.101.177:43205 (live)    simnow/中信 md front     │
│   4002 paper ─────────────┐          中信仿真前置                    │                        │
│                           │                                             │                        │
│  :5006 live_gateway       │      :5002 webhook_bridge (PM2 trading-bridge)   :5003 md-simnow │
│   live_gateway_app.py     │       notify/webhook_bridge.py (Flask)         :5004 md-citic    │
│   ├ IB → 直连 4001        │       ├ CTP profile=simnow/citic 子进程                            │
│   └ CTP → ctp_worker 子进程│       ├ gm 模拟子进程  ├ OKX demo  ├ IB paper(4002)                │
│        (CTP_PROFILE=live) │       └ TV/飞书 webhooks                                            │
│        SWIG 6.7.11.1       │                                                                    │
│                            │                                                                    │
│  :8005 quant-core (FastAPI, quant_core)  历史/实时行情聚合（IB HMDS 农场等）                     │
│  :8507 trading kanban (Streamlit, 手动)                                                          │
│  TradingView CDP :9224（便携 TV）  通达信 TdxW                                                    │
└────────────────────────────────────────────────────────────────────────────────────────────┘
          ▲ Tailscale 内网
          │
┌─────────┴──────────────────────────── quant-agent（Mac，本机） ────────────────────────────┐
│ Streamlit dashboard :8506  ──HTTP──▶  spine 代理 :5003*  (run_system.py / quant_agent_flask) │
│                                        │  按 profile/venue 分流：                              │
│                                        │   live / ib_live → 100.99.204.126:5006               │
│                                        │   simnow/citic/gm/okx/ib paper → trading.url(5002)   │
│                                        │   行情 → 100.99.204.126:8005 / md 5003/5004           │
│  tools/trading_adapter.py（CTP/gm/OKX/IB 仿真 + ctp_live 实盘合规门）                          │
│  tools/ib_live_adapter.py（IB 实盘报单/撤单/只读，独立门）                                      │
│  config/services.yaml = 地址唯一事实源（live_gateway / ctp_live / trading / ctp_md）           │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

\* 注意端口 5003 在两台机器上含义不同：winclaw 的 **5003=CTP simnow 行情 worker**；
Mac 本地的 **5003=quant-agent spine HTTP 代理**（只监听 127.0.0.1）。两者不在同一主机，不冲突。

cxclaw（`100.82.238.11`）：`:5002` 仿真桥冗余副本、`:8005` quant-core 冗余、`:5003/5004` md worker。
`config/services.yaml` 的 `trading.url` 指向哪台，仿真流量就走哪台；**实盘永远固定 winclaw 5006，不随该配置切换**。

## 3. 端口表

| 端口 | 主机 | 服务 | 读/写 | 备注 |
|---|---|---|---|---|
| **5006** | winclaw | **live-gateway 实盘唯一入口** | IB/CTP 只读 + 人工写实盘 | Python313 `live_gateway/live_gateway_app.py`；无保活计划任务，手动/脚本重启 |
| 5002 | winclaw | 仿真桥 webhook_bridge | 仿真读写 + webhook | PM2 进程 `trading-bridge`（事实托管方式；`health_check.bat`/`TradingHealthCheck` 兜底）；仅 simnow/citic |
| 5002 | cxclaw | 仿真桥冗余副本 | 同上 | cxclaw 部署，未做 live 收口同步（无实盘流量） |
| 8005 | winclaw/cxclaw | quant-core 行情/数据 API | 只读 | ONLOGON `StartQuantServer` + `TradingHealthCheck` 15min 保活；无 `/health`（`/docs` 200） |
| 5003 | winclaw | CTP md worker（simnow，SWIG 6.7.11.1） | 只读 SSE/快照 | 2026-09-19 因 simnow 绑定原生 abort（累计重启 3416 次）**pm2 stop**，FU 卡回退 gm；待绑定修复 |
| 5004 | winclaw/cxclaw | CTP md worker（citic 仿真，6.5.1_CP） | 只读 | 非交易时段卡 logining 属正常；周一 09:30 IC 验收 |
| 4001/4002 | winclaw | IB Gateway live / paper | 本机 | 计划任务 `IBGW` ONLOGON |
| 8507 | winclaw | trading kanban | — | 手动起，无自启 |
| 8506 | Mac | quant-agent dashboard | 本机 | launchd `com.quant.streamlit8506` |
| 5003 | Mac(127.0.0.1) | quant-agent spine 代理 | 本机 | launchd `com.quant.spine5001`（历史名，实际绑 5003） |
| 8505/5001/8504 | winclaw | life-compass（他系统） | — | trading 红线：不得占用/探活 |

## 4. 5006 live-gateway 接口（2026-09-19 起）

IB live（账户由网关注册表里有资金的 U 账户，默认 U8590961）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | IB 连接 + managed accounts |
| GET | `/api/ib/live/account` `/positions` `/orders` `/trades` | 资金 / 持仓 / 活动委托(openTrades) / 会话成交(fills) |
| POST | `/api/ib/live/order` `/cancel` | 人工报单/撤单，需 `X-Real-Money: CONFIRM` |

CTP live（服务端强制 profile=live，查询 10s 短缓存，订单/成交不缓存）：

| 方法 | 路径 | worker action |
|---|---|---|
| GET | `/api/ctp/account` `/positions` | `query` |
| GET | `/api/ctp/orders` | `trades`（只回 orders） |
| GET | `/api/ctp/trades` | `trades`（orders + trades） |
| GET | `/api/ctp/depth` `/instruments` `/main-contract` `/main-board` | 同名 action |
| POST | `/api/ctp/order` `/cancel` | 报单/撤单，需确认头；超时→503 timeout，原生崩溃→503 crashed |

未知 `/api/ctp/*` 路径一律 **404，不存在透传兜底**。

## 5. 子进程隔离模型（为什么不会被原生库拖垮）

- CTP SWIG 绑定（`.pyd`）会在原生线程无栈 abort；因此 **worker 永远以独立子进程运行**：
  `python -u ctp_client/ctp_worker.py`，环境变量 `CTP_PROFILE / CTP_ACTION / CTP_ORDER_JSON / CTP_TIMEOUT`，
  stdout 收 `RESULT_JSON=...`，解析不到即判 `crashed`（exit≠0）。
- 5002 的 `_ctp_snapshot/_ctp_run_action`（`notify/webhook_bridge.py`）与 5006 的 `_ctp_worker()`
  是同一模式的两份独立实现（刻意不互 import，避免 Flask/仿真依赖进入实盘网关）。
- **绑定版本硬约束**：simnow/live 标准协议 = `C:\tmp\ctp_api\ctp_swig_build-6.7.11.1`；
  中信评测/仿真(66666) = `...6.5.1cp`。版本错配表现为前置握手 `4040 decode err`。
- 一个进程只能加载一套 SWIG：simnow md 与 citic md 必须分进程（5003/5004）。
- 交易 worker 即连即断：每次 action 建 TraderApi、结束 `Release()` 退出，无常驻会话。
- 实盘凭证（`LIVE_CTP_*`）只存 winclaw（环境变量或 `.streamlit/secrets.toml`），Mac 侧不保存任何实盘密钥。

## 6. quant-agent 侧调用约定

- 地址事实源：`config/services.yaml`（`live_gateway.url` / `ctp_live.url` / `trading.url` / `ctp_md.*`），
  均可被同名环境变量覆盖；代码在 `core/config.py` 装配。
- 分流规则（`tools/trading_adapter.py`）：`profile=live` → 5006 且自动加实盘确认头；
  `simnow/citic` → `TRADING_URL`(5002)；gm/okx/ib paper → 5002 对应路由。
- IB 实盘单独走 `tools/ib_live_adapter.py`（`LIVE_GATEWAY_URL`，报单/撤单/只读三个用途）。
- dashboard 不直连云端：统一打本机 spine（127.0.0.1:5003），spine 路由：
  `/api/trading/ctp/*`、`/api/trading/ib-live/*`（orders/trades/order/cancel）。
- 实盘合规门（两重，云端 5006 头校验是最后兜底）：
  账户号确认 + `REAL MONEY` 短语 + kill switch + 净敞口 pre-trade + 审计 jsonl + 飞书通知；
  撤单只减风险，不做净敞口门、kill switch 下仍允许撤（逃生通道），但确认/审计/通知不省。

## 7. 运维要点

- 重启 5006：`live_gateway/start_live_gateway.ps1`（2026-09-19 起先停端口旧 PID 再启动，Python313 绝对路径）。
- 重启 5002：winclaw 上 **`npx pm2 restart trading-bridge --update-env`**（PM2 是事实托管方；
  不要手工 `start webhook_bridge.py`，会产生多个监听同一端口的孤儿进程，2026-09-19 已清理过一次）。
- 只读验活（不需确认头）：5006 `/health`、`/api/ib/live/orders`、`/api/ctp/account`；
  5002 `?profile=live` 必须回 `bad_profile`，`?profile=citic` 应正常。
- CTP 实盘/仿真登录前置在休市时段 TCP 通但不完成握手 → worker 表现为 30s `timeout`，属环境问题非故障；
  夜盘开放（约 20:45）/ 工作日 09:00 后复验。
- 看门狗边界：`TradingHealthCheck` 只保 trading 的 5002/8005；5006 暂不纳入自动拉起（实盘入口刻意人工掌控）；
  life-compass 的 MedalWatchdog 与 trading 互不交叉。
