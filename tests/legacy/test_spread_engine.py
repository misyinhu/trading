#!/usr/bin/env python3
"""
核心价差计算引擎测试
"""

import pytest
import pandas as pd
import numpy as np
import sys
import os
from pathlib import Path

# 添加路径以便导入模块
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT / "z120_monitor" / "core"))

from spread_engine import (
    SpreadEngine,
    HistoricalDeviationDetector,
    UniversalSpreadStrategy,
)


class TestSpreadEngine:
    """测试 SpreadEngine 类"""

    @pytest.fixture
    def sample_assets(self):
        return {
            "asset1": {"symbol": "MNQ", "multiplier": 2.0, "ratio1": 1},
            "asset2": {"symbol": "MYM", "multiplier": 0.5, "ratio2": 2},
        }

    @pytest.fixture
    def spread_engine(self, sample_assets):
        return SpreadEngine(sample_assets["asset1"], sample_assets["asset2"])

    # 测试用例1: 正常价差价值计算
    @pytest.mark.parametrize(
        "price1,price2,expected",
        [
            (100.0, 50.0, 150.0),  # 100*2.0*1 - 50*0.5*2 = 200 - 50 = 150
            (150.0, 75.0, 225.0),  # 150*2.0*1 - 75*0.5*2 = 300 - 75 = 225
            (200.0, 100.0, 300.0),  # 200*2.0*1 - 100*0.5*2 = 400 - 100 = 300
        ],
    )
    def test_calculate_spread_value_normal(
        self, spread_engine, price1, price2, expected
    ):
        result = spread_engine.calculate_spread_value(price1, price2)
        assert abs(result - expected) < 0.001

    # 测试用例2: 边界条件
    @pytest.mark.parametrize(
        "price1,price2",
        [
            (0.0, 0.0),
            (1000000.0, 1000000.0),
            (-100.0, 50.0),
        ],
    )
    def test_calculate_spread_value_boundary(self, spread_engine, price1, price2):
        result = spread_engine.calculate_spread_value(price1, price2)
        assert isinstance(result, float)
        assert not np.isnan(result)
        assert not np.isinf(result)

    # 测试用例3: 异常输入
    @pytest.mark.parametrize(
        "price1,price2",
        [
            (None, 50.0),
            (100.0, None),
            ("invalid", 50.0),
            (100.0, "invalid"),
        ],
    )
    def test_calculate_spread_value_invalid(self, spread_engine, price1, price2):
        with pytest.raises((TypeError, ValueError)):
            spread_engine.calculate_spread_value(price1, price2)

    # 测试用例4: 价差比率计算
    @pytest.mark.parametrize(
        "price1,price2,expected",
        [
            (100.0, 50.0, 4.0),  # (100*2.0*1) / (50*0.5*2) = 200/50 = 4.0
            (150.0, 75.0, 4.0),  # (150*2.0*1) / (75*0.5*2) = 300/75 = 4.0
        ],
    )
    def test_calculate_spread_ratio_normal(
        self, spread_engine, price1, price2, expected
    ):
        result = spread_engine.calculate_spread_ratio(price1, price2)
        assert abs(result - expected) < 0.001

    # 测试用例5: 除零处理
    def test_calculate_spread_ratio_zero_division(self, spread_engine):
        result = spread_engine.calculate_spread_ratio(100.0, 0.0)
        assert result == 0.0


