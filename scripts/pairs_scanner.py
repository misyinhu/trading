#!/usr/bin/env python3
"""
Pairs Z-Score Scanner — 自动扫描多个配对，发均值回归信号。

Priority pairs (已验证相关性):
  crack_spread:   RB/CL (3:2:1), HO/CL (3:1)
  ratio_pairs:   GC/SI, ZC/ZS, ZL/ZS, PL/PA
  calendar:       NG(Dec26)/NG(Nov26)

Usage:
  python pairs_scanner.py                    # 只扫描分析
  python pairs_scanner.py --auto              # 自动下单（白名单）
  python pairs_scanner.py --min-z 1.5         # 更敏感的阈值
  python pairs_scanner.py --top 3            # 最多同时跑3个策略
"""
import argparse, json, math, sys, os, requests, datetime, time
from typing import Dict, List, Tuple, Optional

# Disable system proxy (winclaw has proxy劫持，requests会走错)
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
           "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"

TRADING_API = os.environ.get("TRADING_API", "http://100.99.204.126:5002")
HEADERS = {"Content-Type": "application/json"}
DAYS = 30

# ── 配对定义 ────────────────────────────────────────────────────────────────
# 每个 pair: name, legs=[(symbol, multiplier, direction_ratio), ...]
# direction_ratio: >0=同向, <0=反向
# spread计算: sum(sym_i * ratio_i)
PAIRS = [
    # 能源类
    {
        "name": "RB_CL_crack",
        "strategy": "rb-cl-spread",  # 复用已有策略
        "legs": [
            {"symbol": "RB", "ratio": 3.0},
            {"symbol": "CL", "ratio": -2.0},
        ],
        "unit": "USD/barrel",
        "description": "3:2:1 Crack Spread (买RB 卖CL)",
        "type": "crack",
    },
    {
        "name": "HO_CL_diesel",
        "strategy": "ho-cl-spread",
        "legs": [
            {"symbol": "HO", "ratio": 3.0},
            {"symbol": "CL", "ratio": -2.0},
        ],
        "unit": "USD/barrel",
        "description": "3:1 Diesel Crack (买HO 卖CL)",
        "type": "crack",
    },
    # 贵金属比率
    {
        "name": "GC_SI_ratio",
        "strategy": "gc-si-ratio",
        "legs": [
            {"symbol": "GC", "ratio": 1.0},
            {"symbol": "SI", "ratio": -1.0},
        ],
        "unit": "USD/troz",
        "description": "Gold/Silver Ratio (金/银比)",
        "type": "ratio",
    },
    {
        "name": "PL_PA_ratio",
        "strategy": "pl-pa-ratio",
        "legs": [
            {"symbol": "PL", "ratio": 1.0},
            {"symbol": "PA", "ratio": -1.0},
        ],
        "unit": "USD/troz",
        "description": "Platinum/Palladium Ratio",
        "type": "ratio",
    },
    # 农产品
    {
        "name": "ZC_ZS_spread",
        "strategy": "zc-zs-spread",
        "legs": [
            {"symbol": "ZC", "ratio": 1.0},   # corn cents/bu
            {"symbol": "ZS", "ratio": -1.0}, # soy  cents/bu
        ],
        "unit": "cents/bu",
        "description": "Corn vs Soybean Spread",
        "type": "spread",
    },
    {
        "name": "ZL_ZS_spread",
        "strategy": "zl-zs-spread",
        "legs": [
            {"symbol": "ZL", "ratio": 1.0},   # soy oil cents/lb
            {"symbol": "ZS", "ratio": -1.0}, # soy  cents/bu
        ],
        "unit": "mixed",
        "description": "Soybean Oil vs Soybean",
        "type": "spread",
    },
    # 股指（需要方向归一化）
    {
        "name": "ES_NQ_spread",
        "strategy": "es-nq-spread",
        "legs": [
            {"symbol": "ES", "ratio": 1.0},
            {"symbol": "NQ", "ratio": -1.0},
        ],
        "unit": "points",
        "description": "S&P vs Nasdaq Spread",
        "type": "spread",
    },
    # 港股指数（HKFE 期货，multiplier=50）
    {
        "name": "HSTECH_HSI",
        "strategy": "pairs-spread",
        "legs": [
            {"symbol": "HSTECH", "ratio": 1.0},   # long → BUY HSTECH
            {"symbol": "HSI",     "ratio": -1.0},  # long → SELL HSI
        ],
        "unit": "points",
        "description": "Hang Seng Tech vs Hang Seng Index",
        "type": "spread",
    },
    # 农产品扩展（2026-08-25 新增）
    {
        "name": "ZC_ZM_spread",
        "strategy": "pairs-spread",
        "legs": [
            {"symbol": "ZC", "ratio": 1.0},    # corn (cents/bu)
            {"symbol": "ZM", "ratio": -1.0},   # soymeal (cents/lb → normalized)
        ],
        "unit": "mixed",
        "description": "Corn vs Soybean Meal Spread (feed ratio)",
        "type": "spread",
    },
    {
        "name": "ZW_ZC_spread",
        "strategy": "pairs-spread",
        "legs": [
            {"symbol": "ZW", "ratio": 1.0},    # wheat (cents/bu)
            {"symbol": "ZC", "ratio": -1.0},   # corn (cents/bu)
        ],
        "unit": "cents/bu",
        "description": "Wheat vs Corn Spread (SW/CZ)",
        "type": "spread",
    },
]

