#!/usr/bin/env python3
"""
RB-CL 3:2:1 Crack Spread Z-Score 分析与信号生成脚本。

用法:
    python rbcl_zscore.py                    # 只分析，不下单
    python rbcl_zscore.py --submit           # 分析 + 提交信号（半自动）
    python rbcl_zscore.py --auto             # 分析 + 自动下单（需白名单）
    python rbcl_zscore.py --days 60           # 指定历史天数

逻辑:
    3:2:1 Crack Spread = (3 × RB - 2 × CL) / 3
    Z-Score > +2.0  → 做空 crack (SELL RB + BUY CL)
    Z-Score < -2.0  → 做多 crack (BUY RB + SELL CL)
    阈值内          → 无交易
"""
import argparse, json, math, sys, os, requests, datetime

# ── 配置 ─────────────────────────────────────────────────────────────────────
TRADING_API = os.environ.get("TRADING_API", "http://100.99.204.126:5002")
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")  # 可选
Z_THRESHOLD_WARN = 2.0
Z_THRESHOLD_TRADE = 2.0   # 触发交易的Z阈值
DAYS = 60
HEADERS = {"Content-Type": "application/json"}


def fetch_quotes(symbols, days):
    """从 trading Flask 拉 IB 历史数据"""
    url = f"{TRADING_API}/api/quote"
    params = "&".join(f"symbols={s}" for s in symbols)
    resp = requests.get(f"{url}?symbols={','.join(symbols)}&days={days}", timeout=90)
    resp.raise_for_status()
    return resp.json()


def fetch_quotes_direct(host, port, symbols, days):
    """直接用 ib_insync 查 IB Gateway"""
    import ib_insync
    ib_insync.util.patchAsyncio()
    try:
        import nest_asyncio; nest_asyncio.apply()
    except ImportError:
        pass
    from ib_insync import IB, Contract

    ib = IB()
    ib.connect(host=host, port=port, clientId=993, timeout=10)
    if not ib.isConnected():
        raise RuntimeError("IB not connected")

    results = {}
    for sym in symbols:
        con = Contract(symbol=sym, secType="FUT")
        details = ib.reqContractDetails(con)
        if not details:
            results[sym] = {"error": "contract not found"}
            continue
        candidates = [d.contract for d in details
                     if d.contract.exchange == "NYMEX"
                     and d.contract.lastTradeDateOrContractMonth
                     and d.contract.lastTradeDateOrContractMonth >= "202609"]
        if not candidates:
            candidates = [d.contract for d in details if d.contract.exchange == "NYMEX"]
        if not candidates and details:
            candidates = [details[0].contract]

        bars = ib.reqHistoricalData(
            contract=candidates[0], endDateTime="",
            durationStr=f"{days} D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=False,
            formatDate=1,
            timeout=30
        )
        closes = [float(b.close) for b in bars] if bars else []
        results[sym] = {"hist_closes": closes}
    ib.disconnect()
    return results


def calc_crack_zscore(rb_closes, cl_closes, n=None):
    """
    计算 3:2:1 Crack Spread Z-Score。
    Spread = (3*RB_per_barrel - 2*CL) / 3
           = (3*RB_gallon*42 - 2*CL) / 3
    """
    n = min(len(rb_closes), len(cl_closes))
    spreads = []
    for i in range(n):
        rb_barrel = rb_closes[i] * 42  # USD/加仑 → USD/桶
        cl_price = cl_closes[i]           # USD/桶
        crack = (3 * rb_barrel - 2 * cl_price) / 3
        spreads.append(crack)

    mean = sum(spreads) / len(spreads)
    var = sum((s - mean) ** 2 for s in spreads) / len(spreads)
    std = math.sqrt(var)
    zscore = (spreads[-1] - mean) / std if std > 0 else 0.0
    return {
        "zscore": round(zscore, 4),
        "mean": round(mean, 4),
        "std": round(std, 4),
        "last_spread": round(spreads[-1], 4),
        "rb_last": rb_closes[-1],
        "cl_last": cl_closes[-1],
        "rb_barrel_last": round(rb_closes[-1] * 42, 4),
        "n": n,
        "recent_spreads": [round(s, 2) for s in spreads[-10:]],
    }


def signal_action(zscore, z_threshold=Z_THRESHOLD_TRADE):
    """根据 Z-Score 决定方向"""
    if zscore > z_threshold:
        return "short"   # 做空 crack: 卖RB + 买CL
    elif zscore < -z_threshold:
        return "long"    # 做多 crack: 买RB + 卖CL
    else:
        return None      # 无信号


