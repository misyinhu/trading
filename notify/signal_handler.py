#!/usr/bin/env python3
"""信号处理 — 半自动(人确认) + 全自动(auto=true) 双模式

完全自主下单:
    Agent POST /api/signals {auto: true, source: "quant-agent"}
        → 策略校验 + RiskGate.pre_check
        → _execute_from_signal() 直接执行
        → status: executed (跳过 reviewed)
        → 飞书推送成交结果

安全: AUTO_EXECUTE_WHITELIST 限制可自主执行的 source。
"""
import json, os
from datetime import datetime, timedelta
from pathlib import Path

SIGNALS_FILE = Path(__file__).parent.parent / "data" / "signals.jsonl"
SIGNAL_EXPIRY_HOURS = 24

# 自动执行白名单：仅这些 source 可以使用 auto=true
AUTO_EXECUTE_WHITELIST = frozenset({"quant-agent", "smoke-test"})


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


def _get_open_position_count() -> int:
    """查询 IB 当前持仓symbol数量（去重）"""
    try:
        from client.ib_connection import get_ib_manager
        manager = get_ib_manager()
        def _do():
            ib = manager._ib
            positions = ib.positions()
            # 去重 symbol 数量
            symbols = {p.contract.symbol for p in positions if p.position != 0}
            return len(symbols)
        return manager.run_sync(_do, timeout=10)
    except Exception:
        return 0


def _execute_from_signal(signal: dict) -> dict:
    """
    根据信号内容执行下单（被 handle_confirm_signal 和 handle_submit_signal 共用）。
    返回执行结果 dict。
    """
    from orders.risk_gate import RiskGate, OrderContext, GateMode
    from orders.order_manager import OrderManager
    from orders.strategy_registry import get_registry

    strategy_name = signal.get("strategy", "")
    registry = get_registry()
    spec = registry.get(strategy_name) if strategy_name else None
    exchange = spec.exchange if spec else signal.get("exchange", "IB")

    # 查询当前持仓数，供 RiskGate MaxPositionsGuard 使用
    open_pos_count = _get_open_position_count()

    # 多腿判断: spec 有 spread_symbols（传统多腿），或 signal 带 legs（通用配对）
    is_multileg = (spec and spec.spread_symbols) or bool(signal.get("legs"))
    if is_multileg:
        # 多腿策略
        contexts, _ = registry.build_order_contexts(strategy_name, signal)
        results = []
        all_ok = True
        for ctx_kwargs in contexts:
            ctx_kwargs["signal_id"] = signal.get("signal_id", "")
            risk_gate = RiskGate()
            ctx = OrderContext(open_positions=open_pos_count, **ctx_kwargs)
            risk_result = risk_gate.final_check(ctx, mode=GateMode.STRICT)
            if not risk_result.allowed:
                results.append({
                    "ctx": ctx_kwargs,
                    "status": "rejected",
                    "reason": risk_result.reason,
                })
                all_ok = False
                continue
            mgr = OrderManager()
            res = mgr.place(ctx, gate_mode=GateMode.STRICT)
            results.append({
                "ctx": ctx_kwargs,
                "status": res.status,
                "order_id": res.order_id,
                "message": res.message,
            })
            if res.status != "Filled":
                all_ok = False
        return {
            "status": "executed" if all_ok else "partial",
            "legs": results,
        }
    else:
        # 单腿策略
        risk_gate = RiskGate()
        risk_ctx = OrderContext(
            symbol=signal["symbol"],
            action="BUY" if signal["direction"] == "long" else "SELL",
            quantity=float(signal["quantity"]),
            exchange=exchange,
            zscore=signal.get("zscore"),
            correlation=signal.get("correlation"),
            open_positions=open_pos_count,
            signal_id=signal.get("signal_id", ""),
        )
        risk_result = risk_gate.final_check(risk_ctx, mode=GateMode.STRICT)
        if not risk_result.allowed:
            return {
                "status": "rejected",
                "reason": risk_result.reason,
            }
        mgr = OrderManager()
        result = mgr.place(risk_ctx, gate_mode=GateMode.STRICT)
        return {
            "status": "executed",
            "order_id": result.order_id,
            "message": result.message,
        }


