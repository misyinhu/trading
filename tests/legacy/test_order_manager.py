#!/usr/bin/env python3
"""OrderManager 单元测试"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from unittest.mock import Mock, patch
from orders.order_manager import OrderManager, OrderStatus
from orders.risk_gate import OrderContext, RiskResult, GateMode


@patch('client.ib_connection.get_ib_connection')
@patch('orders.place_order_func.place_order')
def test_place_ib_order(mock_place, mock_ib_conn):
    """OrderManager 路由 IB 订单"""
    mock_place.return_value = {"status": "Filled", "orderId": 42, "filled": 1}
    mock_ib_conn.return_value = Mock()  # 返回 Mock IB 对象
    mgr = OrderManager()
    ctx = OrderContext(symbol="GC", action="BUY", quantity=1, exchange="IB")
    result = mgr.place(ctx, gate_mode=GateMode.ADVISORY)
    assert result.status == "Filled"
    assert result.order_id == "42"


@patch('orders.place_order_func.place_order')
def test_risk_gate_blocks_order(mock_place):
    """风控拦截时不下单（不触发 IB 连接）"""
    mock_place.return_value = {"status": "Filled", "orderId": 99}
    mgr = OrderManager()
    ctx = OrderContext(symbol="GC", action="BUY", quantity=1,
                       exchange="IB", equity=100000, day_pnl=-6000)
    result = mgr.place(ctx, gate_mode=GateMode.STRICT)
    assert result.status == "rejected"
    assert "daily loss" in result.message.lower()
    assert not result.order_id
    mock_place.assert_not_called()  # 风控拦截后不应调 place_order


def test_okx_pending_status():
    """OKX 订单返回 pending 状态"""
    mgr = OrderManager()
    ctx = OrderContext(symbol="DOGE-USDT", action="BUY", quantity=100,
                       exchange="OKX")
    result = mgr.place(ctx, gate_mode=GateMode.ADVISORY)
    assert result.status in ("Submitted", "pending")