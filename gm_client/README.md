# 掘金量化(gm) 模拟交易接入

## 架构
- `gmsim_worker.py` 在**独立 venv**（`C:\projects\gm_env`，含 `gm` SDK 及其 pin 的
  protobuf<4）中运行，避免 gm 的原生依赖污染系统 Python/streamlit 环境。
- worker 必须走 gm 的 `run(mode=1)` 策略框架，在 `init` 回调里调用交易/查询接口。
- 结果经临时文件 `GM_RESULT_FILE` 回传（gm C sdk 会接管 stdout，print 不可靠）。
- 依赖本地「我的掘金终端」运行（终端服务默认 `localhost:7001`）。

## 部署（winclaw）
1. 建 venv：`python -m venv C:\projects\gm_env` 后 `gm_env\Scripts\pip install gm`
2. 复制 worker 到 venv 目录：`copy gm_client\gmsim_worker.py C:\projects\gm_env\gmsim_worker.py`
3. secrets.toml 配置：`GM_TOKEN` / `GM_ACCOUNT`（模拟账户 UUID）/ `GM_SERV_ADDR`（默认 localhost:7001）

## 桥接口（与 /api/ctp/* 同风格）
- `GET /api/gm/account[?force=1]`  账户资金
- `GET /api/gm/positions[?force=1]` 持仓
- `POST /api/gm/order`  下单 `{symbol:"SHSE.600000", side:1, volume:100, order_type:1, position_effect:1, price}`
- `POST /api/gm/cancel` 撤单 `{symbol?}`（省略撤全部未成交）
  - side: 1 买/2 卖；order_type: 1 限价/2 市价；position_effect: 1 开/2 平