def handle_submit_signal(data: dict) -> dict:
    """
    处理 Agent 提交的交易信号。

    半自动模式（默认）: 风控预检 → status=reviewed → 等待人确认
    全自动模式（auto=true）: 风控预检 → 直接执行（跳过人确认）

    仅 AUTO_EXECUTE_WHITELIST 中的 source 可以使用 auto=true。
    """
    from orders.risk_gate import RiskGate, OrderContext, GateMode
    from orders.strategy_registry import get_registry, get_approved_cache

    signal_id = f"sig_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(2).hex()}"
    strategy_name = data.get("strategy", "")
    strategy_id = data.get("strategy_id", "")
    auto_execute = data.get("auto", False)
    source = data.get("source", "unknown")

    # 已批准策略校验（quant-agent 端未批准则拒绝）
    if strategy_id and not get_approved_cache().is_approved(strategy_id):
        return {
            "signal_id": signal_id,
            "status": "rejected",
            "rejected": True,
            "reason": f"strategy_id={strategy_id} not approved by quant-agent",
        }

    # 自动执行权限校验
    if auto_execute and source not in AUTO_EXECUTE_WHITELIST:
        return {
            "signal_id": signal_id,
            "status": "rejected",
            "risk": {
                "allowed": False,
                "reason": f"auto=true not allowed for source={source}. "
                          f"whitelist: {sorted(AUTO_EXECUTE_WHITELIST)}",
            },
        }

    # 策略注册表校验
    registry_errors = []
    if strategy_name:
        registry = get_registry()
        validation = registry.validate(strategy_name, data)
        if not validation.valid:
            registry_errors = validation.errors

    # 查询当前持仓数，供风控使用
    open_pos_count = _get_open_position_count()

    # 风控预检
    risk_gate = RiskGate()
    risk_ctx = OrderContext(
        symbol=data.get("symbol", ""),
        action="BUY" if data.get("direction") == "long" else "SELL",
        quantity=float(data.get("quantity", 1)),
        exchange="IB",
        zscore=data.get("zscore"),
        correlation=data.get("correlation"),
        open_positions=open_pos_count,
    )
    risk_result = risk_gate.pre_check(risk_ctx, mode=GateMode.STRICT)

    # 合并策略校验错误 + 风控结果
    if registry_errors:
        registry_rejection = f"strategy validation failed: {registry_errors[0]}"
        status = "rejected"
        risk_result_allowed = False
        risk_reason = registry_rejection
    else:
        risk_result_allowed = risk_result.allowed
        risk_reason = risk_result.reason
        status = "rejected" if not risk_result_allowed else "reviewed"

    signal = {
        "signal_id": signal_id,
        "source": source,
        "symbol": data.get("symbol", ""),
        "direction": data.get("direction", ""),
        "quantity": data.get("quantity", 1),
        "hedge_ratio": data.get("hedge_ratio"),
        "zscore": data.get("zscore"),
        "reason": data.get("reason", ""),
        "strategy": strategy_name,
        "status": status,
        "legs": data.get("legs"),      # 多腿展开所需（pairs-spread / fu-lu-spread）
        "risk": {
            "allowed": risk_result_allowed,
            "warnings": risk_result.warnings,
            "reason": risk_reason,
        },
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(hours=SIGNAL_EXPIRY_HOURS)).isoformat(),
    }
    _write_signal(signal)

    # ===== 全自动执行路径 =====
    if auto_execute and status == "reviewed":
        exec_result = _execute_from_signal(signal)
        _freshen_signal(signal_id, {
            "status": exec_result.get("status", "rejected"),
            **exec_result,
            "executed_at": datetime.now().isoformat(),
            "mode": "auto",
        })
        resp = {
            "signal_id": signal_id,
            "status": exec_result.get("status", "rejected"),
            "mode": "auto",
            "risk": signal["risk"],
        }
        resp.update(exec_result)
        return resp

    # ===== 半自动路径 =====
    resp = {
        "signal_id": signal_id,
        "status": status,
        "risk": signal["risk"],
    }
    if registry_errors:
        resp["strategy_errors"] = registry_errors
    return resp


def handle_confirm_signal(signal_id: str, action: str) -> dict:
    """处理人的确认/拒绝操作"""
    signals = _read_signals()
    signal = signals.get(signal_id)
    if not signal:
        return {"error": "signal not found", "signal_id": signal_id}

    if signal.get("status") not in ("reviewed",):
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
        exec_result = _execute_from_signal(signal)
        _freshen_signal(signal_id, {
            "status": exec_result.get("status", "rejected"),
            **exec_result,
            "executed_at": datetime.now().isoformat(),
            "mode": "manual",
        })
        return {"signal_id": signal_id, **exec_result}

    return {"error": f"unknown action: {action}", "signal_id": signal_id}


def handle_get_signal(signal_id: str) -> dict:
    """查询信号状态"""
    signals = _read_signals()
    signal = signals.get(signal_id)
    if not signal:
        return {"error": "signal not found", "signal_id": signal_id}
    return signal