# ctp_md —— CTP MdApi 常驻行情服务（P1）

独立进程的 CTP 行情前置长连接，向 quant-agent 提供 tick 推送/快照。
**必须与 5002 webhook 桥接分进程**：CTP SWIG `.pyd`（仅 cp313）可能进程级崩溃，
独立进程不影响桥接主服务。

## 接口（端口 5003）

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
C:\Users\wang\AppData\Local\Programs\Python\Python313\python.exe ctp_md\run_worker.py --port 5003
```

部署由 `.github/workflows/deploy.yml` 在桥接部署后以 pm2 进程 `ctp-md-worker` 拉起（best-effort）。
离线回放（无 SWIG 环境联调）：

```
python ctp_md/run_worker.py --kind replay --replay tests/fixtures/fu2610_20260918_ticks.jsonl --port 5003
```

仅仿真环境（simnow / 中信评测 66666），不接真实下单链路。
