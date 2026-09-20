#!/usr/bin/env python3
"""纸面成交引擎 + 机器人主循环。历史回放用于验证自交易闭环, 实盘可替换 Broker。"""
import os, time, argparse
from datetime import datetime
import numpy as np, pandas as pd

import bt_divergence as bt
from risk import RiskConfig, RiskEngine, Position

FEE_RATE = 0.0005   # taker 单边 0.05%
SLIP = 0.0003       # 滑点 0.03% 单边
COST_RT = 2 * (FEE_RATE + SLIP)


class PaperBroker:
    """单品种、单仓纸面经纪商。按K线 high/low 触发止损止盈。"""
    def __init__(self, starting_equity=8000.0):
        self.equity = starting_equity
        self.start_equity = starting_equity
        self.pos: Position | None = None
        self.trades: list[dict] = []
        self.curve: list[tuple] = []

    def has_position(self):
        return self.pos is not None

    def open(self, pos: Position, bar_time, bar_idx):
        # 成交价含滑点
        slip = pos.entry * SLIP
        fill = pos.entry + slip if pos.side == "long" else pos.entry - slip
        fee = fill * pos.qty * FEE_RATE
        self.pos = Position(pos.inst, pos.side, pos.qty, fill, pos.sl, pos.tp,
                            bar_time, bar_idx, pos.max_hold)
        self.equity -= fee
        self._mark(bar_time, fill)

    def _close(self, price, time, reason):
        p = self.pos
        slip = price * SLIP
        fill = price - slip if p.side == "long" else price + slip
        fee = fill * p.qty * FEE_RATE
        gross = (fill - p.entry) * p.qty if p.side == "long" else (p.entry - fill) * p.qty
        pnl = gross - fee
        self.equity += pnl
        self.trades.append(dict(inst=p.inst, side=p.side, entry=p.entry, exit=fill,
                                qty=p.qty, pnl=round(pnl,2), ret=pnl/self.start_equity*100,
                                reason=reason, open_t=p.open_time, close_t=time,
                                bars=0))
        self.pos = None
        self._mark(time, fill)
        return pnl

    def on_bar(self, high, low, close, time, bar_idx):
        if not self.pos:
            self._mark(time, close)
            return None
        p = self.pos
        exit_px, reason = None, None
        if p.side == "long":
            if low <= p.sl: exit_px, reason = p.sl, "sl"
            elif high >= p.tp: exit_px, reason = p.tp, "tp"
        else:
            if high >= p.sl: exit_px, reason = p.sl, "sl"
            elif low <= p.tp: exit_px, reason = p.tp, "tp"
        if exit_px is None and bar_idx - p.open_bar >= p.max_hold:
            exit_px, reason = close, "time"
        if exit_px is not None:
            return self._close(exit_px, time, reason)
        self._mark(time, close)
        return None

    def _mark(self, time, price):
        eq = self.equity
        if self.pos:
            p = self.pos
            upnl = (price - p.entry)*p.qty if p.side=="long" else (p.entry-price)*p.qty
            eq += upnl
        self.curve.append((time, eq))


def make_signal(df, i, order=3, atr_sl=2.0, atr_tp=3.0, max_hold=48):
    """在已收盘的第 i 根K线(含)之前检测背离, 返回刚确认的信号或None。
    关键: confirm 索引必须 == i 才视为'本根bar确认、下根bar开盘可执行', 杜绝未来函数。"""
    window = df.iloc[:i+1]
    if len(window) < 60:
        return None
    sigs = bt.divergences(window, order=order)
    if not sigs:
        return None
    s = sigs[-1]
    if s["confirm"] != i:      # 只在确认那一根触发
        return None
    window = window.copy()
    window["atr"] = bt.atr(window, 14)
    entry = float(window["close"].iloc[i])
    a = float(window["atr"].iloc[i])
    if np.isnan(a):
        return None
    if s["side"] == "long":
        sl, tp = entry - atr_sl*a, entry + atr_tp*a
    else:
        sl, tp = entry + atr_sl*a, entry - atr_tp*a
    return dict(side=s["side"], entry=entry, sl=sl, tp=tp, atr=a,
                time=window["datetime"].iloc[i], max_hold=max_hold)


