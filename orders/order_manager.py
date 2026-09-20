#!/usr/bin/env python3
"""统一订单管理器 — 所有下单路径归一到此"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional
from datetime import datetime

from orders.risk_gate import RiskGate, OrderContext, GateMode


class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class OrderResult:
    order_id: str = ""
    status: str = ""
    filled: float = 0.0
    message: str = ""
    risk_warnings: list = field(default_factory=list)
    timestamp: str = ""


class OrderManager:
    """统一订单入口 — 风控检查 + 交易所路由 + 订单追踪"""

    def __init__(self):
        self._risk_gate = RiskGate()
        self._orders: Dict[str, dict] = {}

    def place(self, ctx: OrderContext, gate_mode=GateMode.STRICT) -> OrderResult:
        # SimNow / CTP 路由
        if ctx.exchange == "SIMNOW":
            return self._place_simnow(ctx, gate_mode)
        # 1. 风控检查
        risk_result = self._risk_gate.final_check(ctx, mode=gate_mode)
        if not risk_result.allowed:
            return OrderResult(
                status="rejected",
                message=risk_result.reason,
                risk_warnings=risk_result.warnings,
                timestamp=datetime.now().isoformat(),
            )

        # 2. 路由到对应交易所
        if ctx.exchange == "IB":
            from orders.place_order_func import place_order
            from client.ib_connection import get_ib_connection
            ib = get_ib_connection()
            if ib is None:
                return OrderResult(status="rejected", message="IB not connected")
            result = place_order(
                ib, ctx.symbol, ctx.action, ctx.quantity,
                sec_type=ctx.sec_type or "",
                conId=ctx.conId or None,
                close_position=ctx.close_position,
                outside_rth=ctx.outside_rth,
                order_type=getattr(ctx, "order_type", "MKT") or "MKT",
                limit_price=getattr(ctx, "limit_price", None),
                stop_price=getattr(ctx, "stop_price", None),
                tif=getattr(ctx, "tif", "DAY") or "DAY",
            )
        elif ctx.exchange == "OKX":
            result = {"status": "Submitted", "orderId": "okx_pending"}
        else:
            return OrderResult(status="rejected", message=f"unknown exchange: {ctx.exchange}")

        # 3. 记录
        order_id = str(result.get("orderId", ""))
        self._orders[order_id] = {
            "status": result.get("status", "Unknown"),
            "ctx": ctx,
            "timestamp": datetime.now().isoformat(),
            "risk_warnings": risk_result.warnings,
        }
        # 4. 同步 orderId → signal_id 映射（用于 ORDER_FILLED 回写）
        if order_id and ctx.signal_id:
            try:
                from trading.notify.webhook_bridge import _order_to_signal
                _order_to_signal[int(order_id)] = ctx.signal_id
            except Exception:
                pass  # 非 IB 订单或映射失败不影响主流程

        return OrderResult(
            order_id=order_id,
            status=result.get("status", "Unknown"),
            filled=result.get("filled", 0),
            message=result.get("message", ""),
            risk_warnings=risk_result.warnings,
            timestamp=datetime.now().isoformat(),
        )

    def cancel(self, order_id: str) -> dict:
        """取消订单"""
        if order_id not in self._orders:
            return {"error": "order not found"}
        self._orders[order_id]["status"] = "Cancelled"
        return {"order_id": order_id, "status": "Cancelled"}

    def get_status(self, order_id: str) -> Optional[dict]:
        """查询订单状态"""
        return self._orders.get(order_id)

    # ── SimNow / CTP 下单 ────────────────────────────────────────

    @staticmethod
    def _get_simnow_trader():
        """SimNowTrader 单例（延迟创建）"""
        if not hasattr(OrderManager, "_simnow_trader"):
            OrderManager._simnow_trader: Optional["SimNowTrader"] = None
        if OrderManager._simnow_trader is None:
            from ctp_client.trader import SimNowTrader
            OrderManager._simnow_trader = SimNowTrader()
            ok = OrderManager._simnow_trader.connect(timeout=15.0)
            if not ok:
                err = OrderManager._simnow_trader.last_error()
                OrderManager._simnow_trader = None
                raise RuntimeError(f"SimNow 连接失败: {err}")
        return OrderManager._simnow_trader

    def _place_simnow(self, ctx: OrderContext, gate_mode) -> OrderResult:
        """通过 SimNow / CTP 执行下单"""
        try:
            trader = self._get_simnow_trader()
        except RuntimeError as e:
            return OrderResult(status="rejected", message=str(e))

        action_map = {"BUY": "long", "SELL": "short"}
        direction = action_map.get(ctx.action.upper(), ctx.action.lower())
        price = ctx.price or 0.0

        result = trader.place_order(
            symbol=ctx.symbol,
            direction=direction,
            volume=int(ctx.quantity),
            price=price,
            order_type="market" if price == 0 else "limit",
        )

        self._orders[result.order_id] = {
            "status": result.status,
            "ctx": ctx,
            "timestamp": result.timestamp,
            "risk_warnings": [],
        }

        return OrderResult(
            order_id=result.order_id,
            status=result.status,
            message=result.message,
            timestamp=result.timestamp,
        )
