#!/usr/bin/env python3
"""
TradingView Webhook -> 飞书 中转服务
支持Webhook URL、飞书消息控制、命令执行、自然语言下单
"""

import os
import sys

# 设置代理（必须在OKX SDK导入之前）
os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"

# 首先应用 nest_asyncio patch（必须在导入 ib_insync 之前）
try:
    from ib_insync.util import patchAsyncio

    patchAsyncio()
except Exception:
    pass

import json
import subprocess
import time
import logging
import json
from pathlib import Path
from flask import Flask, request, jsonify
import requests
import yaml

# 添加配置路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)
from config import (
    load_config,
    is_query_only,
    set_query_only,
    get_webhook_port,
    get_project_root,
)
from client.ib_connection import get_ib_connection, get_ib_manager
from notify.nl_parser import parse_trading_command
from concurrent.futures import ThreadPoolExecutor
import threading
import sys

# Background executor for submitting orders without blocking HTTP request
_order_executor = ThreadPoolExecutor(max_workers=4)


def _submit_order_in_background(
    ib,
    symbol,
    action,
    quantity,
    exchange=None,
    sec_type=None,
    conId=None,
    close_position=False,
    outside_rth=None,
):
    """在后台提交订单，避免阻塞主线程。

    对于期货（FUT）默认启用 outsideRth=True，允许盘前/盘后交易。
    """
    # 期货默认启用盘前交易
    if outside_rth is None:
        outside_rth = True  # 默认启用，支持期货盘前订单

    def _order_job():
        try:
            from orders.place_order_func import place_order

            return place_order(
                ib,
                symbol,
                action,
                quantity,
                exchange=exchange,
                sec_type=sec_type,
                conId=conId,
                close_position=close_position,
                outside_rth=outside_rth,
            )
        except Exception as e:
            print(f"[FEISHU] Background order error: {e}", file=sys.stderr)
            return {"error": str(e)}

    return _order_executor.submit(_order_job)


# ============ execDetails 回调 - 成交实时通知 ============
_fill_notified = set()  # 已通知的 execId，避免重复


def _on_exec_details(trade, fill):
    """IB 成交回调 - 通过飞书实时推送"""
    try:
        exec_id = fill.execution.execId
        if exec_id in _fill_notified:
            return
        _fill_notified.add(exec_id)

        contract = trade.contract
        symbol = getattr(contract, "localSymbol", contract.symbol)
        exchange = getattr(contract, "exchange", "")
        side = fill.execution.side  # BOT/SLD
        qty = fill.execution.shares
        price = fill.execution.price
        avg_price = fill.execution.avgPrice or price
        order_id = getattr(fill.execution, "orderId", 0)
        exec_time = fill.execution.time

        # 获取盈亏信息
        real_pnl = getattr(fill, "commissionReport", None)
        commission = getattr(real_pnl, "commission", 0) if real_pnl else 0
        realized_pnl = getattr(real_pnl, "realizedPNL", 0) if real_pnl else 0

        # 翻译方向
        action_cn = "买入" if side == "BOT" else "卖出" if side == "SLD" else side

        # 格式化时间 (直接用北京时间显示)
        # IB 的 exec_time 通常已经是 UTC，但有时需要特殊处理
        from datetime import timezone, timedelta

        beijing_tz = timezone(timedelta(hours=8))

        if exec_time:
            # 打印原始时间调试
            _debug(f"[FILL] raw exec_time={exec_time}, repr={repr(exec_time)}")

            # 直接用当前北京时间（因为 exec_time 可能不准确）
            from datetime import datetime

            local_time = datetime.now(beijing_tz)
            time_str = local_time.strftime("%H:%M:%S")
        else:
            time_str = "--:--:--"

        # 统一格式：成交回报
        msg = f"""📈 **成交回报**
━━━━━━━━━━━━━━━
标的: {symbol} ({exchange})
方向: {action_cn}
数量: {qty} 手
价格: ${avg_price:,.2f}
时间: {time_str}
订单ID: {order_id}"""

        if commission != 0:
            msg += f"\n手续费: ${abs(commission):,.2f}"
        if realized_pnl != 0:
            pnl_emoji = "💰" if realized_pnl > 0 else "📉"
            msg += f"\n{pnl_emoji} 盈亏: ${realized_pnl:,.2f}"

        _debug(f"[FILL] {msg}")
        send_feishu(msg, FEISHU_CONVERSATION_ID)
    except Exception as e:
        _debug(f"[FILL] callback error: {e}")


def _register_fill_callback():
    """注册 execDetails 回调到 IB 实例"""
    try:
        ib = get_ib_connection()
        ib.execDetailsEvent.clear()  # 清除旧回调
        ib.execDetailsEvent += _on_exec_details
        _debug("[IB] execDetails callback registered")
        print(f"[IB] execDetails callback registered", flush=True)
    except Exception as e:
        _debug(f"[IB] execDetails register failed: {e}")


# 加载主配置
load_config()

# ============ 启动时预初始化 IB 连接 ============
# 必须在 app.run() 前建立，否则第一个请求会卡在 connect(timeout=10) 里
_ib_init_done = False


def _init_ib():
    global _ib_init_done
    if _ib_init_done:
        return
    try:
        ib = get_ib_connection()
        print(f"[IB] pre-connect: {ib}, connected={ib.isConnected()}")
        # 注册 execDetails 成交回调
        _register_fill_callback()
    except Exception as e:
        print(f"[IB] pre-connect failed (will retry on request): {e}")
    _ib_init_done = True


# 详细调试日志文件（写入 webhook_out.log）
_DEBUG_LOG = os.path.join(os.path.dirname(__file__), "webhook_out.log")


def _debug(msg):
    try:
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            import datetime

            f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}\n")
        print(msg, flush=True)
    except Exception:
        pass  # 忽略打印错误


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)


def load_feishu_config():
    """从 settings.yaml 加载飞书配置"""
    from config import (
        get_feishu_app_id,
        get_feishu_app_secret,
        get_feishu_chat_id,
        load_config,
        get,
    )

    load_config()
    return {
        "app_id": get_feishu_app_id(),
        "app_secret": get_feishu_app_secret(),
        "chat_id": get_feishu_chat_id(),
        "api_endpoint": get(
            "feishu.api_endpoint", "https://open.feishu.cn/open-apis/im/v1/messages"
        ),
        "auth_endpoint": get(
            "feishu.auth_endpoint",
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        ),
        "timeout": get("feishu.timeout", 30),
    }


feishu_config = load_feishu_config()
FEISHU_APP_ID = feishu_config.get("app_id", "")
FEISHU_APP_SECRET = feishu_config.get("app_secret", "")
FEISHU_CONVERSATION_ID = feishu_config.get("chat_id", "")

# 仅查询模式
QUERY_ONLY = is_query_only()

_token_cache = {"token": None, "expire": 0}

# TV Scheduler
import threading
import schedule
import atexit

_tv_scheduler_running = False
_tv_scheduler_thread = None


