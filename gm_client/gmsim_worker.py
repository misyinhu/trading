# -*- coding: utf-8 -*-
"""掘金量化(gm) 模拟交易子进程 worker（与 ctp_worker 同风格，独立进程隔离）。

Flask 主服务以 subprocess 调起本脚本：通过本地掘金终端服务（localhost:7001）
连接模拟账户，执行 account/positions/order/cancel，结果以 RESULT_JSON=... 单行
打到 stdout 后退出。gm SDK 原生层若崩溃只杀子进程，不影响 Flask。

必须走 gm 的 run() 策略框架（mode=1 仿真），在 init 回调里调用交易/查询接口
（裸调 get_cash/order_volume 在原生层会阻塞退出）。

环境变量：
  GM_TOKEN      掘金 token
  GM_ACCOUNT    模拟账户 ID（UUID）
  GM_SERV_ADDR  终端服务地址（默认 localhost:7001）
  GM_ACTION     account / positions / order / cancel
  GM_ORDER_JSON 下单/撤单参数 JSON
"""
from __future__ import annotations
import os, sys, json, faulthandler
faulthandler.enable()

ACTION = os.environ.get("GM_ACTION", "account").strip().lower()
try:
    ORDER = json.loads(os.environ.get("GM_ORDER_JSON", "") or "{}")
except Exception as e:  # noqa: BLE001
    # 模块也会被 run() import，此处不能 sys.exit；记录后在 init 报错
    ORDER = {"_parse_error": str(e)}


def _emit(obj: dict) -> None:
    line = "RESULT_JSON=" + json.dumps(obj, ensure_ascii=False, default=str)
    try:
        print(line, flush=True)
    except Exception:  # noqa: BLE001
        pass
    # gm C sdk 在某些宿主下会接管 stdout，额外落结果文件保证可读取
    rf = os.environ.get("GM_RESULT_FILE", "")
    if rf:
        try:
            with open(rf, "w", encoding="utf-8") as f:
                f.write(line)
        except Exception:  # noqa: BLE001
            pass


# gm SDK 常量（数字）：side 1买/2卖；order_type 1限价/2市价；position_effect 1开/2平
def _num(v, default=0.0):
    try:
        if v in (None, ""):
            return default
        return float(v)
    except Exception:  # noqa: BLE001
        return default


def _norm_cash(c) -> dict:
    g = (lambda k: c.get(k) if isinstance(c, dict) else getattr(c, k, None))
    cur = g("currency")
    return {
        "account_id": g("account_id"),
        "balance": _num(g("nav")),                 # 总权益(净值)
        "available": _num(g("available")),         # 可用资金
        "market_value": _num(g("market_value")),   # 持仓市值
        "frozen": _num(g("frozen")),
        "pnl": _num(g("pnl")),
        "fpnl": _num(g("fpnl")),
        "currency": "CNY" if cur in (0, None) else str(cur),
        "channel": "gm",
    }


def _norm_positions(pos) -> list:
    out = []
    rows = []
    if pos is None:
        rows = []
    elif hasattr(pos, "to_dict"):
        rows = [pos]
    elif isinstance(pos, list):
        rows = pos
    else:
        try:
            rows = list(pos)  # DataFrame 可迭代为行
        except Exception:  # noqa: BLE001
            rows = []
    for r in rows:
        d = r.to_dict() if hasattr(r, "to_dict") else (dict(r) if not isinstance(r, dict) else r)
        vol = _num(d.get("volume"))
        if vol == 0:
            continue
        side = d.get("side")
        side_s = {1: "long", 2: "short"}.get(int(side), str(side)) if side not in (None, "") else ""
        out.append({
            "symbol": d.get("symbol"),
            "direction": side_s,
            "volume": int(vol),
            "avg_price": _num(d.get("vwap") or d.get("price")),
            "float_pnl": _num(d.get("fpnl")),
            "market_value": _num(d.get("market_value")),
            "channel": "gm",
        })
    return out


