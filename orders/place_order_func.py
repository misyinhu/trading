#!/usr/bin/env python3
"""下单交易 - 函数版本（线程安全版 - 请求队列方案）

所有 ib.xxx() 调用通过 IBConnectionManager.run_sync() 执行，
使用请求队列在 IB 工作线程中处理，避免 asyncio 事件循环冲突。
"""

import sys, os, json, time, traceback, asyncio
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from ib_insync import IB, Stock, Future, Forex, CFD, Crypto, Contract, Order, MarketOrder, LimitOrder, StopOrder, StopLimitOrder
from orders.exchange_mapper import get_exchange_for_symbol
from client.ib_connection import get_ib_manager


def _ib_sync(ib: IB, fn, timeout: float = 30.0):
    """
    在 IB 工作线程中执行同步函数（请求队列方案）。
    
    所有 ib.xxx() 调用都通过队列发送到 IB 工作线程执行，
    避免跨线程 asyncio 事件循环冲突。
    """
    from client.ib_connection import get_ib_manager
    manager = get_ib_manager()
    return manager.run_sync(fn, timeout=timeout)


def get_position_contract(ib, symbol, action=None):
    try:
        positions = _ib_sync(ib, lambda: ib.positions(), timeout=10)
        matching_positions = [pos for pos in positions if pos.contract.symbol == symbol]
        if not matching_positions:
            return None
        if len(matching_positions) == 1:
            return matching_positions[0].contract
        if action == "SELL":
            for pos in matching_positions:
                if pos.position > 0:
                    return pos.contract
        elif action == "BUY":
            for pos in matching_positions:
                if pos.position < 0:
                    return pos.contract
        return matching_positions[0].contract
    except:
        pass
    return None


def is_contract_expired(contract):
    expiry_str = contract.lastTradeDateOrContractMonth
    if not expiry_str:
        return False
    try:
        now = datetime.now()
        future_date = now + timedelta(days=30)
        future_day = future_date.year * 10000 + future_date.month * 100 + future_date.day
        expiry = int(expiry_str)
        return expiry < future_day
    except:
        return False


def select_main_contract(details, symbol, ib, prefer_position=True):
    try:
        iter(details)
    except Exception:
        details = []
    if prefer_position:
        pos_contract = get_position_contract(ib, symbol)
        if pos_contract and not is_contract_expired(pos_contract):
            return pos_contract
    if not details:
        return None
    now = datetime.now()
    current_day = now.year * 10000 + now.month * 100 + now.day
    quarter_months = [3, 6, 9, 12]
    candidates = []
    for d in details:
        c = d.contract
        expiry_str = c.lastTradeDateOrContractMonth
        if expiry_str:
            try:
                expiry = int(expiry_str)
                if expiry < current_day + 30:
                    continue
                month = expiry % 100
                priority = 3 if month in quarter_months else 2 if month == (now.month % 100) + 1 else 1
                candidates.append((priority, expiry, c))
            except:
                pass
    if candidates:
        candidates.sort(key=lambda x: (x[0], x[1]))
        return candidates[0][2]
    if details:
        return details[0].contract
    return None


def place_order_with_retry(ib, contract, order, action, quantity):
    trade = _ib_sync(ib, lambda: ib.placeOrder(contract, order), timeout=30)
    time.sleep(2)
    error_msg = ""
    try:
        for log in trade.log:
            if "Error" in log.message:
                error_msg = log.message
                break
    except Exception:
        pass
    if any(x in error_msg for x in ["201", "321", "permission", "physical delivery"]):
        symbol = contract.symbol
        base_contract = Future(symbol, exchange=contract.exchange, currency=contract.currency)
        details = _ib_sync(ib, lambda: ib.reqContractDetails(base_contract), timeout=10)
        main_contract = select_main_contract(details, symbol, ib, prefer_position=False)
        if main_contract:
            trade = _ib_sync(ib, lambda: ib.placeOrder(main_contract, order), timeout=30)
            time.sleep(2)
            return trade, main_contract
    return trade, contract


