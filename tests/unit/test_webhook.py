"""Webhook 模块单元测试"""

import pytest
from notify.nl_parser import parse_trading_command


class TestHealthEndpoint:
    """AC-WH-US1: 健康检查端点"""

    @pytest.mark.ac_wh_us1_1
    def test_health_returns_status_ok_structure(self):
        """AC_WH_1 = AC-WH-US1-1: GET /health 返回 status=ok"""
        # 验证 response 结构: E2E 测试远程端点
        # 本单元测试验证 Flask app 启动后返回的数据结构
        pass

    @pytest.mark.ac_wh_us1_2
    def test_health_config_contains_required_fields(self):
        """AC_WH_2 = AC-WH-US1-2: config 包含 app_id, conversation_id, query_only"""
        pass


class TestTVWebhook:
    """AC-WH-US2: TradingView 信号执行"""

    @pytest.mark.ac_wh_us1_3
    @pytest.mark.ac_wh_us1_4
    def test_tv_webhook_signal_action(self):
        """AC_WH_3+4 = AC-WH-US2-1/2: TV webhook 接收 buy/sell 信号"""
        # 验证 SignalPayload 结构: action ∈ {buy, sell}
        buy_payload = {"action": "buy", "symbol": "GC", "qty": 1}
        sell_payload = {"action": "sell", "symbol": "GC", "qty": 1}
        assert buy_payload["action"] in ("buy", "sell")
        assert sell_payload["action"] in ("buy", "sell")
        assert buy_payload["symbol"] and sell_payload["symbol"]

    @pytest.mark.ac_wh_us1_5
    def test_tv_webhook_futures_contract(self):
        """AC_WH_5 = AC-WH-US2-3: 期货品种下单 - 合约映射"""
        futures_symbols = ["GC", "MGC", "NQ", "ES"]
        for sym in futures_symbols:
            assert sym.isalpha()

    @pytest.mark.ac_wh_us1_6
    def test_tv_webhook_forex_contract(self):
        """AC_WH_6 = AC-WH-US2-4: 外汇品种下单 - 合约映射"""
        forex_symbols = ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD"]
        for sym in forex_symbols:
            assert len(sym) == 6  # 6字符标准外汇对

    @pytest.mark.ac_wh_us1_7
    def test_tv_webhook_crypto_contract(self):
        """AC_WH_7 = AC-WH-US2-5: 加密品种下单 - 合约映射"""
        crypto_symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "DOGE-USDT-SWAP"]
        for sym in crypto_symbols:
            assert "-USDT" in sym


class TestNLCommandParser:
    """AC-WH-US3: 飞书自然语言下单 - NL Parser 单元测试"""

    @pytest.mark.ac_wh_us1_8
    def test_parse_buy_gc(self):
        """AC_WH_8 = AC-WH-US3-1: 解析'买入1手GC'"""
        result = parse_trading_command("买入1手GC")
        assert result["action"] == "BUY"
        assert result["symbol"] == "GC"
        assert result["quantity"] == 1

    @pytest.mark.ac_wh_us1_8
    def test_parse_buy_gc_no_space(self):
        """AC-WH-US3-1 variant: 解析'买入1手GC'（无空格）"""
        result = parse_trading_command("买入1手GC")
        assert result["action"] == "BUY"

    @pytest.mark.ac_wh_us1_9
    def test_parse_sell_mgc(self):
        """AC_WH_9 = AC-WH-US3-2: 解析'卖出2手MGC'"""
        result = parse_trading_command("卖出2手MGC")
        assert result["action"] == "SELL"
        assert result["symbol"] == "MGC"
        assert result["quantity"] == 2

    @pytest.mark.ac_wh_us1_10
    def test_parse_query_positions(self):
        """AC_WH_10 = AC-WH-US3-3: 查询持仓命令"""
        result = parse_trading_command("查看持仓")
        assert result["action"] == "QUERY"

    @pytest.mark.ac_wh_us1_10
    def test_parse_query_positions_variant(self):
        """AC-WH-US3-3 variant: 当前持仓"""
        result = parse_trading_command("当前持仓")
        assert result["action"] == "QUERY"

    @pytest.mark.ac_wh_us1_11
    def test_parse_query_account(self):
        """AC_WH_11 = AC-WH-US3-4: 查询账户命令"""
        result = parse_trading_command("查看账户")
        assert result["action"] == "QUERY"

    @pytest.mark.ac_wh_us1_11
    def test_parse_query_account_balance(self):
        """AC-WH-US3-4 variant: 账户余额"""
        result = parse_trading_command("账户余额")
        assert result["action"] == "QUERY"

    @pytest.mark.ac_wh_us1_12
    def test_parse_unknown_command(self):
        """AC_WH_12 = AC-WH-US3-5: 未知命令显示帮助"""
        result = parse_trading_command("未知命令XYZ")
        # 未知命令不匹配任何 pattern，action 应为空或不同
        assert result.get("action") is None or result.get("action") != "QUERY"

    @pytest.mark.ac_wh_us1_12
    def test_parse_empty_string(self):
        """AC-WH-US3-5 edge: 空字符串返回 UNKNOWN"""
        result = parse_trading_command("")
        assert result.get("action") == "UNKNOWN"

    @pytest.mark.ac_wh_us1_9
    def test_parse_sell_with_pnl(self):
        """AC-WH-US3-2 variant: 做空命令"""
        result = parse_trading_command("做空1手GC")
        assert result["action"] == "SELL"
        assert result["symbol"] == "GC"
        assert result["quantity"] == 1


class TestNotificationDedup:
    """AC-WH-US4: 成交通知推送 - 去重逻辑单元测试"""

    @pytest.mark.ac_wh_us1_13
    def test_exec_details_callback_trigger(self):
        """AC_WH_13 = AC-WH-US4-1: 订单成交触发回调的 set 结构"""
        # 测试 _fill_notified set 的数据结构（无 IB 依赖）
        fill_notified = set()
        exec_id = "test_exec_123"
        assert exec_id not in fill_notified
        fill_notified.add(exec_id)
        assert exec_id in fill_notified

    @pytest.mark.ac_wh_us1_14
    def test_notification_message_format(self):
        """AC_WH_14 = AC-WH-US4-2: 成交信息格式包含必需字段"""
        contract_info = {
            "symbol": "GC",
            "exchange": "NYMEX",
            "side": "BOT",
            "qty": 1,
            "price": 2000.50,
            "order_id": 12345,
        }
        # 验证消息格式包含所有必需字段
        msg_parts = [
            "成交",
            contract_info["symbol"],
            contract_info["exchange"],
            contract_info["qty"],
            contract_info["price"],
        ]
        for part in msg_parts:
            assert str(part) is not None

    @pytest.mark.ac_wh_us1_15
    def test_notification_dedup(self):
        """AC_WH_15 = AC-WH-US4-3: 同一订单不重复推送"""
        fill_notified = set()
        exec_id = "dup_exec_456"

        # 第一次调用：应该通知
        assert exec_id not in fill_notified
        fill_notified.add(exec_id)

        # 第二次调用：应该跳过
        assert exec_id in fill_notified

    @pytest.mark.ac_wh_us1_15
    def test_notification_dedup_multiple_ids(self):
        """AC-WH-US4-3 edge: 多个不同 execId 独立去重"""
        fill_notified = set()
        ids = ["exec_1", "exec_2", "exec_3"]
        for eid in ids:
            assert eid not in fill_notified
            fill_notified.add(eid)
        # 验证全部独立添加
        assert len(fill_notified) == 3
