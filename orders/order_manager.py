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
            result = place_order(ib, ctx.symbol, ctx.action, ctx.quantity)
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