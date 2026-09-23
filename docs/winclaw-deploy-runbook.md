# winclaw 部署与启动 runbook —— trading 实盘基座 + quant 数据服务 + kanban

> 首次建立：2026-09-02（owner 实测 winclaw 现场后整理）。以 winclaw 本机实测为准；
> 与本仓 `AGENTS.md` 冲突处，以本文件的「2026-09 订正」为准（AGENTS.md 部分端口/Python 描述已过时）。

## 0. 边界（先读）

- 本文档覆盖 winclaw（`ssh winclaw` → `wang@100.99.204.126`，**一台 Windows**）上的**交易系统**：
  - quant 数据服务 **8005**（FastAPI/uvicorn）
  - trading webhook 桥接 **5002**（Flask，**纯仿真**：simnow/citic/gm/OKX/IB paper；2026-09-19 起拒绝 profile=live）
  - **实盘网关 5006**（live_gateway，IB live 4001 + CTP live 直连 worker；实盘唯一入口，详见 `system-architecture.md`）
  - trading 看板 **8507**（Streamlit kanban）
  - 外部依赖：IB Gateway **4001(live)/4002(paper)**、通达信 TdxW、TradingView CDP。
- **不在本文范围**：life-compass 产品三服务 compass **8505** / pmo-ask **5001** / personal-website **8504**。
  那是另一套（出 compass.qiaoge.top / ask.qiaoge.top 公网域名），见 life-compass 自己的 runbook，
  由计划任务 `MedalWatchdog` 保活。**MedalWatchdog 不保活本文任何服务**。
- **端口红线**：8505/5001/8504 已被 life-compass 占用，trading 任何脚本/看板**不得**绑这三个口。
- 订正 AGENTS.md：quant **与 trading 同机**（都在 winclaw 100.99.204.126），不是「另一台服务器」。

## 1. 服务与端口总览

> 权威拓扑（含 5006 实盘网关、5003/5004 行情、跨机关系）见 [`system-architecture.md`](system-architecture.md)。
> 下表为 2026-09-19 订正。

| 服务 | 端口 | 技术/入口 | winclaw 目录 | 健康检查（本机） | 自启/保活 |
|---|---|---|---|---|---|
| quant 数据服务 | **8005** | Python313 `uvicorn quant_core.server.app:app --host 0.0.0.0 --port 8005` | `C:\projects\quant` | `GET /docs` 或 `/sources` 返回 200（**无** `/health` 路由，404 是正常） | ONLOGON `StartQuantServer`（登录拉起）+ **周期保活 `TradingHealthCheck`(15min)**：端口不通→触发 `StartQuantServer` |
| trading webhook 桥接 | **5002** | Python313 `notify\webhook_bridge.py`（Flask，**仅 simnow/citic 仿真**，live 返回 bad_profile） | `C:\projects\trading` | `GET /health` 200，body 含 feishu/order 组件状态 | **PM2 进程 `trading-bridge`（事实托管，`npx pm2 restart trading-bridge`）**；`wb_bridge2`/`TradingHealthCheck`(15min)/`health_check.bat` 兜底。勿手工另起，避免同端口多实例 |
| **实盘网关 live-gateway** | **5006** | Python313 `live_gateway\live_gateway_app.py`（Flask）：IB live 直连 4001；CTP live 走常驻 daemon `ctp_daemon.py`（127.0.0.1:5013，强制 CTP_PROFILE=live，不代理 5002） | `C:\projects\trading` | `GET /health` 200（managed 含 U8590961）；`GET /api/ib/live/orders`、`/api/ctp/account` | **无自启/无看门狗**（实盘入口刻意人工掌控）；重启跑 `live_gateway\start_live_gateway.ps1`（先停旧 PID，首次 CTP 查询自动拉起 5013 daemon）；写操作须 `X-Real-Money: CONFIRM` |
| CTP 行情 simnow | **5003** | Python313 `ctp_md\run_worker.py --profiles simnow`（常驻 MdApi+SSE/快照，独立进程隔离 SWIG 崩溃） | `C:\projects\trading` | `GET /api/ctp/md/health`，盘中 state=logined/tick_count 增长 | **2026-09-19 状态：pm2 stop**（6.7.11.1 md 绑定夜盘原生 abort，累计重启 3416 次；FU 卡回退 gm fail-safe）。cxclaw 同口部署，待绑定修复 |
| CTP 行情 citic | **5004** | Python313 `ctp_md\run_worker.py --profiles citic`（绑定 6.5.1_CP，与 simnow 必须分进程） | `C:\projects\trading` | `GET /api/ctp/md/health` | 同上（pm2 `ctp-md-citic`）；非交易时段 logining 属正常 |
| trading kanban 看板 | **8507** | Python313 `streamlit run kanban\app.py --server.port 8507` | `C:\projects\trading\kanban` | `GET /_stcore/health` → `ok` | **无**（手动起，未挂自启/保活，见待办） |
| IB Gateway | **4001 live / 4002 paper** | `C:\ibgateway\ibgateway.exe`（5006 连 4001 做实盘，仿真桥/研究连 4002） | `C:\ibgateway` | 进程在监听即可；quant 日志看 IB 连接 | 计划任务 `IBGW`(ONLOGON) |
| 通达信 TdxW | — | `C:\new_tdx64\TdxW.exe`（行情源） | `C:\new_tdx64` | 进程在 | 计划任务 `StartTdxW`(Time) |
| TradingView CDP | **9224** | `C:\Users\wang\Desktop\TV-Extracted\TradingView.exe --remote-debugging-port=9224`（便携版） | — | `http://127.0.0.1:9224/json/list` 可连；kanban `tv_cdp.port=9224` | 计划任务 `TradingView_CDP`/`_Launch`（2026-09 已对齐 TV-Extracted:9224）；桌面另有手动快捷方式 |

