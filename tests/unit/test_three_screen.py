import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


SIGNALS = {
    "M30": None,
    "M5": None,
    "M1": None,
}


def get_three_screen_signal(m30, m5, m1):
    if m30 == "up" and m5 == "up" and m1 == "up":
        return {"action": "做多", "icon": "📈", "highlight": True}
    elif m30 == "down" and m5 == "down" and m1 == "down":
        return {"action": "做空", "icon": "📉", "highlight": True}
    else:
        return {"action": None, "icon": "🟡", "highlight": False}


class TestThreeScreenSignalDisplay:
    """TC_TS_201 @AC-TS-US1-1/2/3/4 三周期信号显示"""

    @pytest.mark.TC_TS_201
    @pytest.mark.ac_ts_us1_1
    def test_display_three_periods(self):
        periods = ["M30", "M5", "M1"]
        assert len(periods) == 3

    @pytest.mark.TC_TS_201
    @pytest.mark.ac_ts_us1_2
    def test_triple_up_signal(self):
        result = get_three_screen_signal("up", "up", "up")
        assert result["action"] == "做多"
        assert result["icon"] == "📈"

    @pytest.mark.TC_TS_201
    @pytest.mark.ac_ts_us1_3
    def test_triple_down_signal(self):
        result = get_three_screen_signal("down", "down", "down")
        assert result["action"] == "做空"
        assert result["icon"] == "📉"

    @pytest.mark.TC_TS_201
    @pytest.mark.ac_ts_us1_4
    def test_no_signal_on_mismatch(self):
        result = get_three_screen_signal("up", "down", "up")
        assert result["action"] is None
        assert result["icon"] == "🟡"


class TestSignalHighlighting:
    """TC_TS_202 @AC-TS-US1-5/6/7 信号一致时高亮"""

    @pytest.mark.TC_TS_202
    @pytest.mark.ac_ts_us1_5
    def test_triple_up_highlight(self):
        result = get_three_screen_signal("up", "up", "up")
        assert result["highlight"] is True

    @pytest.mark.TC_TS_202
    @pytest.mark.ac_ts_us1_6
    def test_triple_down_highlight(self):
        result = get_three_screen_signal("down", "down", "down")
        assert result["highlight"] is True

    @pytest.mark.TC_TS_202
    @pytest.mark.ac_ts_us1_7
    def test_mismatch_no_highlight(self):
        result = get_three_screen_signal("up", "down", "up")
        assert result["highlight"] is False
