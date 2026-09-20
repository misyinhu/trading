# verified-facts

> 本文件是 QA 与 DEV 的唯一事实源。所有验证结果必须记录在此。
> 
> **参考**：PMO 治理框架定义见 [pmo/docs/role-qa.md](../../../../pmo/docs/role-qa.md)

---

## 验收事实

### Feature 3: TradingView Webhook

| # | 事实 | 验证方式 | 状态 | 验证时间 |
|---|------|---------|------|---------|
| 1 | GET /health 返回 200，status=ok | TC-WH-001 | ✅ | 2026-05-10 |
| 2 | POST /tv-webhook 买入信号返回 order.code=0 | TC-WH-101 | ✅ | 2026-05-10 |
| 3 | POST /tv-webhook 卖出信号返回 order.code=0 | TC-WH-102 | ✅ | 2026-05-10 |
| 4 | POST /feishu-webhook 解析 NL 命令返回正确 order 格式 | TC-WH-201 | ✅ | 2026-05-10 |

### Feature 1: OKX 行情对接

| # | 事实 | 验证方式 | 状态 | 验证时间 |
|---|------|---------|------|---------|

### Feature 2: IB 交易执行

| # | 事实 | 验证方式 | 状态 | 验证时间 |
|---|------|---------|------|---------|
| 1 | IB Gateway :4002 连接正常 | TC-IB-001 | ✅ | 2026-08-25 |
| 2 | IB paper 账户可查询 CL/RB/GC/ES/NQ 历史数据（30天日线） | TC-IB-002 | ✅ | 2026-08-25 |
| 3 | IB paper 账户可查询 CL 实时 tick（分钟级，北京时间 11:09 确认 live） | TC-IB-003 | ✅ | 2026-08-25 |
| 4 | Flask /api/quote 端点可查 IB 历史数据（独立线程 clientId=995） | TC-IB-004 | ✅ | 2026-08-25 |
| 5 | RB conId=600696516 NYMEX exp=20261030 mult=42000 | TC-IB-005 | ✅ | 2026-08-25 |
| 6 | CL conId=296574787 NYMEX exp=20261120 mult=1000 | TC-IB-006 | ✅ | 2026-08-25 |
| 7 | Signal API 接受 rb-cl-spread 策略，status=reviewed | TC-IB-007 | ✅ | 2026-08-25 |
| 8 | RiskGate 放行 rb-cl-spread 信号（z=2.5，allowed=True） | TC-IB-008 | ✅ | 2026-08-25 |
| 9 | signal_handler 多腿展开：rb-cl long → BUY 3RB + SELL 2CL | TC-IB-009 | ✅ | 2026-08-25 |
|10 | strategy_registry.register(StrategySpec) 成功注册 rb-cl-spread | TC-IB-010 | ✅ | 2026-08-25 |
|11 | rbcl_zscore.py 脚本可正确计算 3:2:1 crack spread Z-Score | TC-IB-011 | ✅ | 2026-08-25 |
|12 | GET /health 5组件全绿，GET /health/full ib_connection=ok | TC-IB-012 | ✅ | 2026-08-25 |
|13 | smoke_test 4项全绿 | TC-IB-013 | ✅ | 2026-08-25 |
|14 | IB account DUH583159 paper，BuyingPower=$1.5M，NetLiq=$381K | TC-IB-014 | ✅ | 2026-08-25 |

### Feature 5: RB-CL Crack Spread 策略

| # | 事实 | 验证方式 | 状态 | 验证时间 |
|---|------|---------|------|---------|
| 1 | rb-cl-spread 策略注册成功，spread_symbols=RB,CL | TC-RB-001 | ✅ | 2026-08-25 |
| 2 | long 方向 → BUY 3 RB + SELL 2 CL | TC-RB-002 | ✅ | 2026-08-25 |
| 3 | short 方向 → SELL 3 RB + BUY 2 CL | TC-RB-003 | ✅ | 2026-08-25 |
| 4 | Z>2.0 触发做空 crack，Z<-2.0 触发做多 crack | TC-RB-004 | ✅ | 2026-08-25 |
| 5 | Z=+0.56 无信号（HOLD），均值=62.19，当前=63.48 | TC-RB-005 | ✅ | 2026-08-25 |
| 6 | scripts/rbcl_zscore.py 部署到 C:\projects\trading\scripts\ | TC-RB-006 | ✅ | 2026-08-25 |

