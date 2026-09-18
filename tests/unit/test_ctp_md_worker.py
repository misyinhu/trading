"""P1 trading 侧 md worker：回放连接器 + HTTP 契约（snapshot/stream/subscribe/health）。"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask  # noqa: E402

from ctp_md import MdWorkerManager, TickStore  # noqa: E402
from ctp_md.server import create_blueprint, health_components  # noqa: E402


def _tick(iid, ts, price, vol):
    return {"profile": "simnow", "instrument_id": iid, "exchange_id": "SHFE",
            "ts_exchange": f"20260918 {ts}", "ts_recv": ts,
            "last_price": price, "volume": vol, "turnover": 0.0,
            "open_interest": 0, "bid1": price - 1, "ask1": price + 1,
            "bid_vol1": 1, "ask_vol1": 1, "upper_limit": 5808,
            "lower_limit": 4205, "average_price": 0.0}


@pytest.fixture()
def harness(tmp_path):
    replay = tmp_path / "ticks.jsonl"
    replay.write_text("\n".join(json.dumps(_tick("fu2610", f"09:06:0{i}.000",
                                                 4790 + i, 10 + i), ensure_ascii=False)
                                for i in range(1, 4)), encoding="utf-8")
    state = tmp_path / "subs.json"
    store = TickStore()
    mgr = MdWorkerManager(
        {"simnow": {"kind": "replay", "replay_path": str(replay),
                    "exchange_id": "SHFE", "speed": 0}},
        store, str(state))
    app = Flask(__name__)
    app.register_blueprint(create_blueprint(mgr, store))
    return app, mgr, store, state


def test_subscribe_persists_and_feeds_snapshot(harness):
    app, mgr, store, state = harness
    mgr.start()
    c = app.test_client()
    r = c.post("/api/ctp/md/subscribe",
               json={"profile": "simnow", "instruments": ["fu2610"]})
    assert r.status_code == 200 and r.get_json()["subscriptions"] == ["fu2610"]
    time.sleep(0.6)
    # 回放结束但最新 tick 已在内存
    r = c.get("/api/ctp/md/snapshot?profile=simnow&instrument=fu2610")
    assert r.status_code == 200
    assert r.get_json()["tick"]["last_price"] == 4793
    # 未订阅/无 tick → 404 + 明确标记
    r = c.get("/api/ctp/md/snapshot?profile=simnow&instrument=fu9999")
    assert r.status_code == 404 and r.get_json()["subscribed"] is False
    mgr.stop()


def test_subscription_set_survives_restart(tmp_path, harness):
    app, mgr, store, state = harness
    mgr.start()
    app.test_client().post("/api/ctp/md/subscribe",
                           json={"profile": "simnow", "instruments": ["fu2610", "fu2611"]})
    mgr.stop()
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["profiles"]["simnow"] == ["fu2610", "fu2611"]
    # 新 manager 自动恢复订阅集
    mgr2 = MdWorkerManager(
        {"simnow": {"kind": "replay", "replay_path": str(state.parent / "none.jsonl")}},
        TickStore(), str(state))
    assert mgr2.subs.get("simnow") == {"fu2610", "fu2611"}


def test_sse_stream_and_unsubscribe(harness):
    import socket, threading
    import werkzeug.serving
    import requests as rq
    from ctp_md.schema import Tick

    app, mgr, store, state = harness
    mgr.start()
    sock = socket.socket(); sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]; sock.close()
    srv = werkzeug.serving.make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        rq.post(f"{base}/api/ctp/md/subscribe",
                json={"profile": "simnow", "instruments": ["fu2610"]}, timeout=3)
        time.sleep(0.6)

        def stream_and_collect(publish):
            got = []
            with rq.get(f"{base}/api/ctp/md/stream?profile=simnow&instruments=fu2610",
                        stream=True, timeout=5) as resp:
                assert resp.headers["Content-Type"].startswith("text/event-stream")
                t = threading.Thread(target=publish, daemon=True)
                t.start()
                for line in resp.iter_lines():
                    if line and line.startswith(b"data:"):
                        got.append(line.decode())
                        break
            return got

        got = stream_and_collect(lambda: (time.sleep(0.3),
                                          store.publish(Tick(**_tick("fu2610", "09:07:00.500", 4798, 40)))))
        assert got and "fu2610" in got[0]
        # 过滤生效：推别的合约，2s 内收不到任何 data 帧
        import queue as _q
        got2: list = []
        with rq.get(f"{base}/api/ctp/md/stream?profile=simnow&instruments=fu2610",
                    stream=True, timeout=5) as resp:
            threading.Thread(target=lambda: (time.sleep(0.3),
                store.publish(Tick(**_tick("fu9999", "09:07:00.600", 1, 1)))),
                daemon=True).start()
            try:
                for line in resp.iter_lines():
                    if line and line.startswith(b"data:"):
                        got2.append(line.decode()); break
            except rq.exceptions.ConnectionError:
                pass
        assert all("fu9999" not in g for g in got2)

        r = rq.post(f"{base}/api/ctp/md/unsubscribe",
                    json={"profile": "simnow", "instruments": ["fu2610"]}, timeout=3)
        assert r.json()["subscriptions"] == []
    finally:
        srv.shutdown()
        mgr.stop()


def test_sse_catch_up_on_late_connect(harness):
    """SSE 晚于 tick 突发建立：连接时补发环形缓冲近期 tick，不漏根。"""
    import socket, threading, json
    import werkzeug.serving
    import requests as rq

    app, mgr, store, state = harness
    mgr.start()
    sock = socket.socket(); sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]; sock.close()
    srv = werkzeug.serving.make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        rq.post(f"{base}/api/ctp/md/subscribe",
                json={"profile": "simnow", "instruments": ["fu2610"]}, timeout=3)
        time.sleep(0.8)  # 等回放播完（此刻没有任何 SSE 消费者）
        got = []
        with rq.get(f"{base}/api/ctp/md/stream?profile=simnow&instruments=fu2610",
                    stream=True, timeout=8) as resp:
            for line in resp.iter_lines():
                if line and line.startswith(b"data:"):
                    got.append(json.loads(line[5:]))
                    if len(got) == 3:
                        break
        assert [t["last_price"] for t in got] == [4791, 4792, 4793]
    finally:
        srv.shutdown()
        mgr.stop()


def test_health_components_shape(harness):
    app, mgr, store, state = harness
    mgr.start()
    time.sleep(0.6)
    h = health_components(mgr)
    assert "ctp_md_simnow" in h
    assert set(h["ctp_md_simnow"]) >= {"ok", "state", "subscriptions", "tick_count"}
    mgr.stop()


def test_schema_ctp_raw_mapping_and_backfill():
    from ctp_md.schema import tick_from_ctp, make_exchange_ts
    raw = type("D", (), {
        "InstrumentID": "fu2610", "ExchangeID": "SHFE", "ActionDay": "20260918",
        "UpdateTime": "09:07:00", "UpdateMillisec": 500, "LastPrice": 4798.0,
        "Volume": 44310, "Turnover": 0.0, "OpenInterest": 11290,
        "BidPrice1": 4797.0, "AskPrice1": 4798.0, "BidVolume1": 3, "AskVolume1": 1,
        "UpperLimitPrice": 5808.0, "LowerLimitPrice": 4205.0,
        "AveragePrice": 0.0})()
    t = tick_from_ctp(raw, "simnow")
    assert t.ts_exchange == "20260918 09:07:00.500"
    assert t.volume == 44310 and t.bid1 == 4797.0
    assert make_exchange_ts("20260918", "09:07:00", 5) == "20260918 09:07:00.005"
    # 缺字段用最近快照补齐
    partial = type("D", (), {"InstrumentID": "fu2610", "ExchangeID": "",
                             "ActionDay": "20260918", "UpdateTime": "09:07:01",
                             "UpdateMillisec": 0, "LastPrice": 4799.0,
                             "Volume": 44320})()
    t2 = tick_from_ctp(partial, "simnow", last_snapshot=t)
    assert t2.upper_limit == 5808.0 and t2.bid1 == 4797.0
