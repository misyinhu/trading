#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_simnow.py -- SimNow connectivity test.

Local run:
    python scripts/test_simnow.py

Server run:
    ssh wang@100.99.204.126
    C:\\Users\\wang\\AppData\\Local\\Programs\\Python\\Python313\\python.exe C:\\projects\\trading\\scripts\\test_simnow.py
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_simnow():
    from ctp_client.trader import SimNowTrader, SimNowStatus, _HAS_VNPY

    print("=" * 50)
    print("SimNow Connectivity Test")
    print("=" * 50)
    print()

    if not _HAS_VNPY:
        print("[FAIL] vnpy_ctp not installed")
        print("On winclaw run:")
        print("  pip install vnpy_ctp")
        return False

    print("[1] Create SimNowTrader...")
    try:
        trader = SimNowTrader()
        print(f"    [OK] md_server={trader._md_server}")
    except Exception as e:
        print(f"    [FAIL] {e}")
        return False

    print()
    print("[2] Connect to SimNow (timeout 15s)...")
    ok = trader.connect(timeout=15.0)
    if not ok:
        print(f"    [FAIL] {trader.last_error()}")
        return False

    print(f"    [OK] Status: {trader.status.value}")

    print()
    print("[3] Query positions...")
    positions = trader.query_positions()
    print(f"    Position count: {len(positions)}")
    for p in positions:
        print(f"    {p.symbol} {p.direction} {p.volume} lots  avg {p.avg_price}")

    print()
    print("[4] Query account...")
    account = trader.query_account()
    if account:
        print(f"    Account: {account.account_id}")
        print(f"    Balance: {account.balance}")
        print(f"    Available: {account.available}")
        print(f"    Margin: {account.margin}")
    else:
        print("    (account data not available yet, try again)")

    print()
    print("[5] Disconnect...")
    trader.disconnect()
    print("    [OK] disconnected")

    print()
    print("=" * 50)
    print("[PASS] All SimNow checks passed")
    print("=" * 50)
    return True


if __name__ == "__main__":
    ok = test_simnow()
    sys.exit(0 if ok else 1)
