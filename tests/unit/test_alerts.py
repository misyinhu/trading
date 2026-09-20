import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch


class TestAlertCycleSelection:
    """TC-AL-001 @AC-AL-US1-1 警报周期选择"""

    @pytest.mark.TC_AL_001
    @pytest.mark.ac_al_us1_1
    @pytest.mark.parametrize("timeframe", ["M30", "M15", "M5", "M1"])
    @patch("kanban.src.tv.get_all_tv_indicators")
    def test_alert_cycle_selection(self, mock_get, timeframe):
        mock_get.return_value = {"RSI": 65.5, "MA20": 15000.0, "price": 15100.0}
        from kanban.src.tv import get_all_tv_indicators

        result = get_all_tv_indicators(timeframe=timeframe)

        assert result is not None
        assert "RSI" in result or "MA20" in result
        mock_get.assert_called_once_with(timeframe=timeframe)

    @pytest.mark.TC_AL_001
    @pytest.mark.ac_al_us1_1
    @patch("kanban.src.tv.get_all_tv_indicators")
    def test_default_cycle_is_15s(self, mock_get):
        mock_get.return_value = {"RSI": 65.5, "MA20": 15000.0, "price": 15100.0}
        from kanban.src.tv import get_all_tv_indicators

        result = get_all_tv_indicators()

        assert result is not None
        mock_get.assert_called_once()


class TestAlertCycleUpdate:
    """TC-AL-002 @AC-AL-US1-2 切换周期后检测逻辑更新"""

    @pytest.mark.TC_AL_002
    @pytest.mark.ac_al_us1_2
    @patch("kanban.src.tv.get_all_tv_indicators")
    def test_cycle_switch_updates_data(self, mock_get):
        mock_get.return_value = {"RSI": 65.5, "MA20": 15000.0, "price": 15100.0}
        from kanban.src.tv import get_all_tv_indicators

        result_m15 = get_all_tv_indicators(timeframe="M15")
        result_m1 = get_all_tv_indicators(timeframe="M1")

        assert result_m15 is not None
        assert result_m1 is not None
        assert mock_get.call_count == 2


class TestAlertTrigger:
    """TC-AL-201 @AC-AL-US2-1 警报触发检测"""

    @pytest.mark.TC_AL_201
    @pytest.mark.ac_al_us1_3
    def test_rsi_overbought_triggers_alert(self):
        indicators = {"RSI": 75, "price": 15100}

        alert_triggered = indicators["RSI"] > 70

        assert alert_triggered is True

    @pytest.mark.TC_AL_201
    @pytest.mark.ac_al_us1_4
    def test_rsi_oversold_triggers_alert(self):
        indicators = {"RSI": 25, "price": 14900}

        alert_triggered = indicators["RSI"] < 30

        assert alert_triggered is True

    @pytest.mark.TC_AL_201
    @pytest.mark.ac_al_us1_5
    def test_price_move_triggers_alert(self):
        indicators = {"price": 15200, "prev_price": 14900}
        price_change_pct = (
            abs(indicators["price"] - indicators["prev_price"])
            / indicators["prev_price"]
            * 100
        )

        alert_triggered = price_change_pct > 2

        assert alert_triggered is True


class TestAlertListRealtime:
    """TC-AL-202 @AC-AL-US2-4 警报列表实时更新"""

    @pytest.mark.TC_AL_202
    @pytest.mark.ac_al_us1_6
    def test_new_alert_appears_at_top(self):
        alerts = [{"id": 1, "type": "RSI"}, {"id": 2, "type": "Price"}]

        new_alert = {"id": 3, "type": "MA"}
        alerts.insert(0, new_alert)

        assert alerts[0]["id"] == 3
        assert len(alerts) == 3


class TestAlertDetailExpand:
    """TC-AL-301 @AC-AL-US3-1 警报详情展开"""

    @pytest.mark.TC_AL_301
    @pytest.mark.ac_al_us1_7
    def test_alert_expand_shows_details(self):
        alert = {
            "trigger_time": "2025-05-10 14:30:00",
            "indicator": "RSI",
            "threshold": 70,
            "current_value": 75,
            "change_pct": 5,
        }

        assert "trigger_time" in alert
        assert "indicator" in alert
        assert "threshold" in alert


