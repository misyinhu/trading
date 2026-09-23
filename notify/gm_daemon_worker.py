# -*- coding: utf-8 -*-
"""掘金(gm) 常驻历史查询 daemon worker。

与一次性 gmsim_worker 的区别：gm.run() 框架只在进程启动时初始化一次
（冷启动约 60~120s），之后所有 history 查询都在已连接的 SDK 上热执行，
通过任务目录串行派发，避免每次查询都重新冷启动。

协议（JOBS_DIR，默认 C:/projects/gm_env/gm_jobs）：
  task_<cid>.json    bridge 写入：{symbol,frequency,start_time,end_time,enqueued_ts}
  result_<cid>.json  worker 写入：{ok,...}/ {ok:False,error,...}
  daemon_heartbeat.json：{pid,started_at,ts,status,done,last_error}

任务一次只处理一个（gm SDK 查询串行最稳）；worker 崩溃后由 bridge 重启，
未删除的 task 文件会被新进程继续处理，结果幂等。
"""
from __future__ import annotations
import os, sys, json, glob, time, threading, faulthandler
faulthandler.enable()

JOBS_DIR = os.environ.get("GM_JOBS_DIR", r"C:\projects\gm_env\gm_jobs").replace("\\", "/")
HEARTBEAT_PATH = JOBS_DIR + "/daemon_heartbeat.json"
STARTED_AT = time.time()
STATE = {"busy": False, "done": 0, "last_error": ""}

FREQ_MAP = {"60": 60, "1m": 60, "300": 300, "5m": 300,
            "900": 900, "15m": 900, "1800": 1800, "30m": 1800,
            "3600": 3600, "1h": 3600, "60m": 3600,
            "86400": 86400, "1d": 86400, "1D": 86400}


def _hb(status: str) -> None:
    payload = {"pid": os.getpid(), "started_at": STARTED_AT, "ts": time.time(),
               "status": status, "busy": STATE["busy"], "done": STATE["done"],
               "last_error": STATE["last_error"][-300:]}
    tmp = HEARTBEAT_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, HEARTBEAT_PATH)
    except Exception:
        pass


def _write_result(cid: str, obj: dict) -> None:
    obj = dict(obj)
    obj["worker_ts"] = time.time()
    try:
        with open(f"{JOBS_DIR}/result_{cid}.json.tmp", "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, default=str)
        os.replace(f"{JOBS_DIR}/result_{cid}.json.tmp", f"{JOBS_DIR}/result_{cid}.json")
    except Exception as exc:
        STATE["last_error"] = f"write result {cid}: {exc}"


def _run_history(order: dict) -> dict:
    from gm.api import history as gm_history
    sym = order["symbol"]
    freq_s = FREQ_MAP.get(str(order.get("frequency", "1h")), 3600)
    freq_arg = "1d" if freq_s == 86400 else f"{int(freq_s)}s"
    df = gm_history(symbol=sym, frequency=freq_arg,
                    start_time=order.get("start_time", ""),
                    end_time=order.get("end_time", ""), df=True,
                    fields="bob,eob,open,high,low,close,volume,amount")
    bars = []
    for _, r in df.iterrows():
        ts = r.get("eob") or r.get("bob")
        bars.append({
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "open": float(r.get("open")) if r.get("open") is not None else None,
            "high": float(r.get("high")) if r.get("high") is not None else None,
            "low": float(r.get("low")) if r.get("low") is not None else None,
            "close": float(r.get("close")) if r.get("close") is not None else None,
            "volume": float(r.get("volume")) if r.get("volume") is not None else None,
            "amount": float(r.get("amount")) if r.get("amount") is not None else None,
            "symbol": sym, "frequency": order.get("frequency", "1h"),
        })
    return {"ok": True, "status": "logined", "symbol": sym,
            "frequency": order.get("frequency", "1h"),
            "interval_min": freq_s / 60.0, "bars": bars, "count": len(bars)}


def _poll(context) -> None:
    _hb("ready")
    if STATE["busy"]:
        return
    tasks = sorted(glob.glob(f"{JOBS_DIR}/task_*.json"))
    if not tasks:
        return
    path = tasks[0]
    cid = os.path.basename(path)[len("task_"):-len(".json")]
    try:
        with open(path, encoding="utf-8") as f:
            order = json.load(f)
    except Exception as exc:
        _write_result(cid, {"ok": False, "status": "error",
                            "error": f"任务文件解析失败: {exc}"})
        try:
            os.remove(path)
        except OSError:
            pass
        return
    STATE["busy"] = True
    _hb("busy")
    t0 = time.time()
    try:
        res = _run_history(order)
        res["elapsed"] = round(time.time() - t0, 2)
        _write_result(cid, res)
        STATE["done"] += 1
        STATE["last_error"] = ""
    except Exception as exc:
        STATE["last_error"] = f"{type(exc).__name__}: {exc}"
        _write_result(cid, {"ok": False, "status": "error",
                            "error": STATE["last_error"]})
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
        STATE["busy"] = False
        _hb("ready")


def init(context):
    os.makedirs(JOBS_DIR, exist_ok=True)
    for stale in glob.glob(f"{JOBS_DIR}/result_*.tmp"):
        try:
            os.remove(stale)
        except OSError:
            pass
    _hb("ready")
    from gm.api import timer
    tr = timer(_poll, 1, 1)
    if tr.get("status") != 0:
        # timer 注册失败时退化为独立线程（SDK 在非策略线程查询可能阻塞）
        STATE["last_error"] = f"timer failed {tr}"

        def _loop():
            while True:
                time.sleep(1.0)
                try:
                    _poll(None)
                except Exception:
                    pass
        threading.Thread(target=_loop, name="gm-poll", daemon=True).start()


def on_bar(context, bars):
    pass


if __name__ == "__main__":
    from gm.api import run, set_token, set_serv_addr
    token = os.environ.get("GM_TOKEN", "")
    addr = os.environ.get("GM_SERV_ADDR", "localhost:7001")
    os.makedirs(JOBS_DIR, exist_ok=True)
    set_token(token)
    set_serv_addr(addr)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    _hb("starting")
    run(strategy_id="", filename="gm_daemon_worker", mode=1,
        token=token, serv_addr=addr)
