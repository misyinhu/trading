#!/usr/bin/env python3
"""测试自然语言交易功能"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_parse_buy_gc():
    """测试解析 买入1手GC"""
    from notify.nl_parser import parse_trading_command
    
    result = parse_trading_command("买入1手GC")
    print(f"Parse result: {result}")
    
    assert result['action'] == 'BUY', f"Expected BUY, got {result['action']}"
    assert result['symbol'] == 'GC', f"Expected GC, got {result['symbol']}"
    assert result['quantity'] == 1, f"Expected 1, got {result['quantity']}"
    print("✅ test_parse_buy_gc PASSED")


def test_parse_close_btc():
    """测试解析 平掉BTC仓位"""
    from notify.nl_parser import parse_trading_command
    
    result = parse_trading_command("平掉BTC仓位")
    print(f"Parse result: {result}")
    
    assert result['action'] == 'CLOSE', f"Expected CLOSE, got {result['action']}"
    assert result['symbol'] == 'BTC', f"Expected BTC, got {result['symbol']}"
    print("✅ test_parse_close_btc PASSED")


def test_place_order_gc():
    """测试GC下单（需要IB连接）"""
    from client.ib_connection import get_ib_connection
    from orders.place_order_func import place_order
    
    print("Connecting to IB...")
    ib = get_ib_connection()
    
    print("Placing GC order...")
    result = place_order(ib, "GC", "BUY", 1, sec_type="FUT", use_main_contract=True)
    print(f"Order result: {result}")
    
    # 检查结果
    if 'error' in result:
        print(f"❌ Order failed: {result['error']}")
        return False
    
    print("✅ test_place_order_gc PASSED")
    return True


def test_sec_type_detection():
    """测试期货类型检测"""
    test_cases = [
        ("GC", "FUT"),
        ("ES", "FUT"),
        ("NQ", "FUT"),
        ("AAPL", "STK"),
        ("TSLA", "STK"),
    ]
    
    for symbol, expected in test_cases:
        sec = "FUT" if symbol in ("GC", "ES", "NQ", "YM", "ZB", "ZN") else "STK"
        assert sec == expected, f"Expected {expected} for {symbol}, got {sec}"
        print(f"  {symbol} -> {sec}")
    
    print("✅ test_sec_type_detection PASSED")


if __name__ == "__main__":
    print("=" * 50)
    print("Running NL Trading Tests")
    print("=" * 50)
    
    # 测试解析（不需要IB）
    test_parse_buy_gc()
    test_parse_close_btc()
    test_sec_type_detection()
    
    print("=" * 50)
    print("Testing IB order (requires TWS running)...")
    print("=" * 50)
    
    # 尝试下单测试
    try:
        test_place_order_gc()
    except Exception as e:
        print(f"❌ IB test failed: {e}")
    
    print("=" * 50)
    print("Tests complete")
    print("=" * 50)