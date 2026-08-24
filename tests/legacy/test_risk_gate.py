#!/usr/bin/env python3
"""RiskGate 单元测试 — 5条风控规则 + strict/advisory 双模式"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from orders.risk_gate import RiskGate, RiskConfig, OrderContext, RiskResult, GateMode


def test_daily_loss_breaker_blocks():
    """日亏损超过5%时熔断"""
    gate = RiskGate(RiskConfig(max_daily_loss_pct=0.05))
    ctx = OrderContext(symbol="GC", action="BUY", quantity=1,
                       exchange="IB", equity=100000, day_pnl=-6000)
    result = gate.pre_check(ctx)
    assert not result.allowed
    assert "daily loss" in result.reason.lower()


def test_daily_loss_breaker_allows_normal():
    """日亏损未达阈值时放行"""
    gate = RiskGate(RiskConfig(max_daily_loss_pct=0.05))
    ctx = OrderContext(symbol="GC", action="BUY", quantity=1,
                       exchange="IB", equity=100000, day_pnl=-2000)
    result = gate.pre_check(ctx)
    assert result.allowed


def test_exposure_limit_blocks():
    """杠杆超过3x时拒绝"""
    gate = RiskGate(RiskConfig(max_leverage=3.0))
    ctx = OrderContext(symbol="GC", action="BUY", quantity=10,
                       exchange="IB", equity=100000, notional=400000)
    result = gate.pre_check(ctx)
    assert not result.allowed
    lower = result.reason.lower()
    assert "leverage" in lower or "exposure" in lower


def test_correlation_breaker_blocks():
    """相关性低于0.7时熔断"""
    gate = RiskGate(RiskConfig(min_correlation=0.7))
    ctx = OrderContext(symbol="FU-LU", action="BUY", quantity=1,
                       exchange="IB", correlation=0.55)
    result = gate.pre_check(ctx)
    assert not result.allowed
    assert "correlation" in result.reason.lower()


def test_correlation_breaker_allows_high_corr():
    """高相关性时放行"""
    gate = RiskGate(RiskConfig(min_correlation=0.7))
    ctx = OrderContext(symbol="FU-LU", action="BUY", quantity=1,
                       exchange="IB", correlation=0.85)
    result = gate.pre_check(ctx)
    assert result.allowed


def test_zscore_guard_critical():
    """Z-Score超过±4.0时熔断"""
    gate = RiskGate(RiskConfig(zscore_warn=3.0, zscore_critical=4.0))
    ctx = OrderContext(symbol="FU-LU", action="BUY", quantity=1,
                       exchange="IB", zscore=4.5)
    result = gate.pre_check(ctx)
    assert not result.allowed
    assert "z-score" in result.reason.lower()


def test_zscore_guard_warning():
    """Z-Score超过±3.0但未到±4.0时告警但放行"""
    gate = RiskGate(RiskConfig(zscore_warn=3.0, zscore_critical=4.0))
    ctx = OrderContext(symbol="FU-LU", action="BUY", quantity=1,
                       exchange="IB", zscore=3.2)
    result = gate.pre_check(ctx)
    assert result.allowed
    assert len(result.warnings) > 0


def test_advisory_mode_always_allows():
    """advisory 模式永远放行，只记录告警"""
    gate = RiskGate(RiskConfig(max_daily_loss_pct=0.05))
    ctx = OrderContext(symbol="GC", action="BUY", quantity=1,
                       exchange="IB", equity=100000, day_pnl=-6000)
    result = gate.final_check(ctx, mode=GateMode.ADVISORY)
    assert result.allowed
    assert len(result.warnings) > 0


def test_all_rules_pass():
    """所有规则通过时正常放行"""
    gate = RiskGate(RiskConfig(max_daily_loss_pct=0.05, max_leverage=3.0,
                               min_correlation=0.7, zscore_warn=3.0, zscore_critical=4.0))
    ctx = OrderContext(symbol="GC", action="BUY", quantity=1,
                       exchange="IB", equity=100000, day_pnl=-1000,
                       notional=50000, correlation=0.9, zscore=1.5)
    result = gate.pre_check(ctx)
    assert result.allowed
    assert len(result.warnings) == 0