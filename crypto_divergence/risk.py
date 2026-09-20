#!/usr/bin/env python3
"""专业风控闸门：按止损距离定仓、单日亏损熔断、杠杆/敞口上限。"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class RiskConfig:
    risk_per_trade: float = 0.01        # 单笔最大亏损占权益 1%
    max_leverage: float = 3.0           # 杠杆上限 (回测显示3x回撤18%可接受)
    max_daily_loss: float = 0.05        # 单日亏损 -5% 触发熔断, 当日停止开新仓
    max_open_positions: int = 1         # 同时持仓数
    min_nominal_usd: float = 100.0      # 最小下单名义金额


@dataclass
class Position:
    inst: str
    side: str           # 'long' / 'short'
    qty: float
    entry: float
    sl: float
    tp: float
    open_time: object
    open_bar: int
    max_hold: int = 48
    extra: dict = field(default_factory=dict)


class RiskEngine:
    def __init__(self, cfg: RiskConfig = None):
        self.cfg = cfg or RiskConfig()
        self.equity: float = 0.0
        self.day_pnl: float = 0.0
        self._day: Optional[date] = None
        self.open_count: int = 0

    def update_equity(self, equity: float, today: date):
        if self._day != today:
            self._day = today
            self.day_pnl = 0.0
        self.equity = equity

    def record_trade_pnl(self, pnl_usd: float, today: date):
        if self._day != today:
            self._day = today
            self.day_pnl = 0.0
        self.day_pnl += pnl_usd

    def daily_loss_hit(self) -> bool:
        return self.equity > 0 and self.day_pnl <= -self.cfg.max_daily_loss * self.equity

    def size_position(self, entry: float, sl: float) -> tuple[float, float, str]:
        """返回 (qty, nominal_usd, reason)。按固定单笔风险反推，受杠杆上限约束。"""
        if self.daily_loss_hit():
            return 0.0, 0.0, "blocked: daily loss limit"
        if self.open_count >= self.cfg.max_open_positions:
            return 0.0, 0.0, "blocked: max positions"
        stop_dist = abs(entry - sl)
        if stop_dist <= 0 or self.equity <= 0:
            return 0.0, 0.0, "blocked: invalid stop/equity"
        risk_usd = self.equity * self.cfg.risk_per_trade
        # qty 使得 qty*stop_dist = risk_usd
        qty = risk_usd / stop_dist
        nominal = qty * entry
        # 杠杆约束: 名义 <= equity * max_leverage
        max_nominal = self.equity * self.cfg.max_leverage
        if nominal > max_nominal:
            qty = max_nominal / entry
            nominal = max_nominal
        if nominal < self.cfg.min_nominal_usd:
            return 0.0, 0.0, f"blocked: nominal ${nominal:.0f} < min"
        return qty, nominal, "ok"
