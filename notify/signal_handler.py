#!/usr/bin/env python3
"""信号处理 — Agent 提交信号 → 风控预检 → 飞书推送 → 人确认 → 下单"""
import json, os
from datetime import datetime, timedelta
from pathlib import Path

SIGNALS_FILE = Path(__file__).parent.parent / "data" / "signals.jsonl"
SIGNAL_EXPIRY_HOURS = 24


def _read_signals():
    if not SIGNALS_FILE.exists():
        return {}
    signals = {}
    with open(SIGNALS_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                sig = json.loads(line)
                signals[sig["signal_id"]] = sig
            except json.JSONDecodeError:
                continue
    return signals


def _write_signal(sig: dict):
    SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SIGNALS_FILE, 'a') as f:
        f.write(json.dumps(sig, ensure_ascii=False) + '\n')


def _freshen_signal(signal_id: str, updates: dict):
    """更新信号状态（追加新行，解析时取最后一条）"""
    signals = _read_signals()
    sig = signals.get(signal_id, {})
    sig.update(updates)
    _write_signal(sig)


def handle_submit_signal(data: dict) -> dict:
    """处理 Agent 提交的交易信号"""
    from orders.risk_gate import RiskGate, OrderContext, GateMode

    signal_id = f"sig_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(2).hex()}"

    # 风控预检
    risk_gate = RiskGate()
    risk_ctx = OrderContext(
        symbol=data.get("symbol", ""),
        action="BUY" if data.get("direction") == "long" else "SELL",
        quantity=float(data.get("quantity", 1)),
        exchange="IB",
        zscore=data.get("zscore"),
        correlation=data.get("correlation"),
    )
    risk_result = risk_gate.pre_check(risk_ctx, mode=GateMode.STRICT)

    status = "rejected" if not risk_result.allowed else "reviewed"
    signal = {
        "signal_id": signal_id,
        "source": data.get("source", "unknown"),
        "symbol": data.get("symbol", ""),
        "direction": data.get("direction", ""),
        "quantity": data.get("quantity", 1),
        "hedge_ratio": data.get("hedge_ratio"),
        "zscore": data.get("zscore"),
        "reason": data.get("reason", ""),
        "strategy": data.get("strategy", ""),
        "status": status,
        "risk": {
            "allowed": risk_result.allowed,
            "warnings": risk_result.warnings,
            "reason": risk_result.reason if not risk_result.allowed else "",
        },
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(hours=SIGNAL_EXPIRY_HOURS)).isoformat(),
    }
    _write_signal(signal)

    return {
        "signal_id": signal_id,
        "status": status,
        "risk": signal["risk"],
    }


def handle_confirm_signal(signal_id: str, action: str) -> dict:
    """处理人的确认/拒绝操作"""
    signals = _read_signals()
    signal = signals.get(signal_id)
    if not signal:
        return {"error": "signal not found", "signal_id": signal_id}

    if signal.get("status") != "reviewed":
        return {"error": f"signal already {signal.get('status')}", "signal_id": signal_id}

    # 检查过期
    expires_at = datetime.fromisoformat(signal["expires_at"])
    if datetime.now() > expires_at:
        _freshen_signal(signal_id, {"status": "expired"})
        return {"error": "signal expired", "signal_id": signal_id}

    if action == "reject":
        _freshen_signal(signal_id, {"status": "rejected"})
        return {"signal_id": signal_id, "status": "rejected"}

    if action == "confirm":
        from orders.risk_gate import RiskGate, OrderContext, GateMode
        from orders.order_manager import OrderManager

        # 二次风控校验
        risk_gate = RiskGate()
        risk_ctx = OrderContext(
            symbol=signal["symbol"],
            action="BUY" if signal["direction"] == "long" else "SELL",
            quantity=float(signal["quantity"]),
            exchange="IB",
            zscore=signal.get("zscore"),
            correlation=signal.get("correlation"),
        )
        risk_result = risk_gate.final_check(risk_ctx, mode=GateMode.STRICT)
        if not risk_result.allowed:
            _freshen_signal(signal_id, {
                "status": "rejected",
                "risk_reject_reason": risk_result.reason,
            })
            return {"signal_id": signal_id, "status": "rejected",
                    "reason": risk_result.reason}

        # 执行下单
        mgr = OrderManager()
        result = mgr.place(risk_ctx, gate_mode=GateMode.STRICT)

        _freshen_signal(signal_id, {
            "status": "executed" if result.status == "Filled" else "rejected",
            "order_id": result.order_id,
            "executed_at": datetime.now().isoformat(),
        })
        return {"signal_id": signal_id, "status": signal.get("status", "executed"),
                "order_id": result.order_id, "message": result.message}

    return {"error": f"unknown action: {action}", "signal_id": signal_id}


def handle_get_signal(signal_id: str) -> dict:
    """查询信号状态"""
    signals = _read_signals()
    signal = signals.get(signal_id)
    if not signal:
        return {"error": "signal not found", "signal_id": signal_id}
    return signal