def _run_tv_scheduler():
    """TV定时调度器线程"""
    import schedule

    def job():
        logger.info("[TV-SCHEDULER] 定时执行 TV 分析...")
        try:
            result = run_tv_cross_timeframe_analysis()
            logger.info(f"[TV-SCHEDULER] 结果: {result[:100] if result else 'None'}...")
        except Exception as e:
            logger.error(f"[TV-SCHEDULER] 错误: {e}")

    # 每15分钟执行
    schedule.every(15).minutes.do(job)

    while _tv_scheduler_running:
        schedule.run_pending()
        time.sleep(10)


def start_tv_scheduler():
    """启动 TV 定时调度器"""
    global _tv_scheduler_running, _tv_scheduler_thread

    if _tv_scheduler_running:
        return "TV 调度器已在运行中"

    _tv_scheduler_running = True
    _tv_scheduler_thread = threading.Thread(target=_run_tv_scheduler, daemon=True)
    _tv_scheduler_thread.start()

    # 注册退出时停止
    atexit.register(stop_tv_scheduler)

    return "🚀 TV 调度器已启动 (每15分钟执行)"


def stop_tv_scheduler():
    """停止 TV 定时调度器"""
    global _tv_scheduler_running
    _tv_scheduler_running = False
    return "🛑 TV 调度器已停止"


def get_tv_scheduler_status():
    """获取 TV 调度器状态"""
    if _tv_scheduler_running:
        return "✅ TV 调度器运行中 (每15分钟)"
    return "🔴 TV 调度器未运行"


def get_python_cmd():
    """获取 Python 命令（支持虚拟环境和 Windows）"""
    import sys

    try:
        from config.env_config import get_python_path

        return get_python_path()
    except ImportError:
        # Windows 使用 "python"，Unix 使用 "python3"
        return "python" if sys.platform == "win32" else "python3"


def get_monitor_status():
    """获取监控状态（快速版 - 使用多标缓存）"""
    import yaml

    # z120 已废弃，z120_status 固定返回已停止
    z120_status = "已停止"

    pairs_path = Path(PROJECT_ROOT) / "z120_monitor" / "config" / "pairs.yaml"
    try:
        with open(pairs_path) as f:
            config = yaml.safe_load(f)
            enabled_pairs = [
                p["name"] for p in config.get("pairs", []) if p.get("enabled", False)
            ]
    except:
        enabled_pairs = ["MNQ_MYM"]

    mode = "🔒 仅查询模式" if QUERY_ONLY else "✅ 交易模式"

    status = f"""**📊 Z120 监控状态**

**监控进程:** {z120_status}

**模式:** {mode}

**启用的交易对:**"""
    for pair in enabled_pairs:
        status += f"\n  • {pair}"

    # 快速获取 Z120（从缓存，不调用 IBKR）
    try:
        sys.path.insert(0, PROJECT_ROOT)
        from z120_monitor.z120_cache import format_status_text, get_all_status

        all_data = get_all_status()
        if all_data:
            status += f"\n\n**当前状态:**\n{format_status_text()}"
        else:
            status += "\n\n**当前状态:** 暂无数据"
            status += "\n等待监控任务刷新..."
    except Exception as e:
        status += f"\n\n**当前状态:** 暂无数据 ({e})"

    return status


def get_tenant_token():
    """获取 tenant_access_token"""
    global _token_cache

    if _token_cache["token"] and time.time() < _token_cache["expire"]:
        return _token_cache["token"]

    url = feishu_config.get(
        "auth_endpoint",
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    )
    headers = {"Content-Type": "application/json; charset=utf-8"}
    payload = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        result = resp.json()
        if result.get("code") == 0:
            _token_cache["token"] = result["tenant_access_token"]
            _token_cache["expire"] = time.time() + result.get("expire", 7200) - 60
            return _token_cache["token"]
        else:
            print(f"获取 token 失败: {result}")
            return None
    except Exception as e:
        print(f"获取 token 错误: {e}")
        return None


def send_feishu(text, receive_id=None):
    """发送消息到飞书"""
    _debug(f"[FEISHU] send_feishu called: text={text[:50]}..., receive_id={receive_id}")
    try:
        token = get_tenant_token()
        _debug(f"[FEISHU] Token result: {token}")
        if not token:
            print("[FEISHU] Error: No token available")
            return (False, "No token")

        target_id = receive_id or FEISHU_CONVERSATION_ID
        _debug(f"[FEISHU] target_id: {target_id}")
        if not target_id:
            print("[FEISHU] Error: No target_id available")
            return (False, "No target_id")

        url = feishu_config.get(
            "api_endpoint", "https://open.feishu.cn/open-apis/im/v1/messages"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        params = {"receive_id_type": "chat_id"}
        message = {
            "receive_id": target_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        }

        resp = requests.post(
            url, params=params, json=message, headers=headers, timeout=10
        )
        _debug(f"[FEISHU] Response: {resp.status_code}")
        if resp.status_code == 200:
            return (True, resp.text)
        else:
            return (False, f"Status {resp.status_code}: {resp.text}")
    except Exception as e:
        import traceback

        _debug(f"[FEISHU] Exception: {e}")
        traceback.print_exc()
        return (False, str(e))


def execute_command(cmd):
    """执行命令并返回结果（Windows UTF-8 兼容）"""
    try:
        import sys

        # Windows 需要特殊处理编码
        if sys.platform == "win32":
            import subprocess

            result = subprocess.run(
                cmd, shell=True, capture_output=True, timeout=30, cwd=get_project_root()
            )
            # 手动解码，避免 GBK 错误
            stdout = (
                result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
            )
            stderr = (
                result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            )
            return stdout + stderr
        else:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=get_project_root(),
            )
            return result.stdout + result.stderr
    except Exception as e:
        return str(e)


def _get_ib():
    """获取 IB 连接，未连接时返回 None"""
    ib = get_ib_connection()
    if ib is None or not ib.isConnected():
        return None
    return ib


def _run_ib(fn, timeout=15.0):
    """在 IB 线程中执行函数（通过 run_sync 队列）"""
    manager = get_ib_manager()
    return manager.run_sync(fn, timeout=timeout)


def get_positions_formatted():
    """获取格式化持仓"""
    try:
        ib = _get_ib()
        if ib is None:
            return "❌ IB 未连接"
        # positions 需要通过 run_sync 在 IB 线程执行
        positions = _run_ib(lambda: ib.positions(), timeout=15)
        if not positions:
            return "📊 当前无持仓"
        lines = ["**📊 当前持仓**\n"]
        for pos in positions:
            symbol = pos.contract.symbol
            sec_type = pos.contract.secType
            position = pos.position
            avg_cost = pos.avgCost
            if position == 0:
                continue
            pos_str = (
                f"{position:+.0f}"
                if position != int(position)
                else f"{int(position):+}"
            )
            cost_str = f"{avg_cost:.2f}" if avg_cost else "N/A"
            lines.append(f"• {symbol} ({sec_type}): {pos_str} @ {cost_str}")
        if len(lines) == 1:
            return "📊 当前无持仓"
        return "\n".join(lines)
    except Exception as e:
        return f"❌ 获取持仓失败: {e}"


