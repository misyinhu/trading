#!/usr/bin/env python3
"""分页下载 OKX 永续历史K线 -> CSV。走 127.0.0.1:7890 代理。"""
import os, sys, time, csv, requests
from datetime import datetime

os.environ.setdefault("HTTP_PROXY", "http://127.0.0.1:7890")
os.environ.setdefault("HTTPS_PROXY", "http://127.0.0.1:7890")

BASE = "https://www.okx.com/api/v5/market/history-candles"
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def fetch(inst, bar, total_bars):
    """用 after 分页向更早拉取。每页最多100根。"""
    out = []
    after = None
    while len(out) < total_bars:
        params = {"instId": inst, "bar": bar, "limit": "100"}
        if after:
            params["after"] = after
        r = requests.get(BASE, params=params, timeout=20)
        j = r.json()
        if j.get("code") != "0" or not j.get("data"):
            print("stop:", j); break
        chunk = j["data"]
        out.extend(chunk)
        after = chunk[-1][0]  # 最早一根的 ts
        print(f"  {inst} {bar}: {len(out)}/{total_bars}  earliest={datetime.fromtimestamp(int(after)/1000)}")
        time.sleep(0.15)
        if len(chunk) < 100:
            break
    out = out[:total_bars]
    path = os.path.join(DATA, f"{inst.replace('-','_')}_{bar}.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["datetime", "open", "high", "low", "close", "vol"])
        for c in out:
            w.writerow([datetime.fromtimestamp(int(c[0]) / 1000),
                        c[1], c[2], c[3], c[4], c[5]])
    print(f"saved {path} ({len(out)} bars)")
    return path


if __name__ == "__main__":
    inst = sys.argv[1] if len(sys.argv) > 1 else "BTC-USDT-SWAP"
    bar = sys.argv[2] if len(sys.argv) > 2 else "1H"
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 8000
    fetch(inst, bar, n)
