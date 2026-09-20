#!/usr/bin/env python3
"""
BTC 1H MACD 背离实盘信号器 (可信口径)
- 每小时检查已确认的背离信号 (极值确认需 order 根K线, 无未来函数)
- 参数: order=3, SL=2.0 ATR, TP=3.0 ATR, max_hold=48h (回测 PF1.52, 两段稳定)
- 默认只输出信号(dry-run); 接入 trading/orders 或 OKXTrader 下单时务必加风控闸门
用法:
  python live_signal.py                       # 看当前信号
  python live_signal.py --loop --interval 300 # 持续轮询
"""
import os, sys, time, argparse
from datetime import datetime, timezone
import requests
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bt_divergence as bt  # noqa

PROXY = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}


def fetch_recent(inst, bar="1H", n=120):
    r = requests.get("https://www.okx.com/api/v5/market/candles",
                     params={"instId": inst, "bar": bar, "limit": str(n)},
                     proxies=PROXY, timeout=15)
    data = r.json()["data"]
    rows = []
    for c in reversed(data):  # OKX 返回是新->旧, 反转为时间正序
        rows.append(dict(datetime=datetime.fromtimestamp(int(c[0])/1000),
                         open=float(c[1]), high=float(c[2]), low=float(c[3]),
                         close=float(c[4]), vol=float(c[5])))
    return pd.DataFrame(rows)


def current_signal(inst="BTC-USDT-SWAP", order=3, atr_sl=2.0, atr_tp=3.0):
    df = fetch_recent(inst, "1H", 150)
    df["atr"] = bt.atr(df, 14)
    sigs = bt.divergences(df, order=order)
    if not sigs:
        return None
    last = sigs[-1]
    ei = last["confirm"]
    # 信号在最近2根K线内才算有效
    age = len(df) - 1 - ei
    if age > 2:
        return None
    entry = float(df["close"].iloc[ei]); a = float(df["atr"].iloc[ei])
    if last["side"] == "long":
        sl, tp = entry - atr_sl*a, entry + atr_tp*a
    else:
        sl, tp = entry + atr_sl*a, entry - atr_tp*a
    return dict(side=last["side"], entry=entry, sl=round(sl,2), tp=round(tp,2),
                atr=round(a,2), confirm_time=str(df["datetime"].iloc[ei]), age_bars=age,
                rr=atr_tp/atr_sl)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inst", default="BTC-USDT-SWAP")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--interval", type=int, default=300)
    args = ap.parse_args()
    seen = set()
    while True:
        try:
            sig = current_signal(args.inst)
            if sig and sig["confirm_time"] not in seen:
                seen.add(sig["confirm_time"])
                print(f"[{datetime.now()}] 🔔 {sig['side'].upper()} {args.inst} "
                      f"入场~{sig['entry']} SL{sig['sl']} TP{sig['tp']} "
                      f"ATR{sig['atr']} R:R={sig['rr']} (确认于{sig['confirm_time']})")
            elif not args.loop:
                print(f"[{datetime.now()}] 当前无新信号 (最新确认信号年龄={None if not sig else sig['age_bars']}根)")
        except Exception as e:
            print("error:", e)
        if not args.loop:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