def get_account_summary_formatted():
    """获取格式化账户摘要（通过 run_sync 在 IB 线程执行）"""
    try:
        ib = _get_ib()
        if ib is None:
            return "❌ IB 未连接"
        summary = _run_ib(lambda: ib.accountSummary(), timeout=15)
        if not summary:
            return "📊 无账户数据"
        key_tags = {
            "NetLiquidation": "净值",
            "UnrealizedPnL": "未实现盈亏",
            "RealizedPnL": "已实现盈亏",
            "AvailableFunds": "可用资金",
            "BuyingPower": "购买力",
            "TotalCashValue": "现金",
            "GrossPositionValue": "持仓市值",
            "MaintMarginReq": "维持保证金",
        }
        lines = ["**💰 账户摘要**\n"]
        tag_map = {}
        for item in summary:
            tag_map[item.tag] = item
        for tag, label in key_tags.items():
            if tag in tag_map:
                val = tag_map[tag].value
                currency = tag_map[tag].currency
                try:
                    num = float(val)
                    lines.append(f"• {label}: {num:,.2f} {currency}")
                except (ValueError, TypeError):
                    lines.append(f"• {label}: {val} {currency}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ 获取账户摘要失败: {e}"


def get_orders_formatted():
    """获取格式化订单列表（通过 run_sync 在 IB 线程执行）"""
    try:
        ib = _get_ib()
        if ib is None:
            return "❌ IB 未连接"
        trades = _run_ib(lambda: ib.trades(), timeout=10)
        if not trades:
            return "📋 当前无订单"
        pending, filled, cancelled, inactive = [], [], [], []
        for trade in trades:
            os = trade.orderStatus
            c = trade.contract
            order_info = {
                "orderId": trade.order.orderId,
                "symbol": c.localSymbol
                if hasattr(c, "localSymbol") and c.localSymbol
                else c.symbol,
                "action": trade.order.action,
                "quantity": trade.order.totalQuantity,
                "filled": os.filled,
                "remaining": os.remaining,
                "avgFillPrice": os.avgFillPrice,
                "status": os.status,
            }
            if os.status in {
                "Submitted",
                "PendingSubmit",
                "PreSubmitted",
                "Active",
                "ApiPending",
            }:
                pending.append(order_info)
            elif os.status in {"Filled", "ApiTraded"}:
                filled.append(order_info)
            elif os.status in {"Cancelled", "ApiCancelled"}:
                cancelled.append(order_info)
            else:
                inactive.append(order_info)
        lines = ["**📋 订单状态**\n"]
        if pending:
            lines.append(f"🔄 待成交 ({len(pending)} 单)")
            for o in pending:
                lines.append(
                    f"  • {o['symbol']}: {o['action']} {o['filled']:.0f}/{o['quantity']} ({o['status']})"
                )
        if filled:
            lines.append(f"\n✅ 已成交 ({len(filled)} 单)")
            for o in filled:
                lines.append(
                    f"  • {o['symbol']}: {o['action']} {o['filled']:.0f}/{o['quantity']} @ ${o['avgFillPrice']:.2f}"
                )
        if cancelled:
            lines.append(f"\n❌ 已取消 ({len(cancelled)} 单)")
            for o in cancelled:
                lines.append(f"  • {o['symbol']}: {o['action']} {o['quantity']}")
        if inactive:
            lines.append(f"\n⏸ 未激活 ({len(inactive)} 单)")
            for o in inactive:
                lines.append(
                    f"  • {o['symbol']}: {o['action']} {o['quantity']} ({o['status']})"
                )
        if len(lines) == 1:
            return "📋 当前无订单"
        return "\n".join(lines)
    except Exception as e:
        return f"❌ 获取订单失败: {e}"


def get_fills_formatted():
    """获取格式化成交记录（通过 run_sync 在 IB 线程执行）"""
    try:
        ib = _get_ib()
        if ib is None:
            return "❌ IB 未连接"
        fills = _run_ib(lambda: ib.fills(), timeout=10)
        if not fills:
            return "📊 今日无成交"
        lines = ["**📊 成交记录**\n"]
        for fill in fills:
            symbol = fill.contract.symbol
            action = fill.execution.side
            qty = fill.execution.cumQty
            price = fill.execution.price
            commission = (
                fill.commissionReport.commission if fill.commissionReport else 0
            )
            exec_time = (
                fill.execution.time.strftime("%H:%M:%S") if fill.execution.time else ""
            )
            lines.append(
                f"• {symbol}: {action} {qty} @ ${price:.2f} (手续费 ${commission:.2f}) {exec_time}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"❌ 获取成交记录失败: {e}"


def get_help_text():
    """获取帮助文本"""
    return """**📊 交易系统命令列表**

**查询类:**
• /持仓 - 查询当前持仓
• /账户 - 查询账户摘要
• /订单 - 查询活动订单
• /成交 - 查询成交记录

**监控类:**
• /status - 查看 TV 调度器状态
• /refresh - 刷新监控数据
• /start - 启动 TV 调度器 (每15分钟)
• /stop - 停止 TV 调度器
• /log - 查看 TV 调度器状态

**模式切换:**
• /交易模式 - 切换到交易模式
• /查询模式 - 切换到仅查询模式

**分析类:**
• /多周期分析 - 执行多周期共振分析（默认DOGEUSDT）
• /多周期分析 BTCUSDT - 指定品种

**帮助:**
• /help - 显示此帮助"""


def trigger_refresh():
    """触发监控刷新，完成后主动发送飞书反馈"""
    import threading
    import subprocess

    def do_refresh():
        try:
            python_cmd = get_python_cmd()
            refresh_script = str(Path(__file__).parent / "refresh_and_notify.py")
            result = subprocess.run(
                [
                    python_cmd,
                    refresh_script,
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            print(f"刷新结果: {result.stdout}{result.stderr}")
        except Exception as e:
            print(f"刷新出错: {e}")

    threading.Thread(target=do_refresh, daemon=True).start()
    return "🔄 监控刷新中，请稍候..."


def run_multi_timeframe_analysis(symbol: str = "DOGE-USDT") -> str:
    """运行多周期共振分析"""
    try:
        sys.path.insert(0, PROJECT_ROOT)
        from quant_core.sources import create_datasource

        _debug(f"[MTF] Starting analysis for {symbol}")

        okx = create_datasource("okx")

        timeframes = [
            ("1h", "1H", 50),
            ("4h", "4H", 50),
            ("1D", "1D", 30),
            ("1W", "1W", 20),
        ]

        results = []
        for tf_name, tf_bar, tf_num in timeframes:
            try:
                _debug(f"[MTF] Fetching {tf_name}...")
                bars = okx.get_history(symbol, bar_size=tf_bar, num=tf_num)

                if not bars:
                    results.append(f"  {tf_name}: 无数据")
                    continue

                closes = [b.close for b in bars]
                current_price = closes[-1]

                rsi = calculate_rsi(closes)
                ma20 = calculate_ma(closes, 20) if len(closes) >= 20 else None
                ma50 = calculate_ma(closes, 50) if len(closes) >= 50 else None

                if ma20 and current_price > ma20:
                    ma_signal = "BUY"
                elif ma20 and current_price < ma20:
                    ma_signal = "SELL"
                else:
                    ma_signal = "NEUTRAL"

                if rsi < 30:
                    osc_signal = "BUY"
                elif rsi > 70:
                    osc_signal = "SELL"
                else:
                    osc_signal = "NEUTRAL"

                results.append(
                    f"  {tf_name}: RSI={rsi:.1f} MA={ma_signal} OSC={osc_signal}"
                )
            except Exception as e:
                _debug(f"[MTF] Error {tf_name}: {e}")
                results.append(f"  {tf_name}: 获取失败 - {str(e)[:30]}")

        if not results:
            return f"无法获取 {symbol} 的数据，请检查品种代码"

        buy_count = sum(1 for r in results if "BUY" in r)
        sell_count = sum(1 for r in results if "SELL" in r)
        total = len(timeframes)
        resonance = int((max(buy_count, sell_count) / total) * 100) if total > 0 else 0

        level = (
            "强共振"
            if buy_count > sell_count and buy_count >= 3
            else "强分歧"
            if sell_count > buy_count and sell_count >= 3
            else "分歧"
        )

        return f"""**{symbol} 多周期共振分析**

{chr(10).join(results)}

**共振评分:** {resonance}/100 ({level})"""
    except Exception as e:
        _debug(f"[MTF] Final error: {e}")
        return f"分析失败: {str(e)}"


def calculate_rsi(prices: list, period: int = 14) -> float:
    """计算 RSI"""
    if len(prices) < period + 1:
        return 50.0

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_ma(prices: list, period: int) -> float:
    """计算移动平均"""
    if len(prices) < period:
        return 0.0
    return sum(prices[-period:]) / period


def _parse_tv_float(val, default=None):
    """解析 TradingView 格式化的数字（如 \"1.29\" 或 \"−0.52\"）"""
    if val is None:
        return default
    try:
        return float(str(val).replace("−", "-").replace("−", "-"))
    except:
        return default


def _get_zscore_color(z):
    """根据 Z-Score 值返回颜色标注"""
    if z is None:
        return ""
    if abs(z) >= 3:
        return "🔴"
    elif abs(z) >= 2:
        return "🟡"
    return ""


def _get_corr_color(corr):
    """根据相关性值返回颜色标注"""
    if corr is None:
        return ""
    if corr < -0.5:
        return "🔴"
    elif corr < 0:
        return "🟡"
    return ""


def _extract_tv_indicators(studies):
    """从 TradingView studies 中提取指标值"""
    result = {}
    for study in studies:
        name = study.get("name", "")
        if name == "Overlay":
            continue
        values = study.get("values", {})
        for k, v in values.items():
            result[k] = v
    return result


def _format_tv_symbol_report(symbol, data_map):
    """格式化单个品种的 TV 跨周期报告

    Args:
        symbol: 品种代码
        data_map: dict，key 为 timeframe (30m/5m/1m)，value 为包含 quote 和 indicators 的 dict

    Returns:
        格式化报告字符串
    """
    # 获取价格（优先使用 M30）
    price = (
        data_map.get("30m", {}).get("quote", {}).get("close")
        or data_map.get("5m", {}).get("quote", {}).get("close")
        or data_map.get("1m", {}).get("quote", {}).get("close")
    )
    price_str = f"{price:.4f}" if price else "N/A"

    lines = [f"━━━ {symbol} ━━━", f"💰 价格: {price_str}", ""]

    # 按时间周期显示数据
    for tf in ["15m", "5m", "1m"]:
        tf_data = data_map.get(tf, {})
        indicators = tf_data.get("indicators", {})

        zscore = _parse_tv_float(indicators.get("Z-Score"))
        long_corr = _parse_tv_float(indicators.get("长期相关性"))
        short_corr = _parse_tv_float(indicators.get("短期相关性"))

        z_color = _get_zscore_color(zscore)
        lc_color = _get_corr_color(long_corr)
        sc_color = _get_corr_color(short_corr)

        z_str = f"{zscore:.2f}" if zscore is not None else "N/A"
        lc_str = f"{long_corr:.2f}" if long_corr is not None else "N/A"
        sc_str = f"{short_corr:.2f}" if short_corr is not None else "N/A"

        z_display = f"{z_color}{z_str}" if z_color else z_str
        lc_display = f"{lc_color}{lc_str}" if lc_color else lc_str
        sc_display = f"{sc_color}{sc_str}" if sc_color else sc_str

        tf_label = {"15m": "M15", "5m": "M5", "1m": "M1"}.get(tf, tf)
        lines.append(
            f"📊 {tf_label} | Z: {z_display} | 长相关: {lc_display} | 短相关: {sc_display}"
        )

    return "\n".join(lines)


def run_tv_cross_timeframe_analysis():
    """运行 TradingView 跨周期分析（从 CDP 读取）"""
    try:
        # 添加 kanban 路径以复用 tv.py
        kanban_path = Path(PROJECT_ROOT) / "kanban"
        if str(kanban_path) not in sys.path:
            sys.path.insert(0, str(kanban_path))

        from src.tv import get_all_tv_indicators

        # 获取三个时间周期的数据
        data_m15 = get_all_tv_indicators(timeframe="15m")
        data_m5 = get_all_tv_indicators(timeframe="5m")
        data_m1 = get_all_tv_indicators(timeframe="1m")

        # 检查是否有数据
        if (
            not data_m15.get("tabs")
            and not data_m5.get("tabs")
            and not data_m1.get("tabs")
        ):
            return "⚠️ 未获取到任何图表数据，请检查 TradingView CDP 连接"

        # 按品种聚合数据
        symbol_map = {}

        for data, tf_key in [(data_m15, "15m"), (data_m5, "5m"), (data_m1, "1m")]:
            for tab in data.get("tabs", []):
                symbol = tab.get("symbol", "N/A")
                if symbol not in symbol_map:
                    symbol_map[symbol] = {
                        "description": tab.get("description", ""),
                    }

                indicators = _extract_tv_indicators(tab.get("studies", []))
                symbol_map[symbol][tf_key] = {
                    "quote": tab.get("quote", {}),
                    "indicators": indicators,
                }

        # 格式化每个品种的报告
        reports = []
        for symbol, data in symbol_map.items():
            report = _format_tv_symbol_report(symbol, data)
            reports.append(report)

        # 组合消息（限制最多10个品种）
        if len(reports) > 10:
            reports = reports[:10]
            footer = f"\n\n（共 {len(symbol_map)} 个品种，显示前10个）"
        else:
            footer = ""

        message = "\n\n".join(reports) + footer

        # 发送飞书消息
        success, resp = send_feishu(message)
        if success:
            return (
                message
                if len(message) < 2000
                else message[:2000] + "\n\n（报告已发送至飞书）"
            )
        else:
            return f"❌ 发送失败: {resp}"

    except Exception as e:
        import traceback

        traceback.print_exc()
        return f"❌ TradingView 数据不可用: {str(e)}"


COMMANDS = {
    # 监控类
    "status": lambda: get_tv_scheduler_status(),
    "refresh": trigger_refresh,
    "start": lambda: start_tv_scheduler(),
    "stop": lambda: stop_tv_scheduler(),
    "log": lambda: get_tv_scheduler_status(),
    # 模式切换
    "交易模式": lambda: (
        set_query_only(False) or globals().__setitem__("QUERY_ONLY", False),
        "✅ **已切换到交易模式**\n\n现在允许查询和下单操作。",
    )[1],
    "查询模式": lambda: (
        set_query_only(True) or globals().__setitem__("QUERY_ONLY", True),
        "🔒 **已切换到仅查询模式**\n\n现在仅允许查询操作，不允许下单。",
    )[1],
    # 查询类（内联，复用 webhook IB 连接）
    "持仓": lambda: get_positions_formatted(),
    "账户": lambda: get_account_summary_formatted(),
    "订单": lambda: get_orders_formatted(),
    "成交": lambda: get_fills_formatted(),
    "help": lambda: get_help_text(),
    # 多周期分析
    "多周期分析": lambda: run_multi_timeframe_analysis(),
    # TradingView 跨周期分析
    "tv": lambda: run_tv_cross_timeframe_analysis(),
}


def _submit_okx_order(
    symbol: str,
    action: str,
    quantity: float,
    usd_amount: float = None,
    leverage: int = None,
    margin_mode: str = "cash",
    order_type: str = "market",
):
    okx_trader = None
    try:
        from okx_client.okx_trader import OKXTrader

        okx_trader = OKXTrader()
    except Exception as e:
        return {"error": f"OKX 客户端初始化失败: {e}"}

    try:
        if usd_amount and leverage:
            quantity = okx_trader.calc_quantity_from_usd(symbol, usd_amount, leverage)
            okx_trader.set_leverage(symbol, str(leverage), margin_mode)

        side = "buy" if action == "BUY" else "sell"
        td_mode = (
            "cash"
            if margin_mode == "cash"
            else ("cross" if margin_mode == "cross" else "isolated")
        )

        # 现货 (cash) 不需要 posSide，只有合约/杠杆交易需要
        is_contract = td_mode in ("cross", "isolated")
        pos_side = ("long" if action == "BUY" else "short") if is_contract else None

        order_params = {
            "inst_id": symbol,
            "side": side,
            "sz": str(quantity),
            "ord_type": order_type.lower(),
            "tdMode": td_mode,
        }
        if pos_side:
            order_params["posSide"] = pos_side

        result = okx_trader.place_order(**order_params)
        return result
    except Exception as e:
        return {"error": f"OKX 下单失败: {e}"}


def _submit_pair_trade(
    symbols: list,
    actions: list = None,
    usd_amount: float = None,
    leverage: int = 3,
    margin_mode: str = "cash",
    order_type: str = "market",
):
    """同时下单多个标的（配对交易）"""
    from concurrent.futures import ThreadPoolExecutor

    # 如果没有传入 actions，默认全部用 BUY
    if actions is None:
        actions = ["BUY"] * len(symbols)

    results = []
    errors = []

    def _trade_one(symbol, action):
        try:
            result = _submit_okx_order(
                symbol=symbol,
                action=action,
                quantity=0,  # 通过 usd_amount 计算
                usd_amount=usd_amount,
                leverage=leverage,
                margin_mode=margin_mode,
                order_type=order_type,
            )
            return {symbol: result}
        except Exception as e:
            return {symbol: {"error": str(e)}}

    # 并发执行所有订单
    with ThreadPoolExecutor(max_workers=len(symbols)) as executor:
        futures = [
            executor.submit(_trade_one, sym, act) for sym, act in zip(symbols, actions)
        ]
        for future in futures:
            result = future.result()
            results.append(result)

    return {"pair_trade": results}


@app.route("/tv-webhook", methods=["POST"])
def tv_webhook():
    try:
        data = request.json
        print(f"收到Webhook数据:")
        print(json.dumps(data, indent=2, ensure_ascii=False))

        symbol = data.get("symbol", "").upper()
        action = data.get("action", "").upper()

        if symbol and action in ("BUY", "SELL", "CLOSE"):
            quantity = data.get("quantity", 1)
            sec_type = data.get("sec_type", "FUT")
            exchange = data.get("exchange", "").upper()
            usd_amount = data.get("usd_amount")
            leverage = data.get("leverage")
            # 自动识别现货/合约：SWAP/PERP 为合约，其他为现货
            requested_margin = data.get("margin_mode", None)
            if requested_margin:
                margin_mode = requested_margin
            else:
                # 根据交易对自动判断
                symbol_upper = symbol.upper()
                is_contract = any(
                    x in symbol_upper for x in ["-SWAP", "-PERP", "-FUTURES", "-USD-"]
                )
                margin_mode = "cross" if is_contract else "cash"
            order_type = data.get(
                "order_type", "market" if exchange == "OKX" else "MKT"
            )

            # 支持配对交易：symbols 数组
            symbols = data.get("symbols", [])
            # 支持 actions 数组：每个标的独立方向
            actions = data.get("actions", [action] * len(symbols) if symbols else [])

            if exchange == "OKX":
                from datetime import datetime

                time_str = datetime.now().strftime("%H:%M:%S")

                # 配对交易模式
                if symbols and len(symbols) > 1:
                    # 构建方向描述
                    dir_parts = []
                    for sym, act in zip(symbols, actions):
                        act_cn = "买入" if act == "BUY" else "卖出"
                        dir_parts.append(f"{sym}: {act_cn}")
                    dir_str = " | ".join(dir_parts)
                    leverage_info = (
                        f" {leverage if leverage else 3}x杠杆" if leverage else "3x杠杆"
                    )
                    submit_msg = f"⏳ OKX 配对交易提交中\n{dir_str}\n杠杆: {leverage_info}\n模式: {margin_mode}\n时间: {time_str}"
                    send_feishu(submit_msg)

                    result = _submit_pair_trade(
                        symbols=symbols,
                        actions=actions,
                        usd_amount=usd_amount,
                        leverage=leverage if leverage else 3,
                        margin_mode=margin_mode,
                        order_type=order_type,
                    )

                    output_str = str(result)[:500] if result else ""
                    msg = f"🤖 OKX 配对交易信号\n{dir_str}\n保证金: {usd_amount} USD\n\n结果: {output_str}"
                    send_feishu(msg)
                    return jsonify({"status": "ok", "order": result})

                # 单标的下单
                time_str = datetime.now().strftime("%H:%M:%S")
                action_cn = "买入" if action == "BUY" else "卖出"
                leverage_info = f" {leverage}x杠杆" if leverage else ""
                submit_msg = f"⏳ OKX 订单提交中\n标的: {symbol}\n方向: {action_cn}{leverage_info}\n模式: {margin_mode}\n时间: {time_str}"
                send_feishu(submit_msg)

                result = _submit_okx_order(
                    symbol=symbol,
                    action=action,
                    quantity=quantity,
                    usd_amount=usd_amount,
                    leverage=leverage,
                    margin_mode=margin_mode,
                    order_type=order_type,
                )

                output_str = str(result)[:500] if result else ""
                msg = (
                    f"🤖 OKX 交易信号\n标的: {symbol}\n操作: {action}\n杠杆: {leverage}x\n保证金: {usd_amount} USD\n数量: {quantity}\n\n结果: {output_str}"
                    if leverage and usd_amount
                    else f"🤖 OKX 交易信号\n标的: {symbol}\n操作: {action}\n数量: {quantity}\n\n结果: {output_str}"
                )
                send_feishu(msg)
                return jsonify({"status": "ok", "order": result})
            else:
                try:
                    from orders.exchange_mapper import get_exchange_for_symbol

                    exchange = (
                        get_exchange_for_symbol(symbol, "FUT")
                        if sec_type == "FUT"
                        else ""
                    )
                except Exception:
                    exchange = ""

                try:
                    from client.ib_connection import get_ib_connection
                    from orders.place_order_func import place_order

                    ib = get_ib_connection()
                    if ib is None or not ib.isConnected():
                        output = "IB 连接失败或已断开"
                    else:
                        from datetime import datetime

                        time_str = datetime.now().strftime("%H:%M:%S")
                        action_cn = (
                            "买入"
                            if action == "BUY"
                            else "卖出"
                            if action == "SELL"
                            else "平仓"
                        )
                        submit_msg = f"""⏳ **订单提交中**
━━━━━━━━━━━━━━━━
标的: {symbol} ({exchange})
方向: {action_cn}
数量: {quantity} 手
时间: {time_str}"""
                        _ = send_feishu(submit_msg)

                        future = _submit_order_in_background(
                            ib,
                            symbol,
                            action,
                            quantity,
                            exchange=exchange,
                            sec_type=sec_type,
                            close_position=(action == "CLOSE"),
                            outside_rth=True,
                        )
                        output = {
                            "status": "Submitted",
                            "message": f"后台已提交下单: {symbol} {action} {quantity}",
                        }
                except Exception as e:
                    output = f"错误: {e}"

                output_str = str(output)[:500] if output else ""
                msg = f"🤖 Webhook 交易信号\n\n标的: {symbol}\n操作: {action}\n数量: {quantity}\n订单类型: {order_type}\n\n结果:\n{output_str}"
                send_feishu(msg)

                order_payload = (
                    output
                    if isinstance(output, dict)
                    else {"status": "Unknown", "order": str(output)}
                )
                return jsonify({"status": "ok", "order": order_payload})
        else:
            # 打印收到的原始数据用于调试
            print(
                f"[TV-WEBHOOK] 收到数据: {json.dumps(data, ensure_ascii=False)[:500]}"
            )

            title = data.get("title", "Webhook 警报")
            description = data.get("description", "")
            # 也检查其他常见字段
            ticker = data.get("ticker", "")
            reason = data.get("reason", "")
            message = data.get("message", "")

            # 过滤掉 Z120 "无法获取当前价差" 警报（这类警报由 TradingView 频繁推送，无需转发到飞书）
            filter_text = "无法获取当前价差"
            if filter_text in (title + description + ticker + reason + message):
                print(
                    f"[TV-WEBHOOK] 过滤掉 Z120 警报: title={title}, ticker={ticker}, reason={reason}"
                )
                return jsonify({"status": "ok", "filtered": True})

            success, result = send_feishu(f"{title}\n\n{description}")
            return jsonify({"status": "ok" if success else "error", "result": result})

    except Exception as e:
        print(f"Webhook错误: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/feishu-webhook", methods=["GET", "POST"])
def feishu_webhook():
    """接收飞书消息并执行命令"""
    logger.info(f"[FEISHU] Method: {request.method}")
    logger.info(f"[FEISHU] Headers: {dict(request.headers)}")
    logger.info(f"[FEISHU] Data: {request.data}")

    if request.method == "GET":
        challenge = request.args.get("challenge", request.args.get("chu") or "")
        logger.info(f"[FEISHU] GET challenge: {challenge}")
        return jsonify({"challenge": challenge})

    try:
        order_result = None  # 捕获订单结果用于 HTTP 响应
        event = request.json

        # ========== 请求格式归一化 ==========
        # 支持简化测试格式: {"message": {"content": "买入1手GC"}}
        # 自动转换为 Feishu 事件格式
        if event.get("message") and not event.get("header"):
            msg_data = event["message"]
            raw = msg_data.get("content", "")
            # content 可能是纯文本或 JSON 字符串
            try:
                json.loads(raw)
            except (TypeError, ValueError):
                raw = json.dumps({"text": raw})
            from warnings import simplefilter

            # 归一化为 Schema 2.0 格式
            event = {
                "header": {"event_type": "im.message.receive_v1"},
                "event": {
                    "message": {
                        "content": raw,
                        "message_id": msg_data.get("message_id", ""),
                        "chat_id": msg_data.get("chat_id", FEISHU_CONVERSATION_ID),
                    }
                },
            }
        # ====================================

        logger.info(f"[FEISHU] Event: {json.dumps(event, ensure_ascii=False)}")

        if event.get("type") == "url_verification" or event.get("challenge"):
            challenge = event.get("challenge", "")
            logger.info(f"[FEISHU] URL verification challenge: {challenge}")
            return jsonify({"challenge": challenge})

        msg_type = event.get("header", {}).get("event_type", "")
        logger.info(f"[FEISHU] Event type: {msg_type}")
        logger.info(f"[FEISHU] Full event: {json.dumps(event, ensure_ascii=False)}")

        if msg_type == "im.message.receive_v1":
            # Schema 2.0: message is in event.message.content
            # Schema 1.0: message is in body.message.content
            event_data = event.get("event", event.get("body", {}))
            message = event_data.get("message", {})

            # 去重：检查 message_id
            msg_id = message.get("message_id", "")
            if msg_id:
                cache_key = f"feishu_msg_{msg_id}"
                import time

                current_time = int(time.time())
                if not hasattr(feishu_webhook, "_msg_cache"):
                    feishu_webhook._msg_cache = {}
                # 5秒内重复消息跳过
                if cache_key in feishu_webhook._msg_cache:
                    if current_time - feishu_webhook._msg_cache[cache_key] < 5:
                        logger.info(f"[FEISHU] Duplicate message: {msg_id}, skip")
                        return jsonify({"status": "ok", "order": order_result}), 200
                feishu_webhook._msg_cache[cache_key] = current_time

            logger.info(f"[FEISHU] Message: {json.dumps(message, ensure_ascii=False)}")

            content_raw = message.get("content", "{}")
            logger.info(f"[FEISHU] Content raw: {content_raw}")

            try:
                content = json.loads(content_raw)
                text = content.get("text", "").strip()
            except Exception as parse_err:
                # 如果不是 JSON，尝试直接作为文本处理（兼容旧版或测试环境）
                logger.info(
                    f"[FEISHU] Content parse error: {parse_err}, treating as plain text"
                )
                text = content_raw.strip()
                if text.startswith("{") and text.endswith("}"):
                    # 看起来像 JSON 但解析失败，可能是被转义的
                    try:
                        text = json.loads(text).get("text", text)
                    except Exception:
                        pass

            logger.info(f"[FEISHU] Message text: '{text}'")

            # 获取 chat_id 用于回复
            chat_id = message.get("chat_id", FEISHU_CONVERSATION_ID)
            logger.info(f"[FEISHU] Will reply to: {chat_id}")

            # 检查是否以 / 开头（命令模式）
            if text.startswith("/"):
                cmd_name = text[1:].strip()
                _debug(f"[FEISHU] CMD: {cmd_name}")
                logger.info(f"[FEISHU] Command: {cmd_name}")

                # 分离命令和参数
                parts = cmd_name.split(None, 1)
                cmd_base = parts[0]
                cmd_args = parts[1] if len(parts) > 1 else ""

                # 尝试找到匹配的命令（忽略大小写）
                matched_cmd = None
                for cmd in COMMANDS:
                    if cmd.lower() == cmd_base.lower():
                        matched_cmd = cmd
                        break

                if matched_cmd:
                    logger.info(f"[FEISHU] matched_cmd={matched_cmd}")
                    # 支持带参数的命令
                    if matched_cmd == "多周期分析" and cmd_args:
                        logger.info(f"[FEISHU] 调用多周期分析 with args: {cmd_args}")
                        output = run_multi_timeframe_analysis(cmd_args.strip().upper())
                    elif matched_cmd == "多周期分析":
                        logger.info(f"[FEISHU] 调用多周期分析 default")
                        output = run_multi_timeframe_analysis()
                    else:
                        output = COMMANDS[matched_cmd]()
                    logger.info(f"[FEISHU] Command output: {output}")
                    success, resp = send_feishu(f"**{cmd_name}**\n\n{output}", chat_id)
                    logger.info(f"[FEISHU] Send result: {success}")
                else:
                    send_feishu(
                        f"未知命令: {cmd_name}\n\n发送 `/help` 查看可用命令", chat_id
                    )
            else:
                # 自然语言模式 - 先检查是否在命令中（忽略大小写）
                cmd_key = text.strip()
                cmd_key_lower = cmd_key.lower()

                # 尝试找到匹配的命令（忽略大小写）
                matched_cmd = None
                for cmd in COMMANDS:
                    if cmd.lower() == cmd_key_lower:
                        matched_cmd = cmd
                        break

                if matched_cmd:
                    logger.info(f"[FEISHU] Found command: {cmd_key} -> {matched_cmd}")
                    output = COMMANDS[matched_cmd]()
                    success, resp = send_feishu(f"**{cmd_key}**\n\n{output}", chat_id)
                else:
                    parsed = parse_trading_command(text)
                    action = parsed.get("action")
                    symbol = parsed.get("symbol")
                    quantity = parsed.get("quantity", 1)
                    sec_type = parsed.get("sec_type")  # 外汇为 CASH, 黄金为 CFD
                    parsed_exchange = parsed.get("exchange")  # 交易所
                    cfd_symbol = parsed.get("cfd_symbol")  # CFD 实际符号
                    cfd_conId = parsed.get("cfd_conId")  # CFD 合约ID

                    if quantity is None:
                        quantity = 1

                    if action in ("BUY", "SELL", "CLOSE"):
                        # ===== 订单级去重（60秒内相同订单，文件缓存支持多worker）=====
                        import time as _time, threading as _threading, json as _json

                        _DLOCK = _threading.Lock()
                        _DFILE = os.path.join(PROJECT_ROOT, ".order_dedup_cache.json")
                        _ACN = {"BUY": "买入", "SELL": "卖出", "CLOSE": "平仓"}.get(
                            action, action
                        )
                        _OK = f"{action}|{symbol}|{quantity}|{sec_type or ''}|{parsed_exchange or ''}"
                        _NOW = int(_time.time())
                        _ISDUP = False
                        with _DLOCK:
                            try:
                                _C = (
                                    _json.load(open(_DFILE, encoding="utf-8"))
                                    if os.path.exists(_DFILE)
                                    else {}
                                )
                            except Exception:
                                _C = {}
                            _C = {k: v for k, v in _C.items() if _NOW - v < 120}
                            if _OK in _C and _NOW - _C[_OK] < 60:
                                _ISDUP = True
                            else:
                                _C[_OK] = _NOW
                                try:
                                    _json.dump(_C, open(_DFILE, "w", encoding="utf-8"))
                                except:
                                    pass
                        if _ISDUP:
                            _sym_str = symbol if symbol else "N/A"
                            _MSG = (
                                "\u26a0\ufe0f **重复订单已拦截**（60秒内相同订单）\n标的: "
                                + _sym_str
                                + " | 方向: "
                                + _ACN
                                + " | 数量: "
                                + str(quantity)
                            )
                            logger.info("[FEISHU] Duplicate: " + _OK + ", skip")
                            send_feishu(_MSG, chat_id)
                            return jsonify(
                                {"status": "ok", "order": order_result or {}}
                            ), 200
                        # ================================================

                        try:
                            logger.info(
                                f"[FEISHU] NL parsed: action={action}, symbol={symbol}, qty={quantity}, sec_type={sec_type}"
                            )

                            # 复用 IB 连接，直接调用 place_order_func.place_order
                            # 添加事件循环，避免 ib_insync 内部错误
                            import asyncio
                            import sys
                            import traceback as tb_module

                            # 应用 nest_asyncio 允许嵌套事件循环（修复 ib_insync 在子线程中的问题）
                            try:
                                import nest_asyncio

                                nest_asyncio.apply()
                            except ImportError:
                                pass

                            from client.ib_connection import get_ib_connection
                            from orders.place_order_func import place_order
                            from orders.exchange_mapper import get_exchange_for_symbol

                            _debug(
                                f"[FEISHU] get_ib_connection() calling...",
                            )
                            ib = get_ib_connection()
                            _debug(
                                f"[FEISHU] get_ib_connection() returned ib={ib}, connected={ib.isConnected() if ib else None}",
                            )

                            if ib is None or not ib.isConnected():
                                error_msg = "IB 连接失败或已断开"
                                _debug(
                                    f"[FEISHU] {error_msg}",
                                )
                                send_feishu(
                                    f"❌ 下单失败: {error_msg}\n请检查 IB Gateway",
                                    chat_id,
                                )
                                order_result = {"error": error_msg}
                            else:
                                # 使用解析出的交易所，或根据品种类型推断
                                if parsed_exchange:
                                    exchange = parsed_exchange
                                elif sec_type:
                                    exchange = get_exchange_for_symbol(symbol, sec_type)
                                else:
                                    exchange = get_exchange_for_symbol(symbol, "FUT")
                                is_close = action == "CLOSE"

                                # CFD 使用实际符号
                                actual_symbol = cfd_symbol if cfd_symbol else symbol
                                actual_conId = cfd_conId if cfd_conId else None

                                _debug(
                                    f"[FEISHU] Calling place_order: symbol={actual_symbol}, action={action}, qty={quantity}, sec_type={sec_type}, exchange={exchange}, conId={actual_conId}, close_position={is_close}"
                                )

                                # 先发送订单提交通知（立即）
                                from datetime import datetime

                                time_str = datetime.now().strftime("%H:%M:%S")
                                action_cn = (
                                    "买入"
                                    if action == "BUY"
                                    else "卖出"
                                    if action == "SELL"
                                    else "平仓"
                                )
                                submit_msg = f"""⏳ **订单提交中**
━━━━━━━━━━━━━━━
标的: {symbol} ({exchange})
方向: {action_cn}
数量: {quantity} 手
时间: {time_str}"""
                                send_feishu(submit_msg, chat_id)

                                # 后台提交订单并等待结果
                                future = _submit_order_in_background(
                                    ib,
                                    actual_symbol,
                                    action,
                                    quantity,
                                    exchange=exchange,
                                    sec_type=sec_type,
                                    conId=actual_conId,
                                    close_position=is_close,
                                )
                                # 等待订单执行结果（同步等待后台线程完成）
                                order_result = future.result(timeout=60)
                                if order_result is None:
                                    order_result = {"error": "Order timed out"}
                        except Exception as e:
                            err_str = tb_module.format_exc()
                            _debug(
                                f"[FEISHU] IB/connect EXCEPTION: {type(e).__name__}: {e}\n{err_str}",
                            )
                            order_result = {"error": f"{type(e).__name__}: {e}"}
                    else:
                        send_feishu(get_help_text(), chat_id)

        return jsonify({"status": "ok", "order": order_result}), 200
    except Exception as e:
        logger.info(f"[FEISHU] Error: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/test-api", methods=["POST"])
def test_api():
    """测试API方式"""
    success, result = send_feishu("🧪 测试消息")
    return jsonify({"success": success, "result": result})


@app.route("/positions", methods=["GET"])
def get_positions_endpoint():
    """Get current positions"""
    try:
        from client.ib_connection import get_ib_manager

        manager = get_ib_manager()
        ib = manager.get_connection()
        positions = manager.run_sync(lambda: ib.positions(), timeout=10)
        result = []
        for p in positions:
            result.append(
                {
                    "symbol": p.contract.symbol,
                    "position": p.position,
                    "avgCost": p.avgCost,
                    "account": p.account,
                    "contract": str(p.contract),
                }
            )
        return jsonify({"positions": result, "count": len(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/orders", methods=["GET"])
def get_orders_endpoint():
    """Get open orders"""
    try:
        from client.ib_connection import get_ib_manager

        manager = get_ib_manager()
        ib = manager.get_connection()
        trades = manager.run_sync(lambda: ib.openTrades(), timeout=10)
        result = []
        for t in trades:
            result.append(
                {
                    "orderId": t.order.orderId,
                    "symbol": t.contract.symbol,
                    "action": t.order.action,
                    "quantity": t.order.totalQuantity,
                    "status": t.orderStatus.status,
                    "filled": t.orderStatus.filled,
                }
            )
        return jsonify({"orders": result, "count": len(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    config_status = {
        "app_id": bool(FEISHU_APP_ID),
        "conversation_id": bool(FEISHU_CONVERSATION_ID),
        "query_only": QUERY_ONLY,
    }
    return jsonify({"status": "ok", "config": config_status})


@app.route("/test-mtf", methods=["POST"])
def test_mtf():
    try:
        text = request.json.get("text", "/多周期分析")
        if text.startswith("/多周期分析"):
            cmd = text[1:].strip()
            if cmd == "多周期分析":
                symbol = "DOGE-USDT"
            else:
                symbol = cmd.strip().upper()
            result = run_multi_timeframe_analysis(symbol)
            return jsonify({"status": "ok", "result": result})
        return jsonify({"status": "error", "message": "invalid command"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# === Signal API endpoints ===
@app.route("/api/signals", methods=["POST"])
def api_submit_signal():
    """Agent 提交交易信号"""
    from notify.signal_handler import handle_submit_signal
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid JSON"}), 400
    result = handle_submit_signal(data)
    status_code = 201 if result.get("status") == "reviewed" else 200
    return jsonify(result), status_code


@app.route("/api/signals/<signal_id>/confirm", methods=["POST"])
def api_confirm_signal(signal_id):
    """人确认/拒绝信号"""
    from notify.signal_handler import handle_confirm_signal
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid JSON"}), 400
    action = data.get("action", "confirm")
    result = handle_confirm_signal(signal_id, action)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result), 200


@app.route("/api/signals/<signal_id>", methods=["GET"])
def api_get_signal(signal_id):
    """查询信号状态"""
    from notify.signal_handler import handle_get_signal
    result = handle_get_signal(signal_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result), 200
# === Signal API endpoints end ===


if __name__ == "__main__":
    # Fix Windows GBK encoding for emoji
    import sys

    if sys.platform == "win32":
        import io

        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )

    port = int(sys.argv[1]) if len(sys.argv) > 1 else get_webhook_port()

    print("=" * 60)
    print("[START] TradingView -> Feishu Bridge")
    print("=" * 60)
    print(f"Address: http://0.0.0.0:{port}")

    # 启动时预初始化 IB（后台线程，避免阻塞 Flask）
    import threading

    def _bg_connect():
        try:
            ib = get_ib_connection()
            print(
                f"[IB] pre-connect result: connected={ib.isConnected() if ib else False}"
            )
            # 注册 execDetails 成交回调
            _register_fill_callback()
        except Exception as e:
            print(f"[IB] pre-connect failed: {e}")

    t = threading.Thread(target=_bg_connect, daemon=True)
    t.start()
    # 不等待，让 Flask 立即启动，IB 在后台连接
    print("[IB] 连接已在后台启动...")

    print()
    print(f"Mode: {'Query Only' if QUERY_ONLY else 'Trading'}")

    # 自动检查并启动 Z120 监控 - 已禁用，用户要求手动启动
    # z120_running = get_z120_status()
    # if z120_running.startswith("✅"):
    #     print(f"📊 Z120 监控: 已运行")
    # else:
    #     print("📊 Z120 监控: 自动启动...")
    #     start_result = start_z120_monitor()
    #     print(f"      {start_result}")

    print()
    print("端点:")
    print(f"  Webhook: http://localhost:{port}/webhook")
    print(f"  飞书控制: POST /feishu-webhook")
    print(f"  测试: POST /test-api")
    print(f"  健康检查: GET /health")
    print()
    print("命令 (在飞书群发送):")
    print("  /持仓 - 查询持仓")
    print("  /账户 - 查询账户")
    print("  /订单 - 查询订单")
    print("  /成交 - 查询成交")
    print("  /status - 查看监控状态")
    print("  /help - 显示帮助")
    print("=" * 60)

    app.run(host="0.0.0.0", port=port, threaded=True)
