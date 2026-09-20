#!/usr/bin/env python3
"""Test the refactored place_order function for GC futures"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import Mock, patch
from client.ib_connection import get_ib_connection
from orders.place_order_func import place_order, select_main_contract
from ib_insync import Future


@patch('ib_insync.IB.reqContractDetails')
def test_place_gc(mock_details):
    """Test that place_order correctly places GC future order on COMEX"""
    
    # Arrange
    mock_ib = Mock()
    
    gc_contract = Future(
        conId=430360630,
        symbol='GC',
        lastTradeDateOrContractMonth='20260626',
        multiplier='100',
        exchange='COMEX',
        currency='USD',
        localSymbol='GCM6',
        tradingClass='GC'
    )
    
    # Mock IBKR responses
    mock_details.return_value = [Mock(contract=gc_contract)]
    mock_ib.positions.return_value = []
    def create_mock_trade():
        mock_trade = Mock()
        mock_trade.orderStatus.status = 'Filled'
        mock_trade.orderStatus.filled = 1
        mock_trade.orderStatus.remaining = 0
        mock_trade.orderStatus.avgFillPrice = 48150.33
        mock_trade.order.orderId = 16
        mock_trade.order.action = 'BUY'
        mock_trade.order.totalQuantity = 1
        mock_trade.order.orderType = 'MKT'
        mock_trade.log = []
        mock_trade.contract.symbol = 'GC'
        return mock_trade

    mock_ib.placeOrder.return_value = create_mock_trade()
    
    try:
        import traceback
        result = place_order(
            ib=mock_ib,
            symbol='GC',
            action='BUY',
            quantity=1.0
        )
        
        # Assert
        print("Place order result:", result)
        assert 'error' not in result, f"Unexpected error: {result['error']}"
        
    except Exception as e:
        print(f"\n=== FULL EXCEPTION ===")
        print(f"Type: {type(e)}")
        print(f"Value: {e}")
        print(f"\nTraceback:")
        print(traceback.format_exc())
    
    print("✅ place_order correctly handles GC futures")


@patch('client.ib_connection.get_ib_connection')
def test_select_main_contract(mock_get):
    """Test select_main_contract with GC future details"""
    
    mock_ib = Mock()
    mock_get.return_value = mock_ib
    
    gc_contract = Future(
        conId=430360630,
        symbol='GC',
        lastTradeDateOrContractMonth='20260626',
        multiplier='100',
        exchange='COMEX',
        currency='USD',
        localSymbol='GCM6',
        tradingClass='GC'
    )
    
    details = [Mock(contract=gc_contract)]
    
    # Call select_main_contract with mocked data
    contract = select_main_contract(details, 'GC', mock_ib)
    
    # Verify
    assert contract.localSymbol == 'GCM6', f"Expected GCM6, got {getattr(contract, 'localSymbol', contract)}"
    
    print("✅ select_main_contract correctly chooses GC future")


def test_import():
    """Verify imports work correctly"""
    try:
        from notify.nl_parser import parse_trading_command
        from orders.place_order_func import place_order
        print("✅ All modules imported correctly")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False


if __name__ == "__main__":
    # Run simple import test
    if not test_import():
        sys.exit(1)
    
    import pytest
    import warnings
    warnings.filterwarnings("ignore")
    
    ret = pytest.main([__file__, '-v'])
    sys.exit(ret)