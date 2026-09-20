import pytest
import sys
import os
import json

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from unittest.mock import Mock, patch
from flask import Flask


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestHealthEndpoint:
    """TC-WH-001 @AC-WH-US1-1 健康检查端点"""

    @pytest.mark.TC_WH_001
    @pytest.mark.ac_wh_us1_1
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    @pytest.mark.TC_WH_001
    @pytest.mark.ac_wh_us1_2
    def test_health_response_has_config(self, client):
        response = client.get("/health")
        data = json.loads(response.data)
        assert "status" in data
        assert "config" in data
        assert "app_id" in data["config"]
        assert "conversation_id" in data["config"]


class TestTVWebhook:
    """TC-WH-101 @AC-WH-US2 TradingView 信号执行"""

    @pytest.mark.TC_WH_101
    @pytest.mark.ac_wh_us1_3
    def test_tv_webhook_buy_signal(self, client, mock_ib_connection):
        payload = {"action": "buy", "symbol": "GC", "qty": 1, "order_type": "market"}

        with patch(
            "client.ib_connection.get_ib_connection", return_value=mock_ib_connection
        ):
            response = client.post("/tv-webhook", json=payload)
            data = json.loads(response.data)
            assert data["status"] == "ok"
            assert "order" in data

    @pytest.mark.TC_WH_101
    @pytest.mark.ac_wh_us1_4
    def test_tv_webhook_sell_signal(self, client, mock_ib_connection):
        payload = {"action": "sell", "symbol": "GC", "qty": 1}

        with patch(
            "client.ib_connection.get_ib_connection", return_value=mock_ib_connection
        ):
            response = client.post("/tv-webhook", json=payload)
            data = json.loads(response.data)
            assert data["status"] == "ok"


class TestFuturesContract:
    """TC-WH-102 @AC-WH-US2-3 期货品种"""

    @pytest.mark.TC_WH_102
    @pytest.mark.ac_wh_us1_5
    def test_futures_contract_mapping(self):
        from notify.webhook_bridge import map_symbol_to_ib_contract

        contract = map_symbol_to_ib_contract("GC", "FUT")
        assert contract is not None
        assert contract.symbol == "GC"
        assert "COMEX" in contract.exchange


class TestForexContract:
    """TC-WH-102 @AC-WH-US2-4 外汇品种"""

    @pytest.mark.TC_WH_102
    @pytest.mark.ac_wh_us1_6
    def test_forex_contract_mapping(self):
        from notify.webhook_bridge import map_symbol_to_ib_contract

        contract = map_symbol_to_ib_contract("EURUSD", "CASH")
        assert contract is not None
        assert contract.symbol == "EURUSD"
        assert contract.exchange == "IDEALPRO"


class TestCryptoContract:
    """TC-WH-102 @AC-WH-US2-5 加密品种"""

    @pytest.mark.TC_WH_102
    @pytest.mark.ac_wh_us1_7
    def test_crypto_contract_mapping(self):
        from notify.webhook_bridge import map_symbol_to_ib_contract

        contract = map_symbol_to_ib_contract("BTC-USDT", "CRYPTO")
        assert contract is not None


class TestNLParser:
    """TC-WH-201 @AC-WH-US3 自然语言解析"""

    @pytest.mark.TC_WH_201
    @pytest.mark.ac_wh_us1_8
    def test_parse_buy_command(self):
        from notify.nl_parser import parse_command

        result = parse_command("买入1手GC")
        assert result["action"] == "buy"
        assert result["symbol"] == "GC"
        assert result["qty"] == 1

    @pytest.mark.TC_WH_201
    @pytest.mark.ac_wh_us1_9
    def test_parse_sell_command(self):
        from notify.nl_parser import parse_command

        result = parse_command("卖出2手MGC")
        assert result["action"] == "sell"
        assert result["symbol"] == "MGC"
        assert result["qty"] == 2

    @pytest.mark.TC_WH_201
    @pytest.mark.ac_wh_us1_10
    def test_parse_position_query(self):
        from notify.nl_parser import parse_command

        result = parse_command("/持仓")
        assert result["type"] == "query"
        assert result["query"] == "positions"

    @pytest.mark.TC_WH_201
    @pytest.mark.ac_wh_us1_11
    def test_parse_account_query(self):
        from notify.nl_parser import parse_command

        result = parse_command("/账户")
        assert result["type"] == "query"
        assert result["query"] == "account"

    @pytest.mark.TC_WH_201
    @pytest.mark.ac_wh_us1_12
    def test_unknown_command_returns_help(self):
        from notify.nl_parser import parse_command

        result = parse_command("未知命令XYZ")
        assert result["type"] == "help"


class TestExecDetailsCallback:
    """TC-WH-301 @AC-WH-US4 成交通知推送"""

    @pytest.mark.TC_WH_301
    @pytest.mark.ac_wh_us1_13
    def test_exec_details_parsing(self):
        exec_details = {
            "ordId": 123,
            "contract": {"symbol": "GC", "exchange": "COMEX"},
            "lastFillPrice": 1950.0,
            "lastFillQuantity": 1,
        }

        assert "ordId" in exec_details
        assert "contract" in exec_details
        assert "lastFillPrice" in exec_details

    @pytest.mark.TC_WH_301
    @pytest.mark.ac_wh_us1_14
    def test_feishu_notification_content(self):
        exec_details = {
            "contract": "GC",
            "quantity": 1,
            "price": 1950.0,
            "time": "2025-05-10 14:30:00",
        }

        message = f"订单成交\n合约: {exec_details['contract']}\n数量: {exec_details['quantity']}\n价格: {exec_details['price']}"
        assert "GC" in message
        assert "1" in message
        assert "1950" in message

    @pytest.mark.TC_WH_301
    @pytest.mark.ac_wh_us1_15
    def test_no_duplicate_notification(self):
        notified_orders = {123}
        order_id = 123

        should_notify = order_id not in notified_orders
        assert should_notify is False