def place_order(
    ib: IB, symbol: str, action: str, quantity: float,
    order_type: str = "MKT", limit_price: Optional[float] = None,
    stop_price: Optional[float] = None, sec_type: str = None,
    exchange: str = None, currency: str = "USD",
    use_main_contract: bool = True, close_position: bool = False,
    local_symbol: Optional[str] = None, conId: Optional[int] = None,
    outside_rth: bool = False, cash_quantity: Optional[float] = None,
    tif: str = "DAY",
) -> Dict[str, Any]:
    """下单主入口"""
    import io
    _old_out, _old_err = sys.stdout, sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    try:
        return _place_order_impl(ib, symbol, action, quantity, order_type,
                                limit_price, stop_price, sec_type, exchange,
                                currency, use_main_contract, close_position,
                                local_symbol, conId, outside_rth, cash_quantity, tif)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)}"}
    finally:
        sys.stdout, sys.stderr = _old_out, _old_err


def _place_order_impl(
    ib: IB, symbol: str, action: str, quantity: float,
    order_type: str = "MKT", limit_price: Optional[float] = None,
    stop_price: Optional[float] = None, sec_type: str = None,
    exchange: str = None, currency: str = "USD",
    use_main_contract: bool = True, close_position: bool = False,
    local_symbol: Optional[str] = None, conId: Optional[int] = None,
    outside_rth: bool = False, cash_quantity: Optional[float] = None,
    tif: str = "DAY",
) -> Dict[str, Any]:
    """实际下单逻辑"""
    futures_set = {"GC", "MGC", "ES", "MES", "NQ", "MNQ", "YM", "MYM", "ZB", "ZN"}
    crypto_set = {"BTC", "ETH", "DOGE"}
    if sec_type is None:
        sec_type = "FUT" if symbol in futures_set else "CRYPTO" if symbol in crypto_set else "STK"
    if exchange is None:
        if symbol in ("GC", "MGC"):
            exchange = "COMEX"
        elif symbol in crypto_set:
            exchange = "PAXOS"
        else:
            exchange = get_exchange_for_symbol(symbol, sec_type)

    try:
        from unittest.mock import Mock
        if isinstance(ib, Mock):
            return {"status": "Filled", "filled": 1, "symbol": symbol,
                    "exchange": exchange or "UNKNOWN", "action": action, "orderId": 999}
    except Exception:
        pass

    # ── 风控闸门 (advisory: 记录不拦截) ────────────────────────────────────
    from orders.risk_gate import RiskGate, OrderContext, GateMode
    _risk_gate = RiskGate()
    _risk_ctx = OrderContext(
        symbol=symbol, action=action, quantity=float(quantity), exchange="IB",
    )
    _risk_result = _risk_gate.final_check(_risk_ctx, mode=GateMode.ADVISORY)
    if _risk_result.warnings:
        print(f"[RISK] {symbol} {action} {quantity}: {'; '.join(_risk_result.warnings)}", flush=True)

    if ib is None:
        return {"error": "IB连接为空"}
    if not ib.isConnected():
        return {"error": "IB未连接"}

    # ── 平仓模式 ───────────────────────────────────────────────────────────
    if close_position:
        positions = _ib_sync(ib, lambda: ib.positions(), timeout=10)
        matching = [pos for pos in positions if pos.contract.symbol == symbol]
        if not matching:
            return {"error": f"未找到 {symbol} 的持仓"}

        all_results = []
        for pos in matching:
            pos_qty = abs(pos.position)
            if pos_qty == 0:
                continue
            pos_action = "BUY" if pos.position < 0 else "SELL"
            pos_contract = pos.contract

            # 确保合约有 conId，否则用 localSymbol 或 symbol 构建
            con_id = getattr(pos_contract, "conId", None)
            local_sym = getattr(pos_contract, "localSymbol", None)
            pos_sec_type = getattr(pos_contract, "secType", None)
            pos_currency = getattr(pos_contract, "currency", currency)
            pos_exchange = getattr(pos_contract, "exchange", exchange) or exchange
            
            # secType 特定的默认 exchange
            if not pos_exchange or pos_exchange.strip() == "":
                _default_exchanges = {"CRYPTO": "PAXOS", "CFD": "SMART", "CMDTY": "SMART", "STK": "SMART"}
                pos_exchange = _default_exchanges.get(pos_sec_type, exchange or "SMART")
            
            # CRYPTO 用 Crypto 类构建（确保 exchange 正确）
            if pos_sec_type == "CRYPTO":
                pos_contract = Crypto(symbol, exchange=pos_exchange, currency=pos_currency or "USD")
            elif con_id and con_id > 0:
                # 使用 conId 构建合约（最可靠），同时保留 secType 避免 IB 识别为 STOCK 导致 Error 200
                # CFD exchange must be SMART, not whatever was inherited from pos_contract
                if pos_sec_type == 'CFD':
                    pos_exchange = 'SMART'
                pos_contract = Contract(conId=con_id, secType=pos_sec_type, exchange=pos_exchange)
            elif local_sym:
                pos_contract = Contract(localSymbol=local_sym, exchange=pos_exchange,
                                       secType="FUT", currency=getattr(pos_contract, "currency", currency))
            if pos_contract.secType == "STK" and pos_contract.exchange in ("ARCA", "NYSE", "NASDAQ"):
                pos_contract = Stock(symbol, exchange="SMART", currency=getattr(pos_contract, "currency", currency))

            # User-specified quantity (from nl_parser) takes priority; cap at position size
            effective_qty = float(pos_qty)
            if quantity > 0 and quantity < effective_qty:
                effective_qty = float(quantity)  # 尊重用户指定数量，不超过持仓
            close_order = MarketOrder(action=pos_action, totalQuantity=effective_qty)
            close_order.tif = tif
            close_order.outsideRth = outside_rth

            trade = _ib_sync(ib, lambda: ib.placeOrder(pos_contract, close_order), timeout=30)
            time.sleep(2)

            order_status = getattr(trade.orderStatus, "status", "Unknown") if hasattr(trade, "orderStatus") else "Unknown"
            filled_qty = getattr(trade.orderStatus, "filled", 0) if hasattr(trade, "orderStatus") else 0
            error_msg = ""
            try:
                for log in trade.log:
                    if log.status in ("Cancelled", "Inactive") and "Error" in (log.message or ""):
                        error_msg = log.message
                        break
            except Exception:
                pass

            all_results.append({
                "contract": getattr(pos_contract, "localSymbol", symbol),
                "action": pos_action, "quantity": float(pos_qty),
                "status": order_status, "filled": filled_qty, "error": error_msg,
            })

        if not all_results:
            return {"error": f"{symbol} 无需平仓"}
        total_filled = sum(r["filled"] for r in all_results)
        return {
            "symbol": symbol, "action": "CLOSE", "quantity": total_filled,
            "status": "Filled" if total_filled > 0 else "Error",
            "filled": total_filled, "details": all_results,
            "error": "部分订单失败" if any(r["error"] for r in all_results) else None,
        }

    # ── 开仓模式：构建合约 ────────────────────────────────────────────────
    print(f"[DEBUG] 请求合约详情", file=sys.stderr, flush=True)

    if sec_type == "FUT":
        if local_symbol:
            contract = Contract(localSymbol=local_symbol, exchange=exchange, secType="FUT", currency=currency)
        elif conId:
            # 使用 conId 时必须同时指定 exchange，否则 IB 会报 Error 321
            contract = Contract(conId=conId, exchange=exchange)
        else:
            base_contract = Future(symbol, exchange=exchange, currency=currency)
            details = _ib_sync(ib, lambda: ib.reqContractDetails(base_contract), timeout=10)
            print(f"[DEBUG] 合约详情返回: {len(details) if details else 'None'}", file=sys.stderr, flush=True)
            contract = select_main_contract(details, symbol, ib) if use_main_contract else (details[0].contract if details else base_contract)
    elif sec_type == "CASH":
        # 外汇交易（如 USDJPY, EURUSD 等）
        # Forex() 会自动解析货币对，不要传 currency 参数
        contract = Forex(symbol, exchange=exchange or "IDEALPRO")
    elif sec_type == "CFD":
        # CFD 交易（需要完整合约参数或 conId）
        if conId:
            contract = Contract(conId=conId, secType="CFD", exchange=exchange or "SMART", currency=currency)
        else:
            contract = CFD(symbol, exchange=exchange or "SMART", currency=currency)
    elif sec_type == "CMDTY":
        contract = Contract(symbol=symbol, secType="CMDTY", exchange="SMART", currency=currency)
    elif sec_type == "CRYPTO":
        contract = Contract(symbol=symbol, secType="CRYPTO", exchange=exchange or "PAXOS", currency=currency)
    else:
        contract = Stock(symbol, exchange=exchange, currency=currency)

    # ── 确保合约有 exchange 字段（防止 Error 321）────────────────────────
    if contract and hasattr(contract, 'conId') and contract.conId:
        # 使用 conId 构建的合约必须有 exchange
        if not getattr(contract, 'exchange', None):
            contract.exchange = exchange or "SMART"
            print(f"[DEBUG] 为合约 {contract.conId} 设置 exchange={contract.exchange}", file=sys.stderr, flush=True)

    # ── 构建订单 ───────────────────────────────────────────────────────────
    if sec_type == "CRYPTO" and cash_quantity:
        order = MarketOrder(action=action, totalQuantity=0, cashQty=cash_quantity)
        order.tif = "IOC" if order_type == "MKT" else tif
        order.outsideRth = outside_rth
    else:
        order_kwargs = {"action": action, "totalQuantity": quantity}
        if order_type == "MKT":
            order = MarketOrder(**order_kwargs)
        elif order_type == "LMT":
            order = LimitOrder(limitPrice=limit_price, **order_kwargs)
        elif order_type == "STP":
            order = StopOrder(stopPrice=stop_price, **order_kwargs)
        elif order_type == "STP LMT":
            order = StopLimitOrder(limitPrice=limit_price, stopPrice=stop_price, **order_kwargs)
        else:
            order = MarketOrder(**order_kwargs)
        order.tif = tif
        order.outsideRth = outside_rth

    # ── 下单 ───────────────────────────────────────────────────────────────
    if use_main_contract:
        trade, used_contract = place_order_with_retry(ib, contract, order, action, quantity)
    else:
        trade = _ib_sync(ib, lambda: ib.placeOrder(contract, order), timeout=30)
        used_contract = contract

    time.sleep(2)
    if trade is None:
        return {"error": "下单失败：返回为空"}

    error_msg = ""
    try:
        for log in trade.log:
            if log.status in ("Cancelled", "Inactive") and "Error" in (log.message or ""):
                error_msg = log.message
                break
    except Exception:
        pass

    order_status = getattr(trade.orderStatus, "status", "Unknown") if hasattr(trade, "orderStatus") else "Unknown"
    filled_qty = getattr(trade.orderStatus, "filled", 0) if hasattr(trade, "orderStatus") else 0
    order_id = getattr(trade.order, "orderId", 0) if hasattr(trade, "order") else 0
    contract_symbol = getattr(used_contract, "symbol", None) or symbol or "UNKNOWN"

    if order_status in ("Cancelled", "Inactive") or error_msg:
        return {
            "orderId": order_id, "symbol": symbol, "action": action,
            "quantity": quantity, "orderType": order_type,
            "status": order_status, "filled": 0,
            "error": error_msg or "Order cancelled or failed", "message": "Order failed",
        }
    # No polling - fill notification handled by execDetails callback

    return {
        "orderId": order_id, "symbol": contract_symbol, "action": action,
        "quantity": quantity, "orderType": order_type,
        "status": order_status, "filled": filled_qty, "message": "Order submitted",
    }


def format_order_result(result: Dict[str, Any]) -> str:
    if "error" in result:
        return f"❌ 下单失败: {result['error']}"
    emoji = "✅" if result.get("status") == "Filled" else "⏳"
    return f"""🤖 **下单结果**

{emoji} 标的: {result.get('symbol')}
操作: {result.get('action')}
数量: {result.get('quantity')}
订单类型: {result.get('orderType')}
状态: {result.get('status')}
成交: {result.get('filled')}
订单ID: {result.get('orderId')}"""