### Feature 6: Pairs-Spread 通用配对策略（2026-08-25）

| # | 事实 | 验证方式 | 状态 | 验证时间 |
|---|------|---------|------|---------|
| 1 | `pairs-spread` 策略注册到 strategy_registry | TC-PS-001 | ✅ | 2026-08-25 |
| 2 | `signal_handler` 保存 `legs` 字段到 signals.jsonl | TC-PS-002 | ✅ | 2026-08-25 |
| 3 | `_execute_from_signal` 多腿判断：含 `spec.spread_symbols` 或 `signal["legs"]` | TC-PS-003 | ✅ | 2026-08-25 |
| 4 | `pairs-spread` build_order_contexts 正确展开多腿 | TC-PS-004 | ✅ | 2026-08-25 |
| 5 | `place_order_func` futures_set 含 PL/PA/HO（修复 STK 误判） | TC-PS-005 | ✅ | 2026-08-25 |
| 6 | PL U6 (NYMEX) conId=662533021，PA U6 conId=656552155 | TC-PS-006 | ✅ | 2026-08-25 |
| 7 | PL/PA 做空信号（SELL PL + BUY PA）完整执行：PL order=103 Submitted，PA order=105 Filled | TC-PS-007 | ✅ | 2026-08-25 |
| 8 | PA BUY 持仓确认：position=+1，avgCost=134652.51 USD | TC-PS-008 | ✅ | 2026-08-25 |
| 9 | PL SELL 持仓确认：position=-1，avgCost=92757.49 USD | TC-PS-009 | ✅ | 2026-08-25 |
|10 | 多 Flask 进程监听 5002 导致旧代码执行（根因确认） | TC-PS-010 | ✅ | 2026-08-25 |
|11 | 单 Flask 实例部署 + smoke_test 全绿 | TC-PS-011 | ✅ | 2026-08-25 |
|12 | pairs-scanner.py 统一用 `pairs-spread` 策略 + `legs` 动态传入 | TC-PS-012 | ✅ | 2026-08-25 |
|13 | hourly cron pairs-scanner 已设置（Asia/Shanghai 整点） | TC-PS-013 | ✅ | 2026-08-25 |

### IB Session/连接稳定性调查（2026-08-25 下午）

| # | 事实 | 验证方式 | 状态 | 验证时间 |
|---|------|---------|------|---------|
| 1 | Flask IB worker 单例（clientId=999），winclaw 上只有 1 个 ESTABLISHED 连接 | netstat :4002 | ✅ | 2026-08-25 |
| 2 | `/api/quote` 旧代码：`_query_thread` 里直接调 `ib.reqHistoricalData()` 后 `ib.disconnect()` → 每次请求断开 Flask IB 连接并产生 TIME_WAIT 累积 | 代码审查 | ✅ | 2026-08-25 |
| 3 | `util.run()` 在 Flask 请求线程里卡死（`reqHistoricalData` 是异步，事件路由到 IB worker 线程的 loop，请求线程的 loop 收不到回调） | 实测 | ✅ | 2026-08-25 |
| 4 | **修复**：`manager.run_sync(_do_query)` + `_do_query` 内 `ib.sleep(0.2)` 轮询等待 `historicalData` 事件到达 → GC 5 天数据正常返回 | 实测 | ✅ | 2026-08-25 |
| 5 | PL 10天历史数据：close=[1764.7~1881.2]，conId=896309315 | /api/quote PL | ✅ | 2026-08-25 |
| 6 | PA 10天历史数据：close=[1293.5~1374.0]，conId=656552155 | /api/quote PA | ✅ | 2026-08-25 |
| 7 | 当前 PL/PA Z-Score=+1.30（spread=536.7，mu=466.55，sigma=54.11）| 手动计算 | ✅ | 2026-08-25 |
| 8 | 修复后：Flask 重启后只有 1 个 ESTABLISHED 连接，0 个 TIME_WAIT（`ib.disconnect()` 移除生效）| netstat :4002 | ✅ | 2026-08-25 |
| 9 | `get_ib_connection()` 在 `_query_thread` 里调用时获取 Flask IB worker 单例，但直接调 IB 方法跨线程不安全（ib_insync 内部依赖事件循环在线程内运行） | 代码审查 | ✅ | 2026-08-25 |
|10 | scanner `--ib-direct` 用 clientId=991（独立于 Flask clientId=999），用完 `ib.disconnect()`，无 session 冲突 | pairs_scanner.py:142,163 | ✅ | 2026-08-25 |