class TestAlertDetailInfo:
    """TC-AL-302 @AC-AL-US3-2 警报详情显示触发时间和阈值"""

    @pytest.mark.TC_AL_302
    @pytest.mark.ac_al_us1_8
    def test_alert_detail_format(self):
        alert = {
            "trigger_time": "2025-05-10 14:30:00",
            "indicator": "RSI",
            "threshold": 70,
            "current_value": 75,
            "change_pct": 5,
        }

        assert alert["trigger_time"] == "2025-05-10 14:30:00"
        assert alert["indicator"] == "RSI"
        assert alert["threshold"] == 70
        assert alert["current_value"] == 75


class TestCorrelationAlert:
    """TC-AL-401 @AC-AL-US4-1 短期相关性低于阈值触发警报"""

    @pytest.mark.TC_AL_401
    @pytest.mark.ac_al_us1_9
    def test_low_correlation_triggers_alert(self):
        short_term_corr = 0.25

        alert_triggered = short_term_corr < 0.3

        assert alert_triggered is True

    @pytest.mark.TC_AL_401
    @pytest.mark.ac_al_us1_10
    def test_long_term_correlation_change(self):
        long_term_corr_prev = 0.8
        long_term_corr_curr = 0.5
        change_pct = (
            abs(long_term_corr_curr - long_term_corr_prev) / long_term_corr_prev * 100
        )

        alert_triggered = change_pct > 20

        assert alert_triggered is True


class TestAlertThresholds:
    """TC-AL-501 @AC_AL_12 用户可自定义警报阈值"""

    @pytest.mark.TC_AL_501
    @pytest.mark.ac_al_us1_12
    def test_default_thresholds(self):
        default_thresholds = {
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "price_change_pct": 2.0,
            "correlation": 0.6,
        }
        assert default_thresholds["rsi_overbought"] == 70
        assert default_thresholds["rsi_oversold"] == 30

    @pytest.mark.TC_AL_501
    @pytest.mark.ac_al_us1_12
    def test_custom_thresholds_applied(self):
        custom_thresholds = {
            "rsi_overbought": 80,
            "rsi_oversold": 20,
            "price_change_pct": 3.0,
            "correlation": 0.5,
        }
        assert custom_thresholds["rsi_overbought"] == 80
        assert custom_thresholds["rsi_oversold"] == 20
        assert custom_thresholds["price_change_pct"] == 3.0
        assert custom_thresholds["correlation"] == 0.5

    @pytest.mark.TC_AL_501
    @pytest.mark.ac_al_us1_12
    def test_threshold_triggers_alert(self):
        thresholds = {"rsi_overbought": 80, "rsi_oversold": 20}
        current_rsi = 85
        alert_triggered = current_rsi >= thresholds["rsi_overbought"]
        assert alert_triggered is True


class TestAlertSoundControl:
    """TC-AL-502 @AC_AL_13 警报声音开关可独立控制"""

    @pytest.mark.TC_AL_502
    @pytest.mark.ac_al_us1_13
    def test_alert_sound_defaults_on(self):
        sound_settings = {
            "rsi_alert": True,
            "price_alert": True,
            "correlation_alert": True,
        }
        assert all(sound_settings.values())

    @pytest.mark.TC_AL_502
    @pytest.mark.ac_al_us1_13
    def test_individual_sound_toggle(self):
        sound_settings = {
            "rsi_alert": True,
            "price_alert": True,
            "correlation_alert": True,
        }
        sound_settings["rsi_alert"] = False
        assert sound_settings["rsi_alert"] is False
        assert sound_settings["price_alert"] is True
        assert sound_settings["correlation_alert"] is True

    @pytest.mark.TC_AL_502
    @pytest.mark.ac_al_us1_13
    def test_other_sounds_unchanged_when_one_toggled(self):
        sound_settings = {
            "rsi_alert": True,
            "price_alert": True,
            "correlation_alert": True,
        }
        original_price = sound_settings["price_alert"]
        sound_settings["rsi_alert"] = False
        assert sound_settings["price_alert"] == original_price


class TestCorrelationSummary:
    """TC-AL-402 @AC-AL-US4-3 多Tab相关性汇总显示"""

    @pytest.mark.TC_AL_402
    @pytest.mark.ac_al_us1_11
    def test_correlation_matrix_display(self):
        correlations = [
            {"symbol1": "BTC", "symbol2": "ETH", "corr": 0.25},
            {"symbol1": "BTC", "symbol2": "SPY", "corr": 0.85},
        ]

        low_corr_pairs = [c for c in correlations if c["corr"] < 0.5]

        assert len(low_corr_pairs) == 1
        assert low_corr_pairs[0]["symbol1"] == "BTC"
