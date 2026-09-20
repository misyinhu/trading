#!/usr/bin/env python3
"""
加密永续 经典价格-MACD 背离策略 —— 可信口径回测
- 极值需 order 根K线确认，入场延迟到确认根收盘(修复未来函数)
- ATR 止损/止盈/最大持仓
- 成本: taker 0.05%/边 + 滑点, 往返 cost_rt
- 输出交易统计 + 账户权益曲线 + 8000美金@杠杆的实际收益/回撤
"""
import os, argparse
import numpy as np, pandas as pd

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def load(inst, bar):
    df = pd.read_csv(os.path.join(DATA, f"{inst.replace('-','_')}_{bar}.csv"),
                     parse_dates=["datetime"])
    return df.sort_values("datetime").reset_index(drop=True)


def atr(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift()
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def find_peaks(vals, order=3):
    hi, lo = [], []
    n = len(vals)
    for i in range(n):
        a = min(i, order); b = min(n - 1 - i, order)
        if a + b < 1: continue
        w = vals[i - a:i + b + 1]
        if vals[i] == w.max(): hi.append(i)
        if vals[i] == w.min(): lo.append(i)
    return hi, lo


def macd(close, fast=12, slow=26, sig=9):
    ef = close.ewm(span=fast, adjust=False).mean()
    es = close.ewm(span=slow, adjust=False).mean()
    line = ef - es
    return line


def divergences(df, order=5, window=60):
    """返回信号列表，每个含确认K线索引 confirm_idx（即入场K线）。"""
    highs, lows = find_peaks(df["high"].values, order)
    m = macd(df["close"]).values
    px_hi = df["high"].values; px_lo = df["low"].values
    sigs = []
    # 顶背离: 价格 higher high, MACD lower high -> short
    for k in range(1, len(highs)):
        i1, i2 = highs[k-1], highs[k]
        if i2 - i1 > window: continue
        if px_hi[i2] > px_hi[i1] and m[i2] < m[i1]:
            sigs.append(dict(side="short", p1=i1, p2=i2, confirm=i2 + order))
    for k in range(1, len(lows)):
        i1, i2 = lows[k-1], lows[k]
        if i2 - i1 > window: continue
        if px_lo[i2] < px_lo[i1] and m[i2] > m[i1]:
            sigs.append(dict(side="long", p1=i1, p2=i2, confirm=i2 + order))
    sigs = [s for s in sigs if s["confirm"] < len(df)]
    # 同一确认K线只保留一个信号
    seen = set(); out = []
    for s in sorted(sigs, key=lambda x: x["confirm"]):
        if s["confirm"] in seen: continue
        seen.add(s["confirm"]); out.append(s)
    return out


def backtest(df, order=5, atr_n=14, atr_sl=1.5, atr_tp=3.0, max_hold=48,
             cost_rt=0.0013):
    df = df.copy()
    df["atr"] = atr(df, atr_n)
    sigs = divergences(df, order=order)
    closes = df["close"].values; highs = df["high"].values; lows = df["low"].values
    atrs = df["atr"].values; times = df["datetime"].values
    trades = []
    in_pos_until = -1
    for s in sigs:
        ei = s["confirm"]
        if ei <= in_pos_until:  # 持仓期间不重复开
            continue
        if np.isnan(atrs[ei]): continue
        entry = closes[ei]; a = atrs[ei]
        if s["side"] == "long":
            sl = entry - atr_sl * a; tp = entry + atr_tp * a
        else:
            sl = entry + atr_sl * a; tp = entry - atr_tp * a
        exit_px, exit_i, reason = None, None, None
        for j in range(ei + 1, min(ei + 1 + max_hold, len(df))):
            if s["side"] == "long":
                if lows[j] <= sl: exit_px, exit_i, reason = sl, j, "sl"; break
                if highs[j] >= tp: exit_px, exit_i, reason = tp, j, "tp"; break
            else:
                if highs[j] >= sl: exit_px, exit_i, reason = sl, j, "sl"; break
                if lows[j] <= tp: exit_px, exit_i, reason = tp, j, "tp"; break
        if exit_px is None:
            exit_i = min(ei + max_hold, len(df) - 1)
            exit_px = closes[exit_i]; reason = "time"
        gross = (exit_px - entry) if s["side"] == "long" else (entry - exit_px)
        r = gross / entry - cost_rt  # 扣除往返成本
        trades.append(dict(side=s["side"], entry_t=times[ei], exit_t=times[exit_i],
                           entry=entry, exit=exit_px, ret=r*100, reason=reason,
                           bars=exit_i - ei))
        in_pos_until = exit_i
    return pd.DataFrame(trades)


def perf(r, capital=8000, lev=5, risk_per_trade=0.0):
    if r.empty: return {}
    # 按固定比例复利: 每次用权益的 fraction 建仓(名义 = equity*lev)
    eq = capital; curve = []
    for x in r["ret"]:
        # 收益 x 是标的价格变动率(扣成本)，乘以杠杆就是仓位收益率
        # 全仓杠杆(名义=equity*lev)时，权益变动 = x * lev
        eq *= (1 + x/100 * lev / 100)  # x单位%, lev倍
        curve.append(eq)
    curve = np.array(curve)
    peak = np.maximum.accumulate(curve)
    dd = (curve - peak) / peak
    wins = r["ret"] > 0
    return dict(
        n=len(r), win=wins.mean()*100,
        total_ret=(curve[-1]/capital-1)*100,
        max_dd=dd.min()*100,
        profit_factor=r.loc[r.ret>0,"ret"].sum()/abs(r.loc[r.ret<0,"ret"].sum()) if (r.ret<0).any() else float("inf"),
        avg=r["ret"].mean(), avg_win=r.loc[wins,"ret"].mean(), avg_loss=r.loc[~wins,"ret"].mean(),
        end_eq=curve[-1], best=r["ret"].max(), worst=r["ret"].min(),
        sl_rate=(r["reason"]=="sl").mean()*100,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inst", default="BTC-USDT-SWAP")
    ap.add_argument("--order", type=int, default=5)
    ap.add_argument("--lev", type=float, default=5)
    ap.add_argument("--split", action="store_true", help="分两段检验稳定性")
    args = ap.parse_args()
    df = load(args.inst, "1H")
    print(f"{args.inst} 1H  {df.datetime.min()} ~ {df.datetime.max()}  ({len(df)} bars)  杠杆{args.lev}x")
    for label, sub in [("FULL", df)] + ([("H1", df.iloc[:len(df)//2]), ("H2", df.iloc[len(df)//2:])] if args.split else []):
        r = backtest(sub, order=args.order)
        p = perf(r, lev=args.lev)
        if not p:
            print(f"  {label}: 无交易"); continue
        print(f"  [{label}] {p['n']}笔 胜率{p['win']:.0f}% 标的均笔{p['avg']:+.2f}% "
              f"账户总收益{p['total_ret']:+.0f}% 末值${p['end_eq']:.0f} 最大回撤{p['max_dd']:.0f}% "
              f"PF{p['profit_factor']:.2f} 止损率{p['sl_rate']:.0f}%")
    # 逐日盈利分布(评估日赚1000可行性)
    r = backtest(df, order=args.order)
    if not r.empty:
        r["entry_day"] = pd.to_datetime(r["entry_t"]).dt.date
        daily = r.groupby("entry_day")["ret"].apply(lambda x: (np.prod(1+x/100)-1)*100*args.lev)
        print(f"  按交易日: 共{daily.shape[0]}个有交易的日子, 均日{daily.mean():+.1f}% 账户, "
              f"盈利日占比{(daily>0).mean()*100:.0f}%, 最佳日{daily.max():+.0f}%, 最差日{daily.min():+.0f}%")
        print(f"  日赚$1000(=12.5%)所需日账户收益≥12.5%的天数占比: {(daily>=12.5).mean()*100:.1f}%")

if __name__ == "__main__":
    main()