---

## Issue 清单

| # | 标题 | 严重性 | 状态 | 发现时间 | 关闭时间 |
|---|------|--------|------|---------|---------|
| 1 | `get_z120_status()` 未定义 | P0 | 已废弃 | 2026-05-05 | 2026-05-09 |
| 2 | `color` 变量未定义（3_three_screen.py:187） | P0 | **Closed** | 2026-05-05 | 2026-05-10 |
| 3 | 重复字典键 `"黄金"`（nl_parser.py:132） | P0 | **Closed** | 2026-05-05 | 2026-05-09 |
| 7 | 飞书交易命令返回 order=null | P1 | **Closed** | 2026-05-10 | 2026-05-10 |
| 8 | 多 Flask 进程同时监听 5002（旧实例未清理 + health_check 自愈叠加） | P0 | **Closed** | 2026-08-25 | 2026-08-25 |
| 9 | `pairs-spread` 策略无 `build_order_contexts` 处理分支（fallthrough 单腿） | P0 | **Closed** | 2026-08-25 | 2026-08-25 |
|10 | `signal_handler` 创建信号时未保存 `legs` 字段 | P0 | **Closed** | 2026-08-25 | 2026-08-25 |
|11 | `place_order_func` futures_set 缺少 PL/PA/HO → 期货误判为 STK 下单失败 | P0 | **Closed** | 2026-08-25 | 2026-08-25 |
|12 | `/api/quote` 两处 bug：① `_query_thread` 末尾 `ib.disconnect()` 断 Flask IB 连接；② `util.run()` 在请求线程卡死（hist_count 恒为 0） | P0 | **Closed** | 2026-08-25 | 2026-08-25 |

---

## Issue #7（Closed）

**标题**：飞书交易命令返回 order=null
**状态**：Closed
**关闭时间**：2026-05-10
**根因**：测试格式与 Feishu 事件格式不兼容 + QUERY action 未正确排除
**修复内容**：
1. 请求格式归一化：支持简化测试格式 `{"message": {"content": "..."}}` 转换为 Feishu Schema 2.0 格式
2. action 条件修正：`if action and action != "UNKNOWN"` → `if action in ("BUY", "SELL", "CLOSE")`，排除 QUERY action
3. 去重消息修复：处理 symbol=None 时的字符串拼接
4. 空输入 fallback：content parse 失败时回退到原始文本

**验证方式**：
1. `curl -s http://100.99.204.126:5002/feishu-webhook -X POST -d '{"message": {"content": "买入1手GC"}}'` → `{"order":{"action":"BUY","exchange":"COMEX","quantity":1,"status":"Submitted","symbol":"GC"},"status":"ok"}` ✅
2. `curl -s http://100.99.204.126:5002/feishu-webhook -X POST -d '{"message": {"content": "查看持仓"}}'` → `{"order":null,"status":"ok"}` ✅
3. WH-201 test against server: ALL PASS ✅

---

## Issue #1（已废弃）

**标题**：`get_z120_status()` 未定义
**状态**：已废弃
**废弃原因**：zz120 功能已废弃，不再需要此函数

---

## Issue #2（Closed）

**标题**：`color` 变量未定义（3_three_screen.py:187）
**状态**：Closed
**关闭时间**：2026-05-10
**验证方式**：`ruff check kanban/pages/3_three_screen.py` → All checks passed ✅

---

## Issue #3（Closed）

**标题**：重复字典键 `"黄金"`（nl_parser.py:132）
**状态**：Closed
**关闭时间**：2026-05-09
**验证方式**：
1. `rg -n '黄金' notify/nl_parser.py` → 只有 1 处
2. `ruff check notify/nl_parser.py` → All checks passed ✅

---

## OKX SDK 2.x 兼容性问题（2026-05-09）

