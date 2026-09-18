# ctp_md —— CTP MdApi 常驻行情服务（P1）

独立进程的 CTP 行情前置长连接，向 quant-agent 提供 tick 推送/快照。
**必须与 5002 webhook 桥接分进程**：CTP SWIG `.pyd`（仅 cp313）可能进程级崩溃，
独立进程不影响桥接主服务。

## 进程拓扑（每 profile 独立进程）

simnow 与中信评测的 SWIG 绑定版本不同（6.7.11.1 / 6.5.1_CP），同一进程只能
加载一套，故分两个进程：**5003=simnow，5004=citic**。进程启动前用
`CTP_PROFILE` 选定绑定目录（`ctp_client/ctp_connector.py` 模块级读取）。

## 接口（示例为 5003，citic 换 5004）

- `POST /api/ctp/md/subscribe` `{profile, instruments[]}` 订阅（持久化到 `data/md_subscriptions.json`，重启自动补订阅）
- `POST /api/ctp/md/unsubscribe`
- `GET  /api/ctp/md/snapshot?profile=&instrument=` 内存最新 tick（微秒级）
- `GET  /api/ctp/md/stream?profile=&instruments=a,b` SSE；连接建立先补发环形缓冲近期 tick（客户端按 ts 去重），15s keepalive
- `GET  /api/ctp/md/health` 每 profile 连接状态/订阅集/tick 计数

## profile 与凭证

profile 与 `ctp_client` 同名（simnow / citic），凭证完全复用
`config/settings.yaml` + `.streamlit/secrets.toml` + 环境变量（见 `ctp_client/ctp_worker.py`），
本目录不存任何账号密码。缺凭证的 profile 启动时自动跳过。

## 运行（Python 3.13）

```bat
C:\Users\wang\AppData\Local\Programs\Python\Python313\python.exe ctp_md\run_worker.py --profiles simnow --port 5003
C:\Users\wang\AppData\Local\Programs\Python\Python313\python.exe ctp_md\run_worker.py --profiles citic  --port 5004
```

部署由 `.github/workflows/deploy.yml` 在桥接部署后以 pm2 进程 `ctp-md-simnow`(:5003) / `ctp-md-citic`(:5004) 拉起（best-effort）。
离线回放（无 SWIG 环境联调）：

```
python ctp_md/run_worker.py --kind replay --replay tests/fixtures/fu2610_20260918_ticks.jsonl --port 5003
```

仅仿真环境（simnow / 中信评测 66666），不接真实下单链路。
