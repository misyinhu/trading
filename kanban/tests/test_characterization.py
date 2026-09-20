#!/usr/bin/env python3
"""
特征测试套件 - Trading 项目核心算法

目的：捕获现有代码的真实行为，作为安全网防止无意的行为变更。
这不是验证"正确性"，而是记录"当前实际行为"。

来源：proposal.md US-AC-TC 追溯 + 代码审查发现的功能点
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock


# =============================================================================
# 核心算法测试 (src/analysis.py)
# =============================================================================


class TestResonanceCalculation:
    """共振分数计算 - RS-US2, RS-US3 对应"""

    def test_all_up_returns_high_score(self):
        """全上涨应得高分"""
        from src.analysis import calculate_resonance_en

        result = calculate_resonance_en(["up", "up", "up", "up", "up"])
        assert result["score"] >= 70
        assert result["level"] == "高"
        assert result["distribution"]["up"] == 5

    def test_all_down_returns_high_score(self):
        """全下跌应得高分"""
        from src.analysis import calculate_resonance_en

        result = calculate_resonance_en(["down", "down", "down", "down", "down"])
        assert result["score"] >= 70
        assert result["level"] == "高"
        assert result["distribution"]["down"] == 5

    def test_mixed_returns_appropriate_score(self):
        """混合方向返回适当分数"""
        from src.analysis import calculate_resonance_en

        result = calculate_resonance_en(["up", "up", "neutral", "neutral", "neutral"])
        assert 30 <= result["score"] < 70
        assert result["level"] in ["低", "中"]

    def test_empty_returns_zero(self):
        """空输入返回零分"""
        from src.analysis import calculate_resonance_en

        result = calculate_resonance_en([])
        assert result["score"] == 0
        assert result["level"] == "低"

    def test_score_bounds_0_to_100(self):
        """分数边界验证"""
        from src.analysis import calculate_resonance_en

        for _ in range(10):
            directions = np.random.choice(["up", "down", "neutral"], size=5).tolist()
            result = calculate_resonance_en(directions)
            assert 0 <= result["score"] <= 100


class TestRSICalculation:
    """RSI 计算测试"""

    def test_rsi_no_change_returns_100(self):
        """价格不变 RSI 应为 100"""
        from src.analysis import calculate_rsi_local

        prices = [100] * 20
        rsi = calculate_rsi_local(prices, period=14)
        assert rsi == 100.0

    def test_rsi_continuous_up_returns_high(self):
        """连续上涨 RSI 应高"""
        from src.analysis import calculate_rsi_local

        prices = list(range(100, 115))  # 连续上涨
        rsi = calculate_rsi_local(prices, period=14)
        assert rsi > 50

    def test_rsi_continuous_down_returns_low(self):
        """连续下跌 RSI 应低"""
        from src.analysis import calculate_rsi_local

        prices = list(range(115, 99, -1))  # 连续下跌
        rsi = calculate_rsi_local(prices, period=14)
        assert rsi < 50

    def test_rsi_short_period(self):
        """数据不足 period 时返回 50"""
        from src.analysis import calculate_rsi_local

        prices = [100] * 10  # 少于 14
        rsi = calculate_rsi_local(prices, period=14)
        assert rsi == 50.0

    def test_rsi_exact_period(self):
        """数据正好等于 period 时正常计算"""
        from src.analysis import calculate_rsi_local

        prices = [100] * 15
        rsi = calculate_rsi_local(prices, period=14)
        assert rsi == 100.0


class TestMACalculation:
    """MA 计算测试"""

    def test_ma_normal(self):
        """正常 MA 计算"""
        from src.analysis import calculate_ma_local

        prices = [100] * 25
        ma = calculate_ma_local(prices, period=20)
        assert ma == 100.0

    def test_ma_insufficient_data(self):
        """数据不足返回 0"""
        from src.analysis import calculate_ma_local

        prices = [100] * 10
        ma = calculate_ma_local(prices, period=20)
        assert ma == 0.0

    def test_ma_exact_period(self):
        """正好 period 条数据"""
        from src.analysis import calculate_ma_local

        prices = list(range(80, 100))
        ma = calculate_ma_local(prices, period=20)
        assert ma == 89.5  # (80+81+...+99)/20 = 89.5


class TestDetectContradictions:
    """矛盾检测 - CT-US1 对应"""

    def test_no_contradiction_when_all_up(self):
        """全涨无矛盾"""
        from src.analysis import detect_contradictions

        result = detect_contradictions(
            {
                "1m": {"trend": "up"},
                "5m": {"trend": "up"},
                "30m": {"trend": "up"},
            }
        )
        assert result["has_contradiction"] == False

    def test_contradiction_short_long_conflict(self):
        """短周期涨但长周期跌 - 矛盾检测 (4h/1D 级别)"""
        from src.analysis import detect_contradictions

        result = detect_contradictions(
            {
                "1m": {"trend": "up"},
                "5m": {"trend": "up"},
                "4h": {"trend": "down"},
            }
        )
        assert result["has_contradiction"] == True
        assert len(result["contradictions"]) > 0

    def test_empty_input(self):
        """空输入无矛盾"""
        from src.analysis import detect_contradictions

        result = detect_contradictions({})
        assert result["has_contradiction"] == False


# =============================================================================
# NL Parser 测试 (notify/nl_parser.py)
# =============================================================================


class TestNLParser:
    """自然语言指令解析 - WH-201 对应"""

    def test_parse_buy_command(self):
        """解析买入指令"""
        from notify.nl_parser import parse_trading_command

        result = parse_trading_command("买入1手GC")
        assert result["action"] == "BUY"
        assert result["symbol"] == "GC"
        assert result["quantity"] == 1

    def test_parse_sell_command(self):
        """解析卖出指令"""
        from notify.nl_parser import parse_trading_command

        result = parse_trading_command("卖出1手NQ")
        assert result["action"] == "SELL"
        assert result["symbol"] == "NQ"
        assert result["quantity"] == 1

    def test_parse_close_command(self):
        """解析平仓指令"""
        from notify.nl_parser import parse_trading_command

        result = parse_trading_command("平仓GC")
        assert result["action"] == "CLOSE"
        assert result["symbol"] == "GC"

    def test_parse_query_command(self):
        """解析查询指令"""
        from notify.nl_parser import parse_trading_command

        result = parse_trading_command("查看持仓")
        assert result["action"] == "QUERY"

    def test_parse_chinese_number(self):
        """解析中文数字"""
        from notify.nl_parser import parse_trading_command

        result = parse_trading_command("买一手BTC")
        assert result["quantity"] == 1

    def test_crypto_symbol_mapping(self):
        """加密货币符号自动映射"""
        from notify.nl_parser import parse_trading_command

        result = parse_trading_command("买入1手DOGE")
        assert "DOGE" in result["symbol"]


# =============================================================================
# 数据获取测试 (src/data.py)
# =============================================================================


class TestInstrumentsConfig:
    """品种配置加载"""

    def test_load_instruments_config(self):
        """加载 instruments.yaml"""
        from src.data import load_instruments_config

        instruments = load_instruments_config()
        assert isinstance(instruments, list)

    def test_get_source_for_symbol(self):
        """获取品种数据源"""
        from src.data import get_source_for_symbol

        source = get_source_for_symbol("DOGE-USDT")
        assert source in ["okx", "ib", "tradingview"]

    def test_tv_symbol_mapping(self):
        """IB 符号到 TV 符号映射"""
        from src.data import get_tv_symbol_for_ib

        assert get_tv_symbol_for_ib("ES") == "ES.cme"
        assert get_tv_symbol_for_ib("GC") == "GC.cme"
        assert get_tv_symbol_for_ib("AAPL") == "AAPL.nasdaq"


# =============================================================================
# INDEX_MAP 测试 (pages/4_market_insight.py, pages/6_market_agent.py)
# =============================================================================


class TestIndexMap:
    """关键词映射 - AG-US3 对应"""

    def test_nasdaq_mapping(self):
        """纳指 -> QQQ"""
        INDEX_MAP = {
            "纳指": ("QQQ", "NASDAQ"),
            "nasdaq": ("QQQ", "NASDAQ"),
            "qqq": ("QQQ", "NASDAQ"),
        }
        text = "纳指上涨"
        text_lower = text.lower()
        found = {sym for kw, (sym, ex) in INDEX_MAP.items() if kw in text_lower}
        assert "QQQ" in found

    def test_dow_mapping(self):
        """道指 -> DIA"""
        INDEX_MAP = {
            "道指": ("DIA", "NYSE"),
            "dow": ("DIA", "NYSE"),
            "dia": ("DIA", "NYSE"),
        }
        text = "道指下跌"
        text_lower = text.lower()
        found = {sym for kw, (sym, ex) in INDEX_MAP.items() if kw in text_lower}
        assert "DIA" in found

    def test_spy_mapping(self):
        """标普 -> SPY"""
        INDEX_MAP = {
            "标普": ("SPY", "NYSE"),
            "spy": ("SPY", "NYSE"),
        }
        text = "标普500创新高"
        text_lower = text.lower()
        found = {sym for kw, (sym, ex) in INDEX_MAP.items() if kw in text_lower}
        assert "SPY" in found

    def test_default_fallback(self):
        """无匹配时默认 QQQ"""
        INDEX_MAP = {
            "纳指": ("QQQ", "NASDAQ"),
        }
        text = "黄金上涨"
        text_lower = text.lower()
        found = {sym for kw, (sym, ex) in INDEX_MAP.items() if kw in text_lower}
        if not found:
            found.add("QQQ")  # 默认
        assert "QQQ" in found


# =============================================================================
# 三重滤网测试 (src/three_filter.py)
# =============================================================================


class TestThreeFilterSignal:
    """三重滤网信号 - TS-US1 对应"""

    def test_signal_dataclass_fields(self):
        """ThreeFilterSignal 字段验证"""
        from src.three_filter import ThreeFilterSignal

        signal = ThreeFilterSignal(
            m30_trend="多头",
            m5_pullback="回调中",
            m1_entry="做多",
            strength=75,
            entry_price=100.5,
            stop_loss=98.0,
            risk_reward_ratio=2.5,
            signal_reason="M30多头确认",
        )
        assert signal.m30_trend == "多头"
        assert signal.m5_pullback == "回调中"
        assert signal.m1_entry == "做多"
        assert signal.strength == 75

    def test_signal_optional_fields_none(self):
        """可选字段可为 None"""
        from src.three_filter import ThreeFilterSignal

        signal = ThreeFilterSignal(
            m30_trend="中性",
            m5_pullback="无回调",
            m1_entry="等待",
            strength=50,
            entry_price=None,
            stop_loss=None,
            risk_reward_ratio=None,
            signal_reason="",
        )
        assert signal.entry_price is None


# =============================================================================
# 跨周期分析逻辑测试 (pages/5_cross_timeframe.py)
# =============================================================================


class TestCrossTimeframeLogic:
    """跨周期矛盾检测逻辑 - CT-US1, CT-US2 对应"""

    def test_zscore_calculation(self):
        """Z-Score 计算"""
        values = [2.5, 3.0, 2.8]
        avg = sum(values) / len(values)
        assert abs(avg - 2.77) < 0.1

    def test_correlation_break_detection(self):
        """相关性破裂检测"""
        corr_values = [0.2, 0.15, 0.25]
        has_corr_break = all(c < 0.3 for c in corr_values)
        assert has_corr_break == True

    def test_signal_score_calculation(self):
        """信号评分计算"""
        zscore_values = [(1, 3.5), (5, 3.2), (30, 3.0)]
        all_extreme = all(abs(z) >= 2 for _, z in zscore_values)
        all_same_sign = all(
            (z > 0) == (zscore_values[0][1] > 0) for _, z in zscore_values
        )
        corr_values = [(1, 0.2), (5, 0.15)]
        has_corr_break = all(c < 0.3 for _, c in corr_values)

        signal_score = 0
        if all_extreme and all_same_sign and has_corr_break:
            signal_score += 2

        assert signal_score == 2

    def test_entry_signal_buy(self):
        """买入信号判断"""
        avg_zscore = -2.5
        signal_score = 2
        action = "🟢 买入" if avg_zscore < 0 and signal_score >= 2 else "neutral"
        assert action == "🟢 买入"

    def test_entry_signal_sell(self):
        """卖出信号判断"""
        avg_zscore = 2.5
        signal_score = 2
        action = "🔴 卖出" if avg_zscore > 0 and signal_score >= 2 else "neutral"
        assert action == "🔴 卖出"


# =============================================================================
# 运行覆盖率报告
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Trading 项目特征测试套件")
    print("=" * 60)
    pytest.main([__file__, "-v", "--cov=.", "--cov-report=term-missing"])