| # | 事实 | 验证方式 | 状态 |
|---|------|---------|------|
| 1 | SDK 2.x 导入路径是 `okx.api.Account/Trade/Market` | 本地测试 | ✅ |
| 2 | SDK 2.x `AccountAPI.__init__()` 不接受 `proxies` 参数 | winclaw 测试 | ✅ |
| 3 | 永续合约需要 `posSide`（long/short），现货不需要 | winclaw 测试 | ✅ |
| 4 | 模拟盘 flag="1"，实盘 flag="2" | okx.yaml 配置 | ✅ |

---

## M5 背离监控器 (2026-06-12)

### 代码验证

| # | 事实 | 验证方式 | 状态 |
|---|------|---------|------|
| 1 | `monitor.py` 语法正确，AST parse 通过 | 本地 python3 -c "ast.parse()" | ✅ |
| 2 | 所有依赖可导入：httpx, pandas, requests, FeishuNotifier | 本地 import 测试 | ✅ |
| 3 | `detect_divergences()` 含 `low_icd_hold_mult=0.5`, `low_icd_threshold=3.0` | 代码审查 | ✅ |
| 4 | 信号去重逻辑正确：同 signal_key 不重复通知 | mock 数据测试 | ✅ |
| 5 | `describe_market()` 输出 IC/IDX 价格、波幅、MA60乖离、信号密度 | mock 数据测试 | ✅ |
| 6 | `|ic_d|≤3` 标记为 ⚠️LOW，hold 缩短为 span×0.5 | mock 数据测试 | ✅ |

### TDX 连通性

| # | 事实 | 验证方式 | 状态 |
|---|------|---------|------|
| 1 | `http://100.99.204.126:8005` 返回 HTTP 502 Bad Gateway | `python3 monitor.py --once` 实测 | ❌ TDX 服务不可用 |
| 2 | quant-core TDX 服务挂死或 SSH tunnel 断开 | 502 错误确认 | ❌ 阻塞 |

### 文件位置

| 文件 | 路径 |
|------|------|
| 监控脚本 | `m5_monitor/monitor.py` |
| 策略修改 | `quant-agent/skills/cf-index-monitor/scripts/scan_m1_tdx.py` |
| 信号状态文件 | `m5_monitor/data/m5_signal_state.json` |
| 日志文件 | `m5_monitor/logs/m5_monitor.log` |

---

## M5 背离策略 — 放大持仓验证 (2026-06-12)

### 数据来源
`quant-agent/skills/cf-index-monitor/scripts/w35_o3_trades.csv`
- 170 笔交易，2026-01 至 2026-06，w35/o3 策略参数

### 核心发现：历史数据中所有交易均为 IC 与 IDX 异向

顶背离（做空）：ic↓ idx↑，共 98 笔
底背离（做多）：ic↑ idx↓，共 72 笔

**"同向放大持仓"在历史数据中不存在样本**（0 笔）

### 按 div_ratio 分组表现

| div_ratio 区间 | 交易数 | 占比 | PnL/笔 | 胜率 | 止损率 | span均值 |
|---------------|-------|------|--------|------|--------|---------|
| [0, 1.0) | 88 | 51.8% | +13.10 | 60.2% | 35.2% | 20.4分钟 |
| [1.0, 2.0) | 31 | 18.2% | **+16.82** | **64.5%** | **19.4%** | 16.8分钟 |
| [2.0, 3.0) | 16 | 9.4% | +9.16 | 56.2% | 43.8% | 17.9分钟 |
| [3.0, ∞) | 35 | 20.6% | **+3.73** | **37.1%** | **54.3%** | 20.3分钟 |

### 高 div_ratio (≥3.0) 交易特征

- |ic_delta|均值仅 **0.81**（IC 几乎不动）
- |idx_delta|均值 **6.22**（IDX 大幅异动）
- 中位数 PnL = **-2.60**（负期望）
- 止损率 54.3%，胜率 37.1%

---

## Trading 架构整合 — 部署验收 (2026-08-25)

### 组件自检