class TestHistoricalDeviationDetector:
    """测试 HistoricalDeviationDetector 类"""

    @pytest.fixture
    def detector(self):
        return HistoricalDeviationDetector(threshold=1000, lookback_days=7)

    @pytest.fixture
    def sample_spread_ratios(self):
        # 创建7天的价差比率数据
        data = [1.0, 1.1, 0.9, 1.2, 0.8, 1.15, 0.85]  # 模拟历史数据
        return pd.Series(data)

    @pytest.fixture
    def extended_spread_ratios(self):
        # 创建15天的价差比率数据
        data = [
            1.0,
            1.1,
            0.9,
            1.2,
            0.8,
            1.15,
            0.85,  # 前7天
            1.05,
            1.25,
            0.75,
            1.3,
            0.7,
            1.35,
            0.65,  # 后8天
            5.0,
        ]  # 当前价差，明显偏离历史
        return pd.Series(data)

    # 测试用例6: 正常信号检测 - MAX_SIGNAL
    def test_detect_opportunity_max_signal(self, detector, extended_spread_ratios):
        result = detector.detect_opportunity(extended_spread_ratios)
        assert result["signal_type"] == "MAX_SIGNAL"
        assert result["threshold_exceeded"] == True
        assert result["action"] == "LONG_ASSET1_SHORT_ASSET2"
        assert "timestamp" in result

    # 测试用例7: 正常信号检测 - MIN_SIGNAL
    def test_detect_opportunity_min_signal(self, detector):
        # 创建一个触发 MIN_SIGNAL 的序列
        data = [
            1.0,
            1.1,
            0.9,
            1.2,
            0.8,
            1.15,
            0.85,
            1.05,
            1.25,
            0.75,
            1.3,
            0.7,
            1.35,
            0.65,
            0.1,
        ]  # 当前价差，明显低于历史最小值
        spread_ratios = pd.Series(data)
        result = detector.detect_opportunity(spread_ratios)
        assert result["signal_type"] == "MIN_SIGNAL"
        assert result["threshold_exceeded"] == True
        assert result["action"] == "SHORT_ASSET1_LONG_ASSET2"

    # 测试用例8: 无信号检测
    def test_detect_opportunity_no_signal(self, detector, sample_spread_ratios):
        result = detector.detect_opportunity(sample_spread_ratios)
        assert result["signal_type"] == "NO_SIGNAL"
        assert result["threshold_exceeded"] == False
        assert result["action"] == "HOLD"

    # 测试用例9: 数据不足处理
    @pytest.mark.parametrize("data_length", [1, 3, 5])
    def test_detect_opportunity_insufficient_data(self, detector, data_length):
        spread_ratios = pd.Series([1.0] * data_length)
        result = detector.detect_opportunity(spread_ratios)
        assert result["signal_type"] == "NO_SIGNAL"
        assert (
            f"数据不足，需要至少{detector.lookback_days}天历史数据" in result["reason"]
        )

    # 测试用例10: 历史统计信息
    def test_get_historical_stats(self, detector, sample_spread_ratios):
        stats = detector.get_historical_stats(sample_spread_ratios)
        assert "current" in stats
        assert "max_7d" in stats
        assert "min_7d" in stats
        assert "mean_7d" in stats
        assert "std_7d" in stats
        assert stats["current"] == 0.85  # 最后一个值
        assert stats["max_7d"] == 1.2
        assert stats["min_7d"] == 0.8


class TestUniversalSpreadStrategy:
    """测试 UniversalSpreadStrategy 类"""

    @pytest.fixture
    def sample_assets(self):
        return {
            "asset1": {"symbol": "MNQ", "multiplier": 2.0, "ratio1": 1},
            "asset2": {"symbol": "MYM", "multiplier": 0.5, "ratio2": 2},
        }

    @pytest.fixture
    def strategy_params(self):
        return {"threshold": 1000, "lookback_days": 7}

    @pytest.fixture
    def strategy(self, sample_assets, strategy_params):
        return UniversalSpreadStrategy(
            sample_assets["asset1"], sample_assets["asset2"], strategy_params
        )

    # 测试用例11: 策略分析功能
    def test_analyze_spread_opportunity(self, strategy):
        result = strategy.analyze_spread_opportunity(100.0, 50.0)

        assert "price1" in result
        assert "price2" in result
        assert "spread_ratio" in result
        assert "spread_value" in result
        assert "signal" in result
        assert "historical_stats" in result
        assert result["price1"] == 100.0
        assert result["price2"] == 50.0

    # 测试用例12: 策略状态获取
    def test_get_strategy_status(self, strategy):
        status = strategy.get_strategy_status()

        assert "asset1" in status
        assert "asset2" in status
        assert "threshold" in status
        assert "lookback_days" in status
        assert "current_position" in status
        assert "history_length" in status
        assert status["asset1"] == "MNQ"
        assert status["asset2"] == "MYM"
        assert status["threshold"] == 1000


if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v"])
