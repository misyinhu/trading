"""CTP MdApi 常驻行情 worker（独立进程，隔离 SWIG 原生崩溃风险）。

凭证复用 ctp_client 既有链路（config/settings.yaml + .streamlit/secrets.toml + 环境变量），
本文件不存任何账号密码。仅仿真环境使用（simnow / citic 评测 66666）。

用法（Python 3.13，SWIG 绑定仅 cp313）：
  python ctp_md/run_worker.py                         # simnow+citic，端口 5003
  python ctp_md/run_worker.py --profiles simnow --port 5003
  python ctp_md/run_worker.py --kind replay --replay tests/fixtures/fu2610_20260918_ticks.jsonl
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from flask import Flask

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ctp_md import MdWorkerManager, TickStore  # noqa: E402
from ctp_md.server import create_blueprint, health_components  # noqa: E402


def build_ctp_profiles(names: list[str]) -> dict:
    """从 ctp_client.ctp_worker 的 profile 装配器构造 worker 配置。"""
    from ctp_client.ctp_worker import _load_config

    out: dict = {}
    for name in names:
        c = _load_config(name)
        missing = c.get("_missing") or []
        if not c.get("md_server") or missing:
            print(f"[md-worker] profile={name} 跳过：缺配置 {missing or ['md_server']}",
                  file=sys.stderr, flush=True)
            continue
        out[name] = {
            "kind": "ctp_client",
            "md_front": c["md_server"],
            "broker_id": c["broker_id"],
            "user": c["user"],
            "password": c["password"],
            "auth_code": c.get("auth_code", ""),
            "app_id": c.get("app_id", ""),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", default="simnow,citic",
                    help="逗号分隔；与 ctp_client profile 同名")
    ap.add_argument("--port", type=int, default=5003)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--state", default=str(ROOT / "data" / "md_subscriptions.json"))
    ap.add_argument("--kind", default="ctp_client", choices=["ctp_client", "replay"])
    ap.add_argument("--replay", default="")
    args = ap.parse_args()

    if args.kind == "replay":
        if not args.replay:
            print("--replay 必填", file=sys.stderr)
            return 2
        profiles = {"replay": {"kind": "replay", "replay_path": args.replay,
                               "speed": 0, "exchange_id": "SHFE"}}
    else:
        profiles = build_ctp_profiles([p.strip() for p in args.profiles.split(",") if p.strip()])
    if not profiles:
        print("[md-worker] 没有可用 profile，退出", file=sys.stderr)
        return 1

    state_path = args.state
    Path(state_path).parent.mkdir(parents=True, exist_ok=True)
    store = TickStore()
    manager = MdWorkerManager(profiles, store, state_path)
    manager.start()

    app = Flask(__name__)
    app.register_blueprint(create_blueprint(manager, store))

    @app.get("/health")
    def health():
        comps = health_components(manager)
        ok = all(v["ok"] for v in comps.values())
        return {"status": "ok" if ok else "degraded", "components": comps}, 200

    print(f"[md-worker] profiles={list(profiles)} listening :{args.port}", flush=True)
    try:
        app.run(host=args.host, port=args.port, threaded=True)
    finally:
        manager.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