| # | 事实 | 验证方式 | 状态 |
|---|------|---------|------|
| 1 | `/health` 返回 5 组件 ok (feishu, risk_gate, signal_api, order_manager, query_only) | curl GET /health | ✅ |
| 2 | `/health/full` 含 IB Gateway :4002 连接状态 | curl GET /health/full | ✅ |
| 3 | RiskGate 5 条规则可插拔 (DailyLoss/Exposure/Correlation/ZScore/MaxPositions) | 代码审查 + 9 条 pytest | ✅ |
| 4 | POST /api/signals → 风控预检 → reviewed/rejected | smoke_test.py 第3项 | ✅ |
| 5 | GET /api/signals/<id> → 404 正确返回 | smoke_test.py 第4项 | ✅ |
| 6 | OrderManager 风控严格模式拦截日亏 >5% | test_risk_gate_blocks_order ✅ | ✅ |
| 7 | advisory 模式不拦截，仅记录告警 | test_advisory_mode_always_allows ✅ | ✅ |
| 8 | Z-Score 三级：warn(±3.0) 告警, critical(±4.0) 熔断 | test_zscore_guard_* ✅ | ✅ |

### 部署详情

| # | 事实 | 验证方式 | 状态 |
|---|------|---------|------|
| 1 | 10 个新文件通过 scp 部署到 winclaw C:\projects\trading\ | `dir` 命令确认 | ✅ |
| 2 | Flask :5002 成功启动，PID 5504 | `netstat -ano` | ✅ |
| 3 | IB Gateway :4002 已连接 (clientId=999) | /health/full 返回 | ✅ |
| 4 | smoke_test.py 4/4 PASS，exit 0 | 远程执行 | ✅ |
| 5 | Windows Task Scheduler `TradingHealthCheck` 注册，每 5 分钟 | `schtasks /query` | ✅ |
| 6 | health_check.bat Python 路径修正为完整路径 | 文件内容对比 | ✅ |
| 7 | smoke_test.py emoji → ASCII 兼容 Windows GBK 控制台 | 文件内容对比 | ✅ |

### 本地测试

| # | 事实 | 验证方式 | 状态 |
|---|------|---------|------|
| 1 | test_risk_gate.py: 9/9 PASS | pytest -v | ✅ |
| 2 | test_order_manager.py: 3/3 PASS | pytest -v | ✅ |
| 3 | test_signal_api.py: 6/6 PASS | pytest -v | ✅ |
| 4 | config/settings.yaml 含 risk_gate 配置段 (5 参数) | 代码审查 | ✅ |
| 5 | quant-agent/tools/trading_adapter.py 含 submit_signal + check_signal | 代码审查 | ✅ |

### StrategyRegistry (2026-08-25)

| # | 事实 | 验证方式 | 状态 |
|---|------|---------|------|
| 1 | strategy_registry.py 含 4 个注册策略 (fu-lu-spread/doge-grid/crypto-divergence/z120-spread) | 代码审查 | ✅ |
| 2 | validate() 拒绝未知策略 + 缺少必填参数 + 超范围参数 | 10 条 pytest | ✅ |
| 3 | build_order_contexts() 为 fu-lu-spread 生成两条腿 (FU+LU) | test_build_fu_lu_spread_long/short | ✅ |
| 4 | handle_submit_signal() 集成策略校验，错误返回 strategy_errors | 代码审查 | ✅ |
| 5 | handle_confirm_signal() 支持多腿 spread（调 StrategyRegistry.build_order_contexts） | 代码审查 | ✅ |
| 6 | test_strategy_registry.py: 10/10 PASS | pytest -v | ✅ |

### 全自动下单模式 (2026-08-25)

| # | 事实 | 验证方式 | 状态 |
|---|------|---------|------|
| 1 | `auto=true` 且 source 在白名单 → status=executed，跳过 reviewed | 6条 pytest | ✅ |
| 2 | source 不在白名单使用 `auto=true` → 拒绝，返回 reason | test_unknown_source_rejected | ✅ |
| 3 | 半自动（无 auto 参数）→ status=reviewed，保持原有行为 | test_no_auto_means_reviewed | ✅ |
| 4 | `_execute_from_signal()` 重构，人确认路径复用同一执行函数 | 代码审查 | ✅ |
| 5 | `AUTO_EXECUTE_WHITELIST` = `{"quant-agent", "smoke-test"}` | 代码审查 | ✅ |
| 6 | test_auto_execute.py: 6/6 PASS | pytest -v | ✅ |

### Feature 7: SimNow 内盘期货模拟接入（2026-08-29）

| # | 事实 | 验证方式 | 状态 | 验证时间 |
|---|------|---------|------|---------|
| 1 | winclaw Python 3.13.12 安装成功（winget） | `winget list Python` | ✅ | 2026-08-29 |
| 2 | vnpy_ctp 6.7.11.4 (cp313) 安装成功 | `pip show vnpy_ctp` | ✅ | 2026-08-29 |
| 3 | `from vnpy_ctp.api import MdApi, TdApi` 导入成功 | `python -c "..."` | ✅ | 2026-08-29 |
| 4 | `simnow_client/ctp_connector.py` import 路径已更新为 vnpy_ctp.api | 代码审查 | ✅ | 2026-08-29 |
| 5 | `simnow_client/trader.py` import 路径已更新 | 代码审查 | ✅ | 2026-08-29 |
| 6 | `config/settings.yaml` 含 simnow 配置段（flag/servers/broker_id） | 代码审查 | ✅ | 2026-08-29 |
| 7 | `scripts/test_simnow.py` 已就绪（服务器路径更新为 Python313） | 代码审查 | ✅ | 2026-08-29 |
| 8 | CTP DLL 下载完成（thostmduserapi_se.dll 3.0MB + thosttraderapi_se.dll 3.4MB） | 下载验证 | ✅ | 2026-08-31 |
| 9 | `SIMNOW_SIM_PASSWORD` 填入 secrets.toml | 待填 | ⏳ | pending |
|10 | `scripts/test_simnow.py` winclaw 连通性测试 PASS | 远程执行 | ⏳ | pending |
|11 | Flask `/api/ctp/account` + `/api/ctp/positions` 端点 | 代码审查 | ✅ | 2026-08-31 |

### Feature 8: TV Study (Z-Score) CDP 读取（2026-08-31）

TradingView Desktop study 数据内部存储路径：
- `source._data._items`: 数组，每项 `{index, value}`
- `dataWindowView()`: 对 study 返回 null（TV Desktop API 限制）
- 旧脚本 `get_window_data.cjs` 用 `dataWindowView()` → 永远读不到 study

Z-Score study 格式（Index Z-Score & Spread）：
- `fullArray[0]`: time (unix)
- `fullArray[1]`: Z-Score 值
- `fullArray[2]`: signal
- `fullArray[3]`: upper band
- `fullArray[4]`: lower band
- `fullArray[5]`: spread

| # | 事实 | 验证方式 | 状态 | 验证时间 |
|---|------|---------|------|---------|
| 1 | `get_window_data.cjs` 用 `_data._items` 读到 Z-Score=-1.18 | CDP 直接探测 | ✅ | 2026-08-31 |
| 2 | `get_window_data.cjs` 用 `_data._items` 读到澳银劈叉 Corr=0.919 | CDP 直接探测 | ✅ | 2026-08-31 |
| 3 | `get_window_data.cjs` 用 `_data._items` 读到 overlay XAGUSD OHLCV | CDP 直接探测 | ✅ | 2026-08-31 |
| 4 | `_extract_tv_indicators` 解析新 study 格式（Z-Score/ Spread/ 相关性） | Python 测试 | ✅ | 2026-08-31 |
| 5 | `_get_active_chart_ws_url()` 找到 OANDA:XAUUSD 活跃 tab | CDP probe | ✅ | 2026-08-31 |
| 6 | `get_single_tab_data_via_cdp` 读取 OANDA:XAUUSD Z-Score=-1.18 | winclaw 集成测试 | ✅ | 2026-08-31 |
| 7 | `tv` webhook 命令返回 ok，飞书消息发送成功 | HTTP 测试 | ✅ | 2026-08-31 |
| 8 | Z-Score 监控链路（TV CDP → _extract → _check_zscore_signal → /api/signals） | 代码审查 | ✅ | 2026-08-31 |
| 9 | clientId 999→0 修复 IB Error 326，`/health/full` ib connected=true | HTTP 测试 | ✅ | 2026-08-31 |
|10 | `get_window_data.cjs` TF 已是目标时跳过切换，耗时 ~1.8s | 计时测试 | ✅ | 2026-08-31 |