def submit_signal(direction, zscore, stats, auto=False):
    """提交信号到 trading Signal API"""
    payload = {
        "source": "rbcl-zscore-script",
        "strategy": "rb-cl-spread",
        "direction": direction,
        "symbol": "RB-CL",
        "quantity": 1.0,
        "zscore": zscore,
        "reason": (f"Z-Score={zscore:.2f} 超过阈值±{z_threshold}，"
                   f"RB={stats['rb_last']:.4f} CL={stats['cl_last']:.2f}，"
                   f"做多做差" if direction == "long" else f"做空差价"),
        "stats": {k: v for k, v in stats.items()
                 if k not in ("recent_spreads",)},
    }
    if auto:
        payload["auto"] = True

    resp = requests.post(
        f"{TRADING_API}/api/signals",
        headers=HEADERS,
        json=payload,
        timeout=15
    )
    resp.raise_for_status()
    return resp.json()


def send_feishu(msg):
    if not FEISHU_WEBHOOK:
        return
    try:
        requests.post(FEISHU_WEBHOOK, json={"msg_type": "text", "content": {"text": msg}}, timeout=5)
    except Exception as e:
        print(f"[WARN] Feishu notification failed: {e}", file=sys.stderr)


def format_report(stats, action):
    z = stats["zscore"]
    trend = "↑偏高" if z > 0 else "↓偏低"
    signal_emoji = {"long": "[BUY RB / SELL CL]", "short": "[SELL RB / BUY CL]", None: "[HOLD]"}
    emoji = {"long": "BUY", "short": "SELL", None: "HOLD"}

    lines = [
        f"[RB-CL 3:2:1 Crack Spread] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"  Z-Score  = {z:+.4f}  ({trend})",
        f"  均值     = {stats['mean']:.4f}",
        f"  标准差   = {stats['std']:.4f}",
        f"  当前价差 = {stats['last_spread']:.4f}",
        f"",
        f"  RB       = {stats['rb_last']:.4f} USD/gallon  ({stats['rb_barrel_last']:.2f} USD/barrel)",
        f"  CL       = {stats['cl_last']:.2f} USD/barrel",
        f"",
        f"  数据量   = {stats['n']} 天",
        f"  交易信号 = {emoji.get(action, 'N/A')} {signal_emoji.get(action, '')}",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="RB-CL Z-Score 分析")
    parser.add_argument("--days", type=int, default=DAYS, help=f"历史天数 (默认{DAYS})")
    parser.add_argument("--z-threshold", type=float, default=Z_THRESHOLD_TRADE,
                        help=f"交易触发阈值 (默认{Z_THRESHOLD_TRADE})")
    parser.add_argument("--submit", action="store_true", help="提交信号到 trading API (半自动)")
    parser.add_argument("--auto", action="store_true", help="全自动下单 (需白名单)")
    parser.add_argument("--ib-direct", action="store_true",
                        help="直接连 IB Gateway，不走 Flask API")
    args = parser.parse_args()

    z_threshold = args.z_threshold

    # 拉数据
    print(f"Fetching RB/CL data ({args.days} days)...")
    try:
        if args.ib_direct:
            data = fetch_quotes_direct("127.0.0.1", 4002, ["RB", "CL"], args.days)
        else:
            data = fetch_quotes(["RB", "CL"], args.days)
    except Exception as e:
        print(f"ERROR: Failed to fetch quotes: {e}")
        sys.exit(1)

    rb_err = data.get("RB", {}).get("error")
    cl_err = data.get("CL", {}).get("error")
    if rb_err or cl_err:
        print(f"ERROR: {rb_err or cl_err}")
        sys.exit(1)

    rb_closes = data["RB"]["hist_closes"]
    cl_closes = data["CL"]["hist_closes"]

    if not rb_closes or not cl_closes:
        print("ERROR: No data returned for RB or CL")
        sys.exit(1)

    print(f"  RB: {len(rb_closes)} bars, last={rb_closes[-1]:.4f}")
    print(f"  CL: {len(cl_closes)} bars, last={cl_closes[-1]:.2f}")

    # 算 Z-Score
    stats = calc_crack_zscore(rb_closes, cl_closes)
    action = signal_action(stats["zscore"], z_threshold)

    # 打印报告
    report = format_report(stats, action)
    print("\n" + report)

    # 提交信号
    if args.auto and not args.submit:
        args.submit = True

    if args.submit and action:
        print(f"\nSubmitting {action} signal to trading API...")
        try:
            result = submit_signal(action, stats["zscore"], stats, auto=args.auto)
            signal_id = result.get("signal_id", result.get("id", ""))
            msg = f"[SIGNAL SUBMITTED] {report}\n\nSignal ID: {signal_id}"
            print(f"\n[OK] Signal submitted: {signal_id}")
            send_feishu(msg)
        except Exception as e:
            print(f"ERROR: Failed to submit signal: {e}", file=sys.stderr)
            send_feishu(f"[ERROR] RB-CL signal submit failed: {e}")
    elif args.submit and not action:
        print("\n[HOLD] No signal (Z-Score within threshold)")
    else:
        print("\n[DRY RUN] Use --submit to send signal, --auto for auto-execute")


if __name__ == "__main__":
    main()