def replay(df, inst="BTC-USDT-SWAP", cfg: RiskConfig = None, order=3,
           atr_sl=2.0, atr_tp=3.0, max_hold=48, verbose=False):
    """逐根回放, 信号在第 i 根确认 -> 第 i+1 根开盘执行。"""
    risk = RiskEngine(cfg or RiskConfig())
    broker = PaperBroker()
    df = df.reset_index(drop=True)
    fills = 0
    for i in range(len(df)):
        row = df.iloc[i]
        t = row["datetime"]
        # 先处理当前bar持仓的退出(用high/low)
        broker.on_bar(row["high"], row["low"], row["close"], t, i)
        risk.update_equity(broker.equity, pd.Timestamp(t).date())
        risk.open_count = 1 if broker.has_position() else 0
        # 在已收盘bar上找信号, 下一根开盘执行
        if not broker.has_position() and i + 1 < len(df):
            sig = make_signal(df, i, order, atr_sl, atr_tp, max_hold)
            if sig:
                qty, nominal, why = risk.size_position(sig["entry"], sig["sl"])
                if verbose or why != "ok":
                    tag = "✅" if why == "ok" else "⛔"
                    print(f"[{t}] {tag} {sig['side']} {inst} entry{sig['entry']:.1f} "
                          f"SL{sig['sl']:.1f} TP{sig['tp']:.1f} qty{qty:.4f} "
                          f"nom${nominal:.0f} ({why})")
                if why == "ok":
                    nxt = df.iloc[i+1]
                    pos = Position(inst, sig["side"], qty, float(nxt["open"]),
                                   sig["sl"], sig["tp"], nxt["datetime"], i+1, max_hold)
                    broker.open(pos, nxt["datetime"], i+1)
                    fills += 1
    return broker, fills


def summarize(broker):
    tr = pd.DataFrame(broker.trades)
    curve = np.array([e for _, e in broker.curve])
    if len(curve) == 0:
        return "无数据"
    peak = np.maximum.accumulate(curve)
    dd = (curve - peak) / peak
    start = broker.start_equity
    end = broker.equity
    if tr.empty:
        return (f"期末${end:,.0f} 收益{(end/start-1)*100:+.0f}% 最大回撤{dd.min()*100:.0f}% 无成交")
    wins = tr[tr.pnl > 0]
    losses = tr[tr.pnl < 0]
    pf = wins.pnl.sum() / abs(losses.pnl.sum()) if len(losses) else float("inf")
    tr["day"] = pd.to_datetime(tr.close_t).dt.date
    daily = tr.groupby("day").pnl.sum()
    return (f"成交{len(tr)}笔 胜率{(tr.pnl>0).mean()*100:.0f}% PF{pf:.2f} | "
            f"权益${start:,.0f}→${end:,.0f} ({(end/start-1)*100:+.0f}%) "
            f"最大回撤{dd.min()*100:.0f}% | "
            f"日均${daily.mean():+,.0f} 盈利日{(daily>0).mean()*100:.0f}% "
            f"最好日${daily.max():+,.0f} 最差日${daily.min():,.0f} | "
            f"止损率{(tr.reason=='sl').mean()*100:.0f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inst", default="BTC-USDT-SWAP")
    ap.add_argument("--risk", type=float, default=0.01, help="单笔风险占比")
    ap.add_argument("--maxlev", type=float, default=3.0)
    ap.add_argument("--maxdd", type=float, default=0.05, help="单日亏损熔断")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    df = bt.load(args.inst, "1H")
    print(f"历史回放 {args.inst} 1H {df.datetime.min()}~{df.datetime.max()} 本金$8000")
    print(f"风控: 单笔风险{args.risk*100:.0f}% 最大杠杆{args.maxlev}x 单日熔断-{args.maxdd*100:.0f}%\n")
    cfg = RiskConfig(risk_per_trade=args.risk, max_leverage=args.maxlev,
                     max_daily_loss=args.maxdd)
    broker, fills = replay(df, args.inst, cfg, verbose=args.verbose)
    print("\n" + summarize(broker))
    print(f"开仓次数: {fills}")


if __name__ == "__main__":
    main()