def init(context):
    acct = os.environ.get("GM_ACCOUNT", "")
    try:
        from gm.api import get_cash, get_position, order_volume, get_unfinished_orders, order_cancel
        if ACTION == "history":
            from gm.api import history as gm_history
            sym = ORDER["symbol"]
            freq = ORDER.get("frequency", "1h")
            # gm frequency 用秒；接受 '30m'/'1h'/'1d' 或秒数
            sec_map = {"60": 60, "1m": 60, "300": 300, "5m": 300,
                       "900": 900, "15m": 900, "1800": 1800, "30m": 1800,
                       "3600": 3600, "1h": 3600, "60m": 3600,
                       "86400": 86400, "1d": 86400, "1D": 86400}
            freq_s = sec_map.get(str(freq), 3600)
            # gm history 的 frequency 必须是字符串（内部 .strip()）：秒数加 's'，日线 '1d'
            freq_arg = "1d" if int(freq_s) == 86400 else f"{int(freq_s)}s"
            st = ORDER.get("start_time", "")
            et = ORDER.get("end_time", "")
            df = gm_history(symbol=sym, frequency=freq_arg, start_time=st,
                            end_time=et, df=True,
                            fields="bob,eob,open,high,low,close,volume,amount")
            bars = []
            try:
                for _, r in df.iterrows():
                    def _ts(v):
                        try:
                            return v.isoformat() if hasattr(v, "isoformat") else str(v)
                        except Exception:  # noqa: BLE001
                            return str(v)
                    bars.append({
                        "timestamp": _ts(r.get("eob") or r.get("bob")),
                        "open": _num(r.get("open")), "high": _num(r.get("high")),
                        "low": _num(r.get("low")), "close": _num(r.get("close")),
                        "volume": _num(r.get("volume")), "amount": _num(r.get("amount")),
                        "symbol": sym, "frequency": freq,
                    })
            except Exception as e:  # noqa: BLE001
                _emit({"ok": False, "status": "error", "error": f"history 解析失败: {e}"})
            else:
                _emit({"ok": True, "status": "logined", "symbol": sym,
                       "frequency": freq, "interval_min": freq_s / 60.0,
                       "bars": bars, "count": len(bars)})
        elif ACTION == "account":
            c = get_cash(account_id=acct)
            _emit({"ok": True, "status": "logined", "account": _norm_cash(c)})
        elif ACTION == "positions":
            p = get_position(account_id=acct)
            ps = _norm_positions(p)
            _emit({"ok": True, "status": "logined", "positions": ps, "count": len(ps)})
        elif ACTION == "order":
            sym = ORDER["symbol"]
            side = int(ORDER.get("side", 1))
            vol = int(float(ORDER.get("volume", 100)))
            otype = int(ORDER.get("order_type", 1))
            peff = int(ORDER.get("position_effect", 1))
            price = float(ORDER.get("price", 0.0) or 0.0)
            r = order_volume(symbol=sym, volume=vol, side=side, order_type=otype,
                             position_effect=peff, price=price, account=acct)
            items = r if isinstance(r, list) else [r]
            orders = []
            for it in items:
                d = it if isinstance(it, dict) else (it.to_dict() if hasattr(it, "to_dict") else {})
                orders.append({
                    "cl_ord_id": d.get("cl_ord_id"),
                    "symbol": d.get("symbol"),
                    "side": d.get("side"),
                    "price": _num(d.get("price")),
                    "volume": d.get("volume"),
                    "filled_volume": d.get("filled_volume"),
                    "status": d.get("status"),
                    "ord_rej_reason_detail": d.get("ord_rej_reason_detail", ""),
                })
            ok0 = bool(orders) and not orders[0].get("ord_rej_reason_detail")
            _emit({"ok": ok0, "status": "submitted" if ok0 else "rejected",
                   "action_result": orders[0] if orders else {}, "orders": orders})
        elif ACTION == "cancel":
            uo = get_unfinished_orders()
            want = ORDER.get("symbol", "")
            targets = []
            for row in (uo or []):
                d = row.to_dict() if hasattr(row, "to_dict") else dict(row)
                if not want or str(d.get("symbol")) == str(want):
                    targets.append(row)
            if not targets:
                _emit({"ok": True, "status": "nothing_to_cancel", "cancelled": 0})
            else:
                order_cancel(targets)
                _emit({"ok": True, "status": "cancel_submitted", "cancelled": len(targets)})
        else:
            _emit({"ok": False, "status": "bad_action", "error": f"unknown GM_ACTION={ACTION}"})
    except Exception as e:  # noqa: BLE001
        import traceback
        _emit({"ok": False, "status": "error", "error": f"{type(e).__name__}: {e}",
               "trace": traceback.format_exc()[-800:]})
    import threading
    threading.Timer(0.8, lambda: os._exit(0)).start()


def on_bar(context, bars):
    pass


if __name__ == "__main__":
    from gm.api import run, set_token, set_serv_addr
    token = os.environ.get("GM_TOKEN", "")
    addr = os.environ.get("GM_SERV_ADDR", "localhost:7001")
    set_token(token)
    set_serv_addr(addr)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    run(strategy_id="", filename="gm_worker", mode=1, token=token, serv_addr=addr)
