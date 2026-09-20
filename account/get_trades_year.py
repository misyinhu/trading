#!/usr/bin/env python3
"""
IBKR 交易历史获取工具
从 IBKR API 获取年度交易记录
"""

import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 确保使用正确的 Python 环境（虚拟环境支持）
try:
    from config.env_config import ensure_venv

    ensure_venv()
except ImportError:
    pass

try:
    from ib_insync import IB
except ImportError:
    print("错误: 需要安装 ib_insync")
    print("运行: pip install ib_insync")
    sys.exit(1)

from client.ibkr_client import get_client_id


def get_trades_year():
    """获取今年所有交易"""
    ib = IB()
    trades = []

    try:
        from config.env_config import get_ib_port

        ib_port = get_ib_port()
    except Exception:
        ib_port = 4001

    try:
        ib.connect("127.0.0.1", ib_port, clientId=get_client_id())

        # 获取今年1月1日至今
        year_start = datetime(datetime.now().year, 1, 1)
        now = datetime.now()

        print(
            f"获取 {year_start.strftime('%Y-%m-%d')} 至 {now.strftime('%Y-%m-%d')} 的交易..."
        )

        # 新版 API: 使用 ib.fills() 获取成交记录
        # 注意: fills() 返回会话期间所有成交，无时间过滤参数
        fills = ib.fills()

        print(f"找到 {len(fills)} 条成交记录")

        # 整理交易数据
        for fill in fills:
            trade_info = {
                "time": fill.execution.time.strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": fill.contract.symbol,
                "secType": fill.contract.secType,
                "action": fill.execution.side,
                "quantity": fill.execution.cumQty,
                "price": fill.execution.price,
                "commission": fill.commissionReport.commission
                if fill.commissionReport
                else 0,
                "account": fill.execution.acctNumber,
            }
            trades.append(trade_info)

        # 按时间排序
        trades.sort(key=lambda x: x["time"])

        return trades, fills

    except Exception as e:
        print(f"错误: {e}")
        import traceback

        traceback.print_exc()
        return [], []
    finally:
        if ib.isConnected():
            ib.disconnect()


def print_trades(trades):
    """打印交易记录"""
    if not trades:
        print("\n未找到交易记录")
        return

    print(f"\n{'=' * 80}")
    print(f"今年交易记录 (共 {len(trades)} 笔)")
    print(f"{'=' * 80}")
    print(
        f"{'时间':<20} {'代码':<8} {'类型':<6} {'方向':<6} {'数量':<8} {'价格':<12} {'佣金':<10}"
    )
    print(f"{'-' * 80}")

    for t in trades:
        print(
            f"{t['time']:<20} {t['symbol']:<8} {t['secType']:<6} {t['action']:<6} "
            f"{t['quantity']:<8.0f} {t['price']:<12.2f} {t['commission']:<10.2f}"
        )


def analyze_trades(trades):
    """分析交易"""
    if not trades:
        return

    # 按品种统计
    symbols = {}
    actions = {"BUY": 0, "SELL": 0}
    total_commission = 0

    for t in trades:
        sym = t["symbol"]
        if sym not in symbols:
            symbols[sym] = {"BUY": 0, "SELL": 0, "count": 0}
        symbols[sym][t["action"]] += t["quantity"]
        symbols[sym]["count"] += 1
        actions[t["action"]] += 1
        total_commission += t.get("commission", 0)

    print(f"\n{'=' * 80}")
    print("交易分析")
    print(f"{'=' * 80}")

    print(f"\n总交易数: {len(trades)}")
    print(f"买入次数: {actions['BUY']}")
    print(f"卖出次数: {actions['SELL']}")
    print(f"总佣金: ${total_commission:.2f}")

    print("\n按品种统计:")
    print(f"{'品种':<10} {'买入':<10} {'卖出':<10} {'交易数':<10}")
    print(f"{'-' * 40}")
    for sym, stats in sorted(symbols.items()):
        print(
            f"{sym:<10} {stats['BUY']:<10.0f} {stats['SELL']:<10.0f} {stats['count']:<10}"
        )


def save_trades(trades, filepath=None):
    """保存交易记录"""
    if filepath is None:
        home = os.path.expanduser("~")
        filepath = os.path.join(home, "trades_report.json")

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(trades, f, ensure_ascii=False, indent=2)
        print(f"\n交易记录已保存到: {filepath}")
    except Exception as e:
        print(f"\n保存失败: {e}")


def main():
    print("=" * 80)
    print("IBKR 交易历史查询工具")
    print("=" * 80)

    # 检查 IB Gateway 是否运行
    print("\n检查 IB Gateway 连接...")
    ib = IB()
    try:
        from config.env_config import get_ib_port

        ib_port = get_ib_port()
    except Exception:
        ib_port = 4001
    ib_host = "127.0.0.1"

    try:
        ib.connect(ib_host, ib_port, clientId=get_client_id())
        print("✅ IB Gateway 已连接")
        ib.disconnect()
    except Exception as e:
        print(f"❌ IB Gateway 连接失败: {e}")
        print("\n请确保:")
        print("1. IB Gateway 已启动")
        print(f"2. API 端口 {ib_port} 已打开")
        print("3. 已登录账户")
        sys.exit(1)

    # 获取交易
    trades, executions = get_trades_year()

    # 打印交易
    print_trades(trades)

    # 分析
    analyze_trades(trades)

    # 保存到用户目录
    save_trades(trades)

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
