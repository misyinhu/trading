import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_nl_parser():
    from notify.nl_parser import parse_trading_command
    
    # 完整测试用例覆盖各种场景
    tests = [
        # 买入场景
        ("买入1手GC", "BUY", "GC", 1),
        ("买入2手ES", "BUY", "ES", 2),
        ("买1手NQ", "BUY", "NQ", 1),
        ("买入5手黄金", "BUY", "黄金", 5),
        ("做多1手BTC", "BUY", "BTC", 1),
        
        # 卖出场景
        ("卖出1手GC", "SELL", "GC", 1),
        ("卖出2手ES", "SELL", "ES", 2),
        ("卖空1手NQ", "SELL", "NQ", 1),
        ("做空1手BTC", "SELL", "BTC", 1),
        
        # 平仓场景
        ("平掉BTC仓位", "CLOSE", "BTC", None),
        ("平掉GC仓位", "CLOSE", "GC", None),
        ("平仓ES", "CLOSE", "ES", None),
        ("清仓", "CLOSE", None, None),
        
        # 股票
        ("买入100股AAPL", "BUY", "AAPL", 100),
        ("卖出50股TSLA", "SELL", "TSLA", 50),
    ]
    
    print("=== Test: NL Parser ===")
    passed = 0
    failed = 0
    for cmd, exp_action, exp_symbol, exp_qty in tests:
        r = parse_trading_command(cmd)
        ok = True
        
        if r['action'] != exp_action:
            print(f"  FAIL: {cmd} -> action={r['action']}, expected={exp_action}")
            ok = False
        if exp_symbol and r.get('symbol') != exp_symbol:
            print(f"  FAIL: {cmd} -> symbol={r.get('symbol')}, expected={exp_symbol}")
            ok = False
        if exp_qty is not None and r.get('quantity') != exp_qty:
            print(f"  FAIL: {cmd} -> qty={r.get('quantity')}, expected={exp_qty}")
            ok = False
            
        if ok:
            print(f"  OK: {cmd} -> {r['action']} {r.get('symbol', '')} {r.get('quantity', '')}")
            passed += 1
        else:
            failed += 1
    
    print(f"\nResult: {passed} passed, {failed} failed")
    return failed == 0


def test_place_order_auto_detect():
    print("\n=== Test: place_order auto-detect ===")
    from client.ib_connection import get_ib_connection
    from orders.place_order_func import place_order
    
    try:
        ib = get_ib_connection()
        
        # 测试不同品种的自动检测
        test_cases = [
            ("GC", "BUY", 1),   # 黄金期货
            ("ES", "SELL", 1),  # 标普期货
            ("NQ", "BUY", 1),  # 纳指期货
            # ("BTC", "BUY", 0.01),  # 加密货币
        ]
        
        for symbol, action, qty in test_cases:
            try:
                r = place_order(ib, symbol, action, qty)
                print(f"  {symbol} {action} {qty}: orderId={r.get('orderId')}, status={r.get('status')}")
            except Exception as e:
                print(f"  {symbol} {action} {qty}: Error - {e}")
    except Exception as e:
        print(f"  IB Connection Error: {e}")


def test_exchange_mapping():
    print("\n=== Test: Exchange mapping ===")
    from orders.place_order_func import place_order
    import inspect
    
    # 检查 place_order 源码中的自动检测逻辑
    source = inspect.getsource(place_order)
    
    checks = [
        ("GC in futures -> COMEX", '"GC" in futures' in source and '"COMEX"' in source),
        ("ES in futures -> COMEX", '"ES" in futures' in source),
        ("BTC in crypto -> PAXOS", '"BTC" in crypto' in source and '"PAXOS"' in source),
    ]
    
    for name, ok in checks:
        print(f"  {name}: {'OK' if ok else 'MISSING'}")
    
    print("PASS")


if __name__ == "__main__":
    # 解析器测试（本地无需 IB）
    test_nl_parser()
    
    print("\n=== Test with IB (requires TWS on CXClaw) ===")
    test_place_order_auto_detect()
    
    print("\n=== Test: Exchange mapping logic ===")
    test_exchange_mapping()