公网/内网访问：quant 数据 API 走内网 `http://100.99.204.126:8005`（Tailscale 网内），不经 Cloudflare；
trading webhook 接收外部 POST 走 `http://100.99.204.126:5002/...`（TV/飞书侧配置的地址）。

## 2. Python 环境（2026-09 重大订正）

- **Python 3.12 已从 winclaw 卸载**（`...\Programs\Python\Python312\` 目录残留但 `python.exe` 不存在）。
  本机现在只有 **Python 3.13**：`C:\Users\wang\AppData\Local\Programs\Python\Python313\python.exe`。
- 所有 winclaw 启动脚本一律用 **Python313 绝对路径**（trading 规范本就要求：不要用 PATH 里的 `python`）。
- 写死 Python312 的旧脚本（webhook/flask/okx-proxy 等共 12 个）已**归档**（非删除）到
  `C:\projects\trading\_archive_py312_20260901\`，确认无用后可整夹删除。
- 计划任务 `wb_bridge2` 动作已于 2026-09 由 Python312 改为 Python313。
- quant 不受此次卸载影响：`start_8005.bat` 本就写 Python313 绝对路径；`start_rdp.bat` 用 PATH `python`（建议也改成 313 绝对路径，见待办）。

## 3. 常用运维操作（从能 `ssh winclaw` 的 Mac 执行）

远程跑 PowerShell 脚本示例（输出含 post-quantum 警告可忽略）：

```bash
# --- 健康检查（本机视角，最可靠）---
ssh winclaw "powershell -NoProfile -Command \"foreach($p in 8005,5002,5006,8507,4001,4002){ Get-NetTCPConnection -LocalPort $p -State Listen -EA SilentlyContinue | Select-Object -First 1 | ForEach-Object { '$p PID='+$_.OwningProcess } }\""

