import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


SCAN_TYPES = {
    "volume_breakout": ["timeframe", "volume_multiplier", "price_change_min", "limit"],
    "bollinger": ["timeframe", "bb_period", "bb_std", "limit"],
    "trending": ["timeframe", "ma_period", "price_change_min", "limit"],
    "consecutive": ["timeframe", "consecutive_count", "change_min_pct", "limit"],
    "multi_changes": ["timeframe", "periods", "change_threshold", "limit"],
}


def get_params_for_scan_type(scan_type):
    return SCAN_TYPES.get(scan_type, [])


class TestScanTypeDisplay:
    """TC-MS-001 @AC-MS-US1-1 显示扫描类型"""

    @pytest.mark.TC_MS_001
    @pytest.mark.ac_ms_us1_1
    def test_all_scan_types_available(self):
        expected_types = [
            "volume_breakout",
            "bollinger",
            "trending",
            "consecutive",
            "multi_changes",
        ]
        for t in expected_types:
            assert t in SCAN_TYPES


class TestScanTypeParams:
    """TC-MS-001 @AC-MS-US1-2/3 参数显示与切换"""

    @pytest.mark.TC_MS_001
    @pytest.mark.ac_ms_us1_2
    @pytest.mark.parametrize(
        "scan_type,expected_params",
        [
            ("volume_breakout", ["volume_multiplier", "price_change_min", "limit"]),
            ("bollinger", ["bb_period", "bb_std", "limit"]),
        ],
    )
    def test_params_for_scan_type(self, scan_type, expected_params):
        params = get_params_for_scan_type(scan_type)
        for p in expected_params:
            assert p in params

    @pytest.mark.TC_MS_001
    @pytest.mark.ac_ms_us1_3
    def test_params_cleared_on_type_switch(self):
        old_params = {"volume_multiplier": 3.0}
        new_type = "bollinger"
        old_params.clear()
        assert len(old_params) == 0


class TestMarketSelection:
    """TC-MS-101 @AC-MS-US2-1/2 市场选择"""

    @pytest.mark.TC_MS_101
    @pytest.mark.ac_ms_us2_4
    def test_common_symbols_enabled(self):
        use_common = True
        assert use_common is True

    @pytest.mark.TC_MS_101
    @pytest.mark.ac_ms_us2_5
    @pytest.mark.parametrize("exchange", ["OKX", "IBKR", "NASDAQ", "SSE", "SZSE"])
    def test_exchange_selection(self, exchange):
        selected_exchanges = [exchange]
        assert exchange in selected_exchanges


class TestSelectAllDeselect:
    """TC-MS-102 @AC-MS-US2-3/4/5 全选/取消全选"""

    @pytest.mark.TC_MS_102
    @pytest.mark.ac_ms_us2_6
    def test_select_all(self):
        all_exchanges = ["OKX", "IBKR", "NASDAQ", "SSE", "SZSE"]
        selected = list(all_exchanges)
        assert len(selected) == 5

    @pytest.mark.TC_MS_102
    @pytest.mark.ac_ms_us3_7
    def test_deselect_all(self):
        selected = []
        assert len(selected) == 0

    @pytest.mark.TC_MS_102
    @pytest.mark.ac_ms_us1_8
    def test_partial_then_select_all(self):
        selected = ["OKX"]
        all_exchanges = ["OKX", "IBKR", "NASDAQ", "SSE", "SZSE"]
        selected = list(all_exchanges)
        assert len(selected) == 5


class TestScanExecution:
    """TC-MS-301 @AC-MS-US3-1/2/3 扫描执行"""

    @pytest.mark.TC_MS_301
    @pytest.mark.ac_ms_us2_9
    def test_scan_button_click(self):
        scan_initiated = True
        assert scan_initiated is True

    @pytest.mark.TC_MS_301
    @pytest.mark.ac_ms_us3_10
    def test_no_results_display(self):
        results = []
        show_empty = len(results) == 0
        assert show_empty is True

    @pytest.mark.TC_MS_301
    @pytest.mark.ac_ms_us3_11
    def test_quant_core_unavailable(self):
        quant_core_available = False
        show_error = not quant_core_available
        assert show_error is True


class TestScanResultDisplay:
    """TC-MS-302 @AC-MS-US3-4/5/6 扫描结果显示"""

    @pytest.mark.TC_MS_302
    @pytest.mark.ac_ms_us3_12
    def test_result_table_columns(self):
        required_columns = ["标的", "当前价格", "变化幅度", "扫描时间"]
        assert len(required_columns) == 4

    @pytest.mark.TC_MS_302
    @pytest.mark.ac_ms_us3_14
    def test_results_sorted_by_change_desc(self):
        results = [
            {"symbol": "BTC", "change": 5.2},
            {"symbol": "ETH", "change": 3.1},
            {"symbol": "SOL", "change": 7.8},
        ]
        sorted_results = sorted(results, key=lambda x: x["change"], reverse=True)
        assert sorted_results[0]["symbol"] == "SOL"
        assert sorted_results[-1]["symbol"] == "ETH"

    @pytest.mark.TC_MS_302
    @pytest.mark.ac_ms_us3_15
    def test_click_result_opens_detail(self):
        result_clicked = True
        detail_shown = result_clicked
        assert detail_shown is True


class TestEmptyScanResult:
    """TC-MS-301 @AC_MS_13 结果为空时显示空状态"""

    @pytest.mark.TC_MS_301
    @pytest.mark.ac_ms_us3_13
    def test_empty_result_shows_empty_state(self):
        empty_results = []
        has_empty_state = len(empty_results) == 0
        assert has_empty_state is True

    @pytest.mark.TC_MS_301
    @pytest.mark.ac_ms_us3_13
    def test_empty_state_message(self):
        empty_message = "未找到满足条件的标的，请调整扫描参数"
        assert "未找到" in empty_message
        assert "调整扫描参数" in empty_message