# ── 数据拉取 ───────────────────────────────────────────────────────────────
def fetch_all_quotes(symbols: List[str], days: int) -> Dict[str, List[float]]:
    """从 Flask API 拉历史数据"""
    url = f"{TRADING_API}/api/quote"
    resp = requests.get(url, params={"symbols": ",".join(symbols), "days": days}, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    result = {}
    for sym, v in data.items():
        if "error" not in v and "hist_closes" in v:
            result[sym] = v["hist_closes"]
    return result


def fetch_all_quotes_direct(host, port, symbols, days):
    """直接连 IB Gateway（用于 winclaw 本地运行）"""
    import ib_insync
    ib_insync.util.patchAsyncio()
    try:
        import nest_asyncio; nest_asyncio.apply()
    except ImportError:
        pass
    from ib_insync import IB, Contract

    ib = IB()
    ib.connect(host=host, port=port, clientId=991, timeout=10)
    if not ib.isConnected():
        raise RuntimeError("IB not connected")

    result = {}
    for sym in symbols:
        con = Contract(symbol=sym, secType="FUT")
        details = ib.reqContractDetails(con)
        if not details:
            continue
        # pick first NYMEX or CME or HKFE
        candidates = [d.contract for d in details
                     if d.contract.exchange in ('NYMEX', 'CME', 'CBOT', 'COMEX', 'NYBOT', 'HKFE')
                     and d.contract.lastTradeDateOrContractMonth
                     and d.contract.lastTradeDateOrContractMonth >= '202609']
        contract = candidates[0] if candidates else details[0].contract
        bars = ib.reqHistoricalData(contract=contract, endDateTime='',
            durationStr=f'{days} D', barSizeSetting='1 day',
            whatToShow='TRADES', useRTH=False, formatDate=1, timeout=30)
        if bars:
            result[sym] = [float(b.close) for b in bars]
    ib.disconnect()
    return result


# ── Z-Score 计算 ────────────────────────────────────────────────────────────
def calc_spread_zscore(closes_list: List[List[float]]) -> Tuple[float, float, float, float]:
    """
    计算配对价差 Z-Score。
    spread_i = sum(ratio_j * price_j_i) for all legs
    Returns: (zscore, mean, std, last_spread)
    """
    n = min(len(c) for c in closes_list)
    spreads = []
    for i in range(n):
        s = sum(closes_list[j][i] for j in range(len(closes_list)))
        spreads.append(s)

    mean = sum(spreads) / len(spreads)
    var = sum((x - mean) ** 2 for x in spreads) / len(spreads)
    std = math.sqrt(var) if var > 0 else 0.001
    zscore = (spreads[-1] - mean) / std
    return zscore, mean, std, spreads[-1]


def calc_ratio_zscore(closes_a: List[float], closes_b: List[float]) -> Tuple[float, float, float, float]:
    """计算价格比率 Z-Score: ratio = a / b"""
    n = min(len(closes_a), len(closes_b))
    ratios = [closes_a[i] / closes_b[i] for i in range(n)]
    mean = sum(ratios) / len(ratios)
    var = sum((r - mean) ** 2 for r in ratios) / len(ratios)
    std = math.sqrt(var) if var > 0 else 0.001
    zscore = (ratios[-1] - mean) / std
    return zscore, mean, std, ratios[-1]


# ── 信号决策 ───────────────────────────────────────────────────────────────
def decide_direction(zscore: float, pair_type: str) -> Optional[str]:
    """
    根据 Z-Score 和配对类型决定方向。
    crack:  spread高→做空(卖原油买汽油)，spread低→做多(买原油卖汽油)
            但实际上: crack高=炼油利润高，通常均值回归
            所以: Z>2 → 做空crack (short), Z<-2 → 做多crack (long)
    ratio:  ratio高→做空ratio (short), ratio低→做多ratio (long)
    spread: spread高→做空spread (short), spread低→做多spread (long)
    """
    threshold = 2.0
    if abs(zscore) < threshold:
        return None
    # spread/ratio高 → short, spread/ratio低 → long
    if zscore > threshold:
        return "short"
    else:
        return "long"


def direction_legs(direction: str, legs: List[dict]) -> List[dict]:
    """
    根据方向决定每条腿的 action。
    ratio/spread 类型: 同向于 ratio>0 的 leg。
    """
    result = []
    for leg in legs:
        ratio = leg["ratio"]
        # ratio>0 的腿，long=buy, short=sell
        # ratio<0 的腿，long=sell, short=buy (反向)
        if direction == "long":
            action = "BUY" if ratio > 0 else "SELL"
        else:  # short
            action = "SELL" if ratio > 0 else "BUY"
        result.append({**leg, "action": action})
    return result


# ── 策略注册 ───────────────────────────────────────────────────────────────
def ensure_strategy_registered(name: str, legs: List[dict], pair_type: str):
    """确保策略已注册到 strategy_registry"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from orders.strategy_registry import get_registry, StrategySpec
        registry = get_registry()
        if registry.get(name):
            return  # already registered
        # compute default quantities
        quantities = {}
        for leg in legs:
            sym = leg["symbol"]
            ratio = abs(leg["ratio"])
            quantities[sym] = ratio

        registry.register(StrategySpec(
            name=name,
            description=f"Auto-scanned pair: {name}",
            exchange="IB",
            required_params=["zscore"],
            param_constraints={"zscore": (-4.0, 4.0)},
            default_quantity=1.0,
            spread_symbols=",".join(l["symbol"] for l in legs),
        ))
        print(f"  [REGISTERED] strategy: {name}")
    except Exception as e:
        print(f"  [WARN] Could not register strategy {name}: {e}")


# ── 信号提交 ───────────────────────────────────────────────────────────────
def submit_signal(pair_name: str, strategy: str, direction: str,
                 zscore: float, stats: dict, legs: List[dict],
                 auto: bool = False) -> Optional[str]:
    """提交信号到 trading API（统一 pairs-spread 格式）"""
    try:
        payload = {
            "source": "pairs-scanner",
            "strategy": strategy,
            "direction": direction,
            "symbol": pair_name,
            "quantity": 1.0,
            "zscore": round(zscore, 4),
            "legs": legs,  # [{"symbol": "PL", "action": "SELL", "quantity": 1.0}, ...]
            "reason": f"[AUTO] {pair_name} Z={zscore:.2f} → {direction} "
                      f"spread={stats.get('last', 'N/A'):.4f}",
            "pair_stats": {k: round(v, 4) if isinstance(v, float) else v
                         for k, v in stats.items()},
        }
        if auto:
            payload["auto"] = True

        resp = requests.post(f"{TRADING_API}/api/signals",
                             headers=HEADERS, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        sig_id = data.get("signal_id") or data.get("id", "")
        print(f"    Signal submitted: {sig_id} status={data.get('status')}")
        return sig_id
    except Exception as e:
        print(f"    Signal submit FAILED: {e}")
        return None


# ── 主扫描逻辑 ─────────────────────────────────────────────────────────────
def scan_pairs(min_z: float = 2.0, auto: bool = False,
               top_n: int = 3, days: int = 30,
               ib_direct: bool = False) -> List[dict]:
    """扫描所有配对，返回触发信号的列表"""

    # 收集所有需要的 symbol
    all_symbols = list({leg["symbol"] for pair in PAIRS for leg in pair["legs"]})

    print(f"Fetching data for {len(all_symbols)} symbols ({days} days)...")
    try:
        if ib_direct:
            data = fetch_all_quotes_direct("127.0.0.1", 4002, all_symbols, days)
        else:
            data = fetch_all_quotes(all_symbols, days)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    results = []

    for pair in PAIRS:
        name = pair["name"]
        legs = pair["legs"]
        pair_type = pair["type"]

        # 拉数据
        closes_list = []
        leg_prices = {}
        ok = True
        for leg in legs:
            sym = leg["symbol"]
            closes = data.get(sym)
            if not closes:
                print(f"  SKIP {name}: no data for {sym}")
                ok = False
                break
            closes_list.append(closes)
            leg_prices[sym] = closes[-1]

        if not ok:
            continue

        # 计算 Z-Score
        if pair_type == "ratio":
            zscore, mean, std, last = calc_ratio_zscore(closes_list[0], closes_list[1])
            stats = {"zscore": zscore, "mean": mean, "std": std,
                     "last": last, "leg_prices": leg_prices}
        else:
            zscore, mean, std, last = calc_spread_zscore(closes_list)
            stats = {"zscore": zscore, "mean": mean, "std": std,
                     "last": last, "leg_prices": leg_prices}

        direction = decide_direction(zscore, pair_type)

        print(f"  {name:25s} Z={zscore:+.3f}  mean={mean:10.4f}  "
              f"last={last:10.4f}  [{direction or 'HOLD':5s}]")

        if direction and abs(zscore) >= min_z:
            results.append({
                "pair": name,
                "strategy": pair["strategy"],
                "direction": direction,
                "zscore": zscore,
                "stats": stats,
                "legs": legs,
                "pair_type": pair_type,
                "description": pair["description"],
            })

    # 按 |Z| 排序，取最强的 top_n
    results.sort(key=lambda x: abs(x["zscore"]), reverse=True)
    results = results[:top_n]

    print(f"\n{'='*60}")
    print(f"Signals triggered: {len(results)}/{len(PAIRS)}")
    for r in results:
        print(f"  {r['direction'].upper():5s} {r['pair']:25s} Z={r['zscore']:+.3f}  {r['description']}")

    return results


# ── 自动执行 ────────────────────────────────────────────────────────────────
AUTO_WHITELIST = {"pairs-scanner", "rbcl-zscore-script", "smoke-test"}


def execute_signals(signals: List[dict], auto: bool = False):
    """对每个信号提交到 trading API（统一 pairs-spread 策略）"""
    submitted = []
    for sig in signals:
        # 检查 auto 权限
        source = "pairs-scanner"
        if auto and source not in AUTO_WHITELIST:
            print(f"  [BLOCKED] {sig['pair']}: source '{source}' not in whitelist")
            continue

        # scanner 的 direction 已经是正确的均值回归方向
        # 用 direction_legs 计算每条腿的 action
        direction = sig["direction"]
        raw_legs = sig["legs"]  # [{"symbol": "PL", "ratio": 1.0}, ...]
        legs_with_action = direction_legs(direction, raw_legs)

        sig_id = submit_signal(
            pair_name=sig["pair"],
            strategy="pairs-spread",   # 统一用通用配对策略
            direction=direction,
            zscore=sig["zscore"],
            stats=sig["stats"],
            legs=legs_with_action,      # 带上完整 legs（含 action）
            auto=auto,
        )
        if sig_id:
            submitted.append((sig["pair"], sig_id))

    return submitted


# ── P&L 追踪 ───────────────────────────────────────────────────────────────
def check_pnl():
    """查询当前账户 P&L"""
    try:
        resp = requests.get(f"{TRADING_API}/positions", timeout=10)
        data = resp.json()
        positions = data.get("positions", [])
        return {"positions": len(positions), "items": positions}
    except Exception as e:
        return {"error": str(e)}


# ── CLI ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Pairs Z-Score Scanner")
    parser.add_argument("--days", type=int, default=DAYS, help="历史天数")
    parser.add_argument("--min-z", type=float, default=2.0, help="最小Z阈值")
    parser.add_argument("--top", type=int, default=3, help="最多同时信号数")
    parser.add_argument("--auto", action="store_true", help="自动下单（需白名单）")
    parser.add_argument("--scan-only", action="store_true", help="仅扫描不提交信号")
    parser.add_argument("--ib-direct", action="store_true", help="直连IB Gateway")
    args = parser.parse_args()

    print(f"[Pairs Scanner] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Days={args.days}  MinZ={args.min_z}  Top={args.top}  Auto={args.auto}")
    print()

    # 当前持仓
    pnl = check_pnl()
    if "error" not in pnl:
        print(f"[Positions] {pnl['positions']} open positions")
        for p in pnl.get("items", [])[:5]:
            print(f"  {p}")

    # 扫描
    signals = scan_pairs(
        min_z=args.min_z,
        auto=args.auto,
        top_n=args.top,
        days=args.days,
        ib_direct=args.ib_direct,
    )

    if args.scan_only or not signals:
        if not signals:
            print("\n[INFO] No signals triggered (Z < threshold)")
        return

    print(f"\n[EXEC] Submitting {len(signals)} signals...")
    submitted = execute_signals(signals, auto=args.auto)
    print(f"\n[DONE] Submitted: {len(submitted)} signals")
    for pair, sid in submitted:
        print(f"  {pair}: {sid}")


if __name__ == "__main__":
    main()