# 5002 桥接健康（含 feishu/order 组件）
ssh winclaw "powershell -NoProfile -Command \"(Invoke-WebRequest http://127.0.0.1:5002/health -UseBasicParsing -TimeoutSec 8).Content\""
# 8005 quant 健康（无 /health，用 /sources）
ssh winclaw "powershell -NoProfile -Command \"(Invoke-WebRequest http://127.0.0.1:8005/sources -UseBasicParsing -TimeoutSec 8).StatusCode\""
# 8507 kanban
ssh winclaw "powershell -NoProfile -Command \"(Invoke-WebRequest http://127.0.0.1:8507/_stcore/health -UseBasicParsing -TimeoutSec 8).Content\""
```

### 重启

```bash
# quant 8005（推荐用 313 绝对路径脚本）
ssh winclaw 'cmd /c "C:\projects\quant\start_8005.bat"'   # 前台 RDP 用；SSH 下见下
# 桥接 5002：走计划任务（已配 313）
ssh winclaw 'schtasks /Run /TN wb_bridge2'
# kanban 8507（手动，隐藏起）
ssh winclaw "powershell -NoProfile -Command \"Start-Process -FilePath 'C:\Users\wang\AppData\Local\Programs\Python\Python313\python.exe' -ArgumentList '-m','streamlit','run','C:\projects\trading\kanban\app.py','--server.port','8507','--server.headless','true','--server.address','127.0.0.1' -WorkingDirectory 'C:\projects\trading\kanban' -WindowStyle Hidden\""
```

> SSH 非交互会话起常驻服务：`start_8005.bat`/`start_rdp.bat` 含 RDP/`pause` 语义，适合登录会话；
> 无人值守建议用计划任务（StartQuantServer / wb_bridge2）或 `Start-Process -WindowStyle Hidden` 方式。

### 日志

- quant：`C:\projects\quant\server8005.log`（`start_8005.bat` 重定向）、`C:\projects\quant\logs\watchdog.log`、`server.log`。
- 桥接：`C:\projects\trading\webhook.log`、`notify\webhook_stdout.log` / `webhook_stderr.log`、`wb*.log`。
- 看板：Streamlit 默认输出到启动它的控制台（隐藏启动时建议自行重定向）。

## 4. 增量部署

- winclaw **不能 git pull**（GitHub 被墙）。在 Mac 改好后 `scp` 到 winclaw，再重启对应服务。
- quant（源仓 Mac `~/.opencode/workspace/quant/`）：改 `quant_core/**.py` → `scp` 到 `C:\projects\quant\` →
  重启 8005；若 `watchdog.py` 在跑，改 `.py` 会自动重启。
- trading 桥接（源仓 Mac `~/.opencode/workspace/trading/`）：改 `notify/webhook_bridge.py`、`orders/**`、`client/**` 等 →
  `scp` 到 `C:\projects\trading\` → `schtasks /Run /TN wb_bridge2` 或重启进程。
- 红线：不在 winclaw 提交/拉取 secrets；`.streamlit/secrets.toml` 已忽略。

## 5. 事故记录

- **2026-09-01 Python 3.12 卸载 + 端口误占**：
  - 现象：8505/5001（life-compass）长时间不可用；排查发现根因是 Python 3.12 被卸载，写死 312 的 `start.ps1`
    启动即崩（看门狗每次探活失败、调重启脚本都拉空）。同期 trading kanban 被手动以 `--server.port 8505` 起在
    life-compass 的口上，导致 compass 域名返回 Streamlit。
  - 处置：kanban 从 8505 挪到 **8507**；life-compass/ask 的启动脚本改为自动选解释器（不属本文）；
    trading 侧 `wb_bridge2` 改 Python313，写死 312 的旧脚本归档 `_archive_py312_20260901`。
  - 教训：trading 任何服务**不要手动绑 8505/5001/8504**；启动脚本一律 Python313 绝对路径。

## 6. 待办 / 隐患（未处理，需人拍板）

- [x] **交易侧周期保活已恢复（2026-09-02）**：重新启用计划任务 `TradingHealthCheck`（**每 15 分钟**，Highest/wang，
      动作 `powershell ... C:\projects\health_check_all.ps1`）。脚本只保 **trading 两端口**——5002 不通则跑
      `C:\projects\trading\health_check.bat`（已 Python313、按窗口标题精确杀重启），8005 不通则触发 `StartQuantServer`；
      日志 `C:\projects\health_check_all.log`。**life-compass 的 8505/5001/8504 已明确不在此脚本内**（见下边界）。
      与 life-compass 的 `MedalWatchdog` 各管各、互不重叠：`MedalWatchdog` 守 5001/8505/8504，`TradingHealthCheck` 守 5002/8005。
- [ ] **看门狗边界**：`C:\projects\health_check_all.ps1` 只允许探 trading 端口（5002/8005）；历史上它曾混入 5001/8505，
      2026-09-02 已按要求剔除（5001/8505 归 `MedalWatchdog`）。后续不要把 life-compass 端口加回这个 trading 脚本。
- [ ] **kanban 8507 无自启/保活**：机器重启或进程崩了不会自拉。若要常驻，建议建 ONLOGON 计划任务固定 8507
      （并写一个类似 life-compass `clean_restart.ps1` 的幂等重启脚本）；不要复用 MedalWatchdog。
- [x] **`start_rdp.bat` 已改 Python313 绝对路径（2026-09-02）**：与 `start_8005.bat` 对齐，不再依赖 PATH `python`（Mac 源 + winclaw 均已更新）。
- [x] **TradingView CDP 已对齐 9224（2026-09-02）**：实际在用的是桌面便携版 `C:\Users\wang\Desktop\TV-Extracted\TradingView.exe`
      监听 **9224**（`config/settings.yaml: tv_cdp.port=9224`，kanban 连 9224）；而计划任务 `TradingView_CDP`/`_Launch`
      原指向 WindowsApps 版的 9222（9222 从未监听、且桌面快捷方式是手动启动不在开机自启）。已把两个计划任务动作改为
      TV-Extracted `--remote-debugging-port=9224`；源码同步：`kanban/src/tv.py`（默认端口 + webSocket replace 9222→9224，
      修了远程 host 替换不生效的小 bug）、`start_tv_cdp.bat`、`check_cdp.js`。注意 `tv.py` 改动下次重启 8507 kanban 才生效
      （当前 kanban 本机直连 127.0.0.1:9224 不受影响）。
- [ ] 归档夹 `C:\projects\trading\_archive_py312_20260901\` 确认无用后可删。
- [x] 本文件已同步到 winclaw `C:\projects\trading\docs\` 与 `C:\projects\quant\docs\`（2026-09-02）；源在 Mac `~/.opencode/workspace/trading/docs/winclaw-deploy-runbook.md`。
