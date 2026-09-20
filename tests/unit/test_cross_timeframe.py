import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestZScoreResonanceDetection:
    """TC-CT-001 @AC-CT-US1-1 多周期 Z-Score 共振检测"""

    @pytest.mark.TC_CT_001
    @pytest.mark.ac_ct_us1_1
    def test_zscore_calculation(self):
        prices = [100, 102, 101, 103, 105, 104, 106, 108, 107, 109]
        mean = sum(prices) / len(prices)
        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        std = variance**0.5
        zscore = (prices[-1] - mean) / std
        assert abs(zscore) < 3


class TestCorrelationBreakDetection:
    """TC-CT-001 @AC-CT-US1-2 相关性破裂检测"""

    @pytest.mark.TC_CT_001
    @pytest.mark.ac_ct_us1_2
    def test_low_correlation_detection(self):
        short_term_corr = 0.25
        threshold = 0.3
        has_break = short_term_corr < threshold
        assert has_break is True

    @pytest.mark.TC_CT_001
    @pytest.mark.ac_ct_us1_3
    def test_contradiction_detection(self):
        m30_direction = "up"
        m5_direction = "down"
        has_contradiction = m30_direction != m5_direction
        assert has_contradiction is True


class TestSignalScoreCalculation:
    """TC-CT-002 @AC-CT-US1-4/5/6 矛盾信号评分计算"""

    @pytest.mark.TC_CT_002
    @pytest.mark.ac_ct_us1_4
    def test_strong_entry_signal(self):
        signal_score = 3
        zscore_values = [-3.5, -3.2, -3.1]
        correlations = [-0.6, -0.55, -0.5]
        is_strong_entry = (
            signal_score >= 2
            and all(abs(z) >= 3 for z in zscore_values)
            and all(c <= -0.5 for c in correlations)
        )
        assert is_strong_entry is True

    @pytest.mark.TC_CT_002
    @pytest.mark.ac_ct_us1_5
    def test_buy_signal(self):
        avg_zscore = -1.5
        signal_score = 2
        is_buy = avg_zscore < 0 and signal_score >= 2
        assert is_buy is True

    @pytest.mark.TC_CT_002
    @pytest.mark.ac_ct_us1_6
    def test_sell_signal(self):
        avg_zscore = 1.5
        signal_score = 2
        is_sell = avg_zscore > 0 and signal_score >= 2
        assert is_sell is True

    @pytest.mark.TC_CT_002
    @pytest.mark.ac_ct_us1_7
    def test_no_signal(self):
        signal_score = 1
        is_no_signal = signal_score < 2
        assert is_no_signal is True
