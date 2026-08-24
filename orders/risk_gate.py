#!/usr/bin/env python3
"""下单前强制风控闸门 — 5条可插拔规则，strict/advisory 双模式"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class GateMode(Enum):
    STRICT = "strict"
    ADVISORY = "advisory"


@dataclass
class RiskConfig:
    max_daily_loss_pct: float = 0.05
    max_leverage: float = 3.0
    min_correlation: float = 0.7
    zscore_warn: float = 3.0
    zscore_critical: float = 4.0
    max_open_positions: int = 3


@dataclass
class OrderContext:
    symbol: str
    action: str
    quantity: float
    exchange: str
    equity: float = 0.0
    day_pnl: float = 0.0
    notional: float = 0.0
    zscore: Optional[float] = None
    correlation: Optional[float] = None
    open_positions: int = 0
    strategy: str = ""


@dataclass
class RiskResult:
    allowed: bool
    reason: str = ""
    warnings: List[str] = field(default_factory=list)
    severity: str = "normal"


class RiskRule:
    """单条风控规则基类"""
    def evaluate(self, ctx: OrderContext, cfg: RiskConfig) -> RiskResult:
        raise NotImplementedError


class DailyLossBreaker(RiskRule):
    def evaluate(self, ctx: OrderContext, cfg: RiskConfig) -> RiskResult:
        if ctx.equity <= 0:
            return RiskResult(allowed=True)
        loss_pct = abs(ctx.day_pnl) / ctx.equity
        if ctx.day_pnl < 0 and loss_pct >= cfg.max_daily_loss_pct:
            return RiskResult(
                allowed=False,
                reason=f"daily loss limit: -{loss_pct:.1%} >= {cfg.max_daily_loss_pct:.0%}",
                severity="critical",
            )
        return RiskResult(allowed=True)


class ExposureLimit(RiskRule):
    def evaluate(self, ctx: OrderContext, cfg: RiskConfig) -> RiskResult:
        if ctx.equity <= 0 or ctx.notional <= 0:
            return RiskResult(allowed=True)
        leverage = ctx.notional / ctx.equity
        if leverage > cfg.max_leverage:
            return RiskResult(
                allowed=False,
                reason=f"exposure limit: leverage {leverage:.1f}x > {cfg.max_leverage}x max",
                severity="critical",
            )
        return RiskResult(allowed=True)


class CorrelationBreaker(RiskRule):
    def evaluate(self, ctx: OrderContext, cfg: RiskConfig) -> RiskResult:
        if ctx.correlation is None:
            return RiskResult(allowed=True)
        if ctx.correlation < cfg.min_correlation:
            return RiskResult(
                allowed=False,
                reason=f"correlation breaker: {ctx.correlation:.2f} < {cfg.min_correlation}",
                severity="critical",
            )
        return RiskResult(allowed=True)


class ZScoreGuard(RiskRule):
    def evaluate(self, ctx: OrderContext, cfg: RiskConfig) -> RiskResult:
        if ctx.zscore is None:
            return RiskResult(allowed=True)
        abs_z = abs(ctx.zscore)
        if abs_z >= cfg.zscore_critical:
            return RiskResult(
                allowed=False,
                reason=f"z-score critical: |{ctx.zscore:.1f}| >= {cfg.zscore_critical}",
                severity="critical",
            )
        if abs_z >= cfg.zscore_warn:
            return RiskResult(
                allowed=True,
                warnings=[f"z-score warning: |{ctx.zscore:.1f}| >= {cfg.zscore_warn}"],
                severity="warning",
            )
        return RiskResult(allowed=True)


class MaxPositionsGuard(RiskRule):
    def evaluate(self, ctx: OrderContext, cfg: RiskConfig) -> RiskResult:
        if ctx.open_positions >= cfg.max_open_positions:
            return RiskResult(
                allowed=False,
                reason=f"max positions: {ctx.open_positions} open >= {cfg.max_open_positions} limit",
                severity="critical",
            )
        return RiskResult(allowed=True)


class RiskGate:
    """风控闸门 — 所有下单必须过此门"""

    def __init__(self, cfg: RiskConfig = None):
        self.cfg = cfg or RiskConfig()
        self.rules: List[RiskRule] = [
            DailyLossBreaker(),
            ExposureLimit(),
            CorrelationBreaker(),
            ZScoreGuard(),
            MaxPositionsGuard(),
        ]

    def pre_check(self, ctx: OrderContext, mode: GateMode = GateMode.STRICT) -> RiskResult:
        return self._evaluate(ctx, mode)

    def final_check(self, ctx: OrderContext, mode: GateMode = GateMode.STRICT) -> RiskResult:
        return self._evaluate(ctx, mode)

    def _evaluate(self, ctx: OrderContext, mode: GateMode) -> RiskResult:
        all_warnings = []
        for rule in self.rules:
            result = rule.evaluate(ctx, self.cfg)
            if not result.allowed:
                if mode == GateMode.STRICT:
                    return result
                else:
                    all_warnings.append(f"[ADVISORY] {result.reason}")
            all_warnings.extend(result.warnings)

        if all_warnings:
            return RiskResult(allowed=True, warnings=all_warnings,
                            severity="warning" if mode == GateMode.STRICT else "normal")
        return RiskResult(allowed=True)