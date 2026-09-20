#!/usr/bin/env python3
"""
OKX 模拟盘/实盘执行适配器，接口对齐 engine.PaperBroker。
默认 dry-run(只打印不下单)。真正下单必须显式 --execute 且 --mode sim/live。
风控仓位由 risk.RiskEngine 决定; 杠杆/下单复用 trading/okx_client。

⚠️  在跑通至少 4-8 周模拟盘、确认滑点/资金费率可接受前, 不要用 --execute live。
"""
import os, sys, time, argparse
from datetime import datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests

import bt_divergence as bt
from risk import RiskConfig, RiskEngine
from engine import make_signal

PROXY = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}
BAR_SECONDS = 3600


def fetch_recent(inst, n=150):
    r = requests.get("https://www.okx.com/api/v5/market/candles",
                     params={"instId": inst, "bar": "1H", "limit": str(n)},
                     proxies=PROXY, timeout=15)
    data = r.json()["data"]
    rows = []
    for c in reversed(data):
        rows.append(dict(datetime=datetime.fromtimestamp(int(c[0])/1000),
                         open=float(c[1]), high=float(c[2]), low=float(c[3]),
                         close=float(c[4]), vol=float(c[5])))
    return pd.DataFrame(rows)


class OKXExecutor:
    """对齐 PaperBroker 的最小实盘接口。未 --execute 时只打印。"""
    def __init__(self, inst, mode="sim", execute=False, leverage=3):
        self.inst = inst
        self.mode = mode            # 'sim' (flag=1) / 'live' (flag=2, 0 for read)
        self.execute = execute
        self.leverage = leverage
        self.client = None
        if execute:
            from okx_client import OKXTrader
            flag = "1" if mode == "sim" else "2"
            self.client = OKXTrader(flag=flag)
            try:
                self.client.set_leverage(inst, str(leverage), tdMode="cross")
            except Exception as e:
                print("set_leverage warn:", e)

    def has_position(self):
        if not self.execute:
            return False
        try:
            pos = self.client.get_positions(inst_type="SWAP")
            for p in (pos.get("data") or []):
                if p.get("instId") == self.inst and float(p.get("pos", 0)) != 0:
                    return True
        except Exception as e:
            print("position check warn:", e)
        return False

    def submit(self, side, qty):
        if not self.execute:
            print(f"  [DRY-RUN] 会下单: {side} {qty:.4f} {self.inst}")
            return

        # RiskGate strict 风控检查
        from orders.risk_gate import RiskGate, OrderContext, GateMode
        _risk_gate = RiskGate()
        _risk_ctx = OrderContext(
            symbol=self.inst, action="BUY" if side == "long" else "SELL",
            quantity=float(qty), exchange="OKX",
        )
        _risk_result = _risk_gate.final_check(_risk_ctx, mode=GateMode.STRICT)
        if not _risk_result.allowed:
            print(f"  [RISK BLOCKED] {_risk_result.reason}")
            return

        okx_side = "buy" if side == "long" else "sell"
        # 永续逐仓/全仓; posSide 用于双向持仓
        res = self.client.place_order(self.inst, okx_side, str(qty),
                                      ord_type="market", tdMode="cross")
        print(f"  下单返回: {res}")

    def place_stop_take(self, side, sl, tp):
        """挂止损/止盈条件单 (OKX algo order)。生产应实现; 这里仅打印占位。"""
        print(f"  [风控单] {side} SL={sl:.2f} TP={tp:.2f} "
              f"{'(未自动挂出, 请在交易所或补充algo接口)' if self.execute else ''}")


def run(inst, cfg, order=3, atr_sl=2.0, atr_tp=3.0, max_hold=48,
        mode="sim", execute=False, interval=60):
    risk = RiskEngine(cfg)
    ex = OKXExecutor(inst, mode=mode, execute=execute, leverage=int(cfg.max_leverage))
    print(f"[{datetime.now()}] 启动 {inst} 1H 机器人 mode={mode} execute={execute} "
          f"单笔风险{cfg.risk_per_trade*100:.0f}% 杠杆≤{cfg.max_leverage}x")
    last_confirmed = None
    while True:
        try:
            df = fetch_recent(inst, 150)
            i = len(df) - 1
            sig = make_signal(df, i, order, atr_sl, atr_tp, max_hold)
            if sig and sig["time"] != last_confirmed and not ex.has_position():
                last_confirmed = sig["time"]
                # 用最新价估算权益(execute模式可用 get_balance)
                equity = 8000.0
                risk.update_equity(equity, datetime.now().date())
                qty, nominal, why = risk.size_position(sig["entry"], sig["sl"])
                tag = "✅" if why == "ok" else "⛔"
                print(f"[{datetime.now()}] {tag} {sig['side']} 信号 "
                      f"entry~{sig['entry']:.1f} SL{sig['sl']:.1f} TP{sig['tp']:.1f} "
                      f"qty{qty:.4f} nom${nominal:.0f} ({why})")
                if why == "ok":
                    ex.submit(sig["side"], qty)
                    ex.place_stop_take(sig["side"], sig["sl"], sig["tp"])
        except Exception as e:
            print("loop error:", e)
        time.sleep(interval)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inst", default="BTC-USDT-SWAP")
    ap.add_argument("--mode", choices=["sim", "live"], default="sim")
    ap.add_argument("--execute", action="store_true", help="真正下单(默认dry-run)")
    ap.add_argument("--risk", type=float, default=0.01)
    ap.add_argument("--maxlev", type=float, default=3.0)
    ap.add_argument("--interval", type=int, default=60)
    args = ap.parse_args()
    cfg = RiskConfig(risk_per_trade=args.risk, max_leverage=args.maxlev,
                     max_daily_loss=0.05)
    run(args.inst, cfg, mode=args.mode, execute=args.execute, interval=args.interval)


if __name__ == "__main__":
    main()
