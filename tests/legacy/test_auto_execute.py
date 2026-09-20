#!/usr/bin/env python3
"""全自动下单模式测试"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from unittest.mock import patch
from notify.signal_handler import (
    handle_submit_signal, handle_confirm_signal, handle_get_signal,
    _execute_from_signal, AUTO_EXECUTE_WHITELIST
)


class TestAutoExecuteWhitelist:
    """auto=true 白名单机制"""

    def test_whitelist_contains_quant_agent(self):
        assert "quant-agent" in AUTO_EXECUTE_WHITELIST

    def test_unknown_source_rejected_for_auto(self):
        """不在白名单的 source 使用 auto=true 被拒绝"""
        result = handle_submit_signal({
            "source": "random-source",
            "auto": True,
            "symbol": "GC",
            "direction": "long",
            "quantity": 1,
        })
        assert result["status"] == "rejected"
        assert "auto=true not allowed" in result["risk"]["reason"]

    @patch('client.ib_connection.get_ib_connection')
    @patch('orders.order_manager.OrderManager.place')
    @patch('orders.risk_gate.RiskGate.final_check')
    def test_whitelisted_source_allowed(self, mock_gate, mock_place, mock_ib):
        """白名单内的 source 使用 auto=true → 直接执行（mock IB 连接）"""
        from unittest.mock import MagicMock
        # Mock IB connected
        mock_ib.return_value = MagicMock(isConnected=lambda: True)
        # Mock risk gate allows
        mock_risk = MagicMock()
        mock_risk.allowed = True
        mock_gate.return_value = mock_risk
        # Mock place success
        mock_order_result = MagicMock()
        mock_order_result.status = "Filled"
        mock_order_result.order_id = "42"
        mock_order_result.message = ""
        mock_place.return_value = mock_order_result

        result = handle_submit_signal({
            "source": "quant-agent",
            "auto": True,
            "symbol": "GC",
            "direction": "long",
            "quantity": 1,
            "strategy": "",
        })
        assert result["status"] == "executed"
        assert result.get("mode") == "auto"
        assert result.get("order_id") == "42"


class TestAutoExecuteExecution:
    """全自动执行逻辑"""

    @patch('orders.order_manager.OrderManager.place')
    @patch('orders.risk_gate.RiskGate.final_check')
    def test_execute_from_signal_single_leg(self, mock_gate, mock_place):
        """单腿信号直接执行"""
        mock_gate.return_value.__class__.__name__ = "RiskResult"
        # Make the mock return a proper RiskResult-like object
        from unittest.mock import MagicMock
        mock_result = MagicMock()
        mock_result.allowed = True
        mock_gate.return_value = mock_result

        mock_place.return_value.__class__.__name__ = "OrderResult"
        mock_order_result = MagicMock()
        mock_order_result.status = "Filled"
        mock_order_result.order_id = "42"
        mock_order_result.message = ""
        mock_place.return_value = mock_order_result

        signal = {
            "symbol": "GC",
            "direction": "long",
            "quantity": 1,
            "strategy": "",
            "zscore": None,
            "correlation": None,
            "exchange": "IB",
        }
        result = _execute_from_signal(signal)
        assert result["status"] == "executed"
        assert result["order_id"] == "42"


class TestManualConfirmStillWorks:
    """人确认路径不受影响"""

    def test_confirm_requires_reviewed_status(self):
        """确认必须状态为 reviewed"""
        result = handle_confirm_signal("nonexistent-sig-123", "confirm")
        assert "error" in result
        assert "not found" in result["error"]


class TestSemiAutoMode:
    """半自动模式（原有行为不变）"""

    def test_no_auto_means_reviewed(self):
        """不带 auto 参数 → status=reviewed"""
        result = handle_submit_signal({
            "source": "quant-agent",
            "symbol": "GC",
            "direction": "long",
            "quantity": 1,
            # 无 equity 放行风控
        })
        assert result["status"] == "reviewed"
        assert result.get("mode") is None
