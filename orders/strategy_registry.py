#!/usr/bin/env python3
"""轻量策略注册表 — 策略名→参数校验→下单上下文映射"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


@dataclass
class StrategySpec:
    """单个策略规格"""
    name: str
    description: str = ""
    exchange: str = "IB"                          # IB / OKX
    required_params: List[str] = field(default_factory=list)   # 必须提供的参数
    param_constraints: Dict[str, Tuple[Any, Any]] = field(default_factory=list)  # 参数名→(min, max) 范围约束
    default_quantity: float = 1.0
    # 多腿支持：None=单腿，非None=多腿
    # spread_symbols: 单个 symbol 字段包含逗号分隔的多腿，如 "FU-LU"
    spread_symbols: Optional[str] = None         # e.g. "FUL8.SHF,LUL8.INE" 或 None
    # 方向映射：signal["direction"] → [(symbol, action), ...]
    direction_map: Dict[str, List[Tuple[str, str]]] = field(default_factory=list)  # 重构，见下方


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class StrategyRegistry:
    """
    策略注册表 — 验证 Agent 信号，映射为 OrderContext。

    使用方式:
        registry = StrategyRegistry()
        result = registry.validate("fu-lu-spread", signal_data)
        if result.valid:
            contexts = registry.build_order_contexts("fu-lu-spread", signal_data)
    """

    def __init__(self):
        self._strategies: Dict[str, StrategySpec] = {}
        self._register_defaults()

    def _register_defaults(self):
        # 燃油/沥青价差策略（IB 期货）
        self.register(StrategySpec(
            name="fu-lu-spread",
            description="FU/LU 价差 — 协整 Z-Score 均值回归",
            exchange="IB",
            required_params=["zscore"],
            param_constraints={
                "zscore": (-4.0, 4.0),
                "correlation": (0.7, 1.0),
                "hedge_ratio": (0.01, 10.0),
            },
            default_quantity=1.0,
            spread_symbols="FU,LU",
            # direction_map: strategy direction → [(symbol_suffix, action)]
            # FU-LU spread: 做多价差=买FU卖LU，做空价差=卖FU买LU
            direction_map={
                "long":  [("FULU_LONG", "BUY")],   # placeholder, actual symbol built in build_order_contexts
                "short": [("FULU_SHORT", "SELL")],
            },
        ))

        # DOGE 网格策略（OKX）
        self.register(StrategySpec(
            name="doge-grid",
            description="DOGE 网格机器人（OKX）",
            exchange="OKX",
            required_params=["symbol"],
            param_constraints={
                "zscore": (-4.0, 4.0),
            },
            default_quantity=1.0,
        ))

        # 加密货币背离监控（OKX）
        self.register(StrategySpec(
            name="crypto-divergence",
            description="加密货币背离信号（OKX）",
            exchange="OKX",
            required_params=["symbol"],
            param_constraints={
                "zscore": (-4.0, 4.0),
            },
            default_quantity=1.0,
        ))

        # BTC 价差监控（IB）
        self.register(StrategySpec(
            name="z120-spread",
            description="Z120 价差监控（IB）",
            exchange="IB",
            required_params=["symbol"],
            param_constraints={
                "zscore": (-4.0, 4.0),
            },
            default_quantity=1.0,
        ))

        # RB-CL 3:2:1 价差策略（IB）
        # 做多价差=买RB卖CL，做空价差=卖RB买CL
        # RB:NYMEX, multiplier=42000 (USD/gallon -> USD/barrel)
        # CL:NYMEX, multiplier=1000 (USD/barrel)
        self.register(StrategySpec(
            name="rb-cl-spread",
            description="RB-CL 3:2:1 Crack Spread — 买3份RB汽油/卖2份CL原油",
            exchange="IB",
            required_params=["zscore"],
            param_constraints={
                "zscore": (-4.0, 4.0),
                "hedge_ratio": (0.5, 5.0),
            },
            default_quantity=1.0,
            spread_symbols="RB,CL",
            direction_map={
                "long":  [("RB_LONG", "BUY")],    # 做多 crack: 买RB + 卖CL
                "short": [("RB_SHORT", "SELL")],
            },
        ))

        # PL/PA 铂钯比率 — 做空比率=卖铂买钯，做多比率=买铂卖钯
        self.register(StrategySpec(
            name="pl-pa-ratio",
            description="Platinum/Palladium Ratio — 均值回归",
            exchange="IB",
            required_params=["zscore"],
            param_constraints={"zscore": (-4.0, 4.0)},
            default_quantity=1.0,
            spread_symbols="PL,PA",
        ))

        # HO/CL 3:1 柴油价差
        self.register(StrategySpec(
            name="ho-cl-spread",
            description="HO-CL 3:1 Diesel Crack — 买3份HO卖2份CL",
            exchange="IB",
            required_params=["zscore"],
            param_constraints={"zscore": (-4.0, 4.0)},
            default_quantity=1.0,
            spread_symbols="HO,CL",
        ))

        # ── 通用配对策略（scanner 用）──────────────────────────────
        # legs 由 signal["legs"] 提供: [{"symbol": "PL", "action": "SELL", "quantity": 1.0}, ...]
        # direction 由 signal["direction"] 提供: "long" / "short"
        self.register(StrategySpec(
            name="pairs-spread",
            description="通用配对策略 — legs 由 signal 传入",
            exchange="IB",
            required_params=["zscore", "legs"],
            param_constraints={"zscore": (-4.0, 4.0)},
            default_quantity=1.0,
            spread_symbols=None,  # 动态，由 legs 决定
        ))

    def register(self, spec: StrategySpec):
        self._strategies[spec.name] = spec

    def get(self, name: str) -> Optional[StrategySpec]:
        return self._strategies.get(name)

    def list_strategies(self) -> List[str]:
        return list(self._strategies.keys())

    def validate(self, strategy_name: str, signal: dict) -> ValidationResult:
        """
        验证信号是否符合策略规格。

        Returns:
            ValidationResult: valid=True 表示通过，False 时 errors 包含拒绝原因
        """
        errors = []
        warnings = []
        spec = self._strategies.get(strategy_name)

        if spec is None:
            return ValidationResult(
                valid=False,
                errors=[f"unknown strategy: {strategy_name}. available: {self.list_strategies()}"]
            )

        # 1. 必填参数检查
        for param in spec.required_params:
            if param not in signal or signal[param] is None:
                errors.append(f"missing required param: {param}")

        # 2. 参数范围约束
        for param, (vmin, vmax) in spec.param_constraints.items():
            val = signal.get(param)
            if val is not None:
                if not (vmin <= val <= vmax):
                    errors.append(
                        f"param {param}={val} out of range [{vmin}, {vmax}] for strategy {strategy_name}"
                    )

        # 3. 方向校验（仅当提供了 direction 时检查，不提供时默认 long）
        direction = signal.get("direction", "")
        if direction and direction not in ("long", "short", "buy", "sell", "BUY", "SELL", "LONG", "SHORT"):
            errors.append(f"invalid direction: {direction}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def build_order_contexts(
        self, strategy_name: str, signal: dict
    ) -> Tuple[List[dict], str]:
        """
        将策略信号映射为一个或多个 OrderContext dict。

        Args:
            strategy_name: 策略名
            signal: 原始信号 dict

        Returns:
            (list of OrderContext kwargs, exchange_name)
        """
        spec = self._strategies[strategy_name]
        symbol = signal.get("symbol", "")
        action_raw = signal.get("direction", "")
        quantity = float(signal.get("quantity", spec.default_quantity))
        exchange = spec.exchange

        # 标准化方向
        action = "BUY" if action_raw in ("long", "buy", "LONG", "BUY") else "SELL"

        # 多腿策略：FU-LU spread
        if strategy_name == "fu-lu-spread":
            # signal["symbol"] 格式: "FUL8.SHF" (隐含做多价差) 或 "FULU_LONG"
            # direction: "long" = 做多价差 = 买FU + 卖LU
            # direction: "short" = 做空价差 = 卖FU + 买LU
            # 从 signal 中解析 FU/LU symbol（由 Agent 传入，或默认）
            fu_symbol = signal.get("fu_symbol", "FUL8.SHF")
            lu_symbol = signal.get("lu_symbol", "LUL8.INE")
            hedge_ratio = signal.get("hedge_ratio", 1.0)

            if action == "BUY":
                # 做多价差: 买FU + 卖LU
                return (
                    [
                        {
                            "symbol": fu_symbol,
                            "action": "BUY",
                            "quantity": quantity,
                            "exchange": exchange,
                            "strategy": strategy_name,
                            "zscore": signal.get("zscore"),
                            "correlation": signal.get("correlation"),
                            "hedge_ratio": hedge_ratio,
                        },
                        {
                            "symbol": lu_symbol,
                            "action": "SELL",
                            "quantity": round(quantity * hedge_ratio, 4),
                            "exchange": exchange,
                            "strategy": strategy_name,
                            "zscore": signal.get("zscore"),
                            "correlation": signal.get("correlation"),
                            "hedge_ratio": hedge_ratio,
                        },
                    ],
                    exchange,
                )
            else:
                # 做空价差: 卖FU + 买LU
                return (
                    [
                        {
                            "symbol": fu_symbol,
                            "action": "SELL",
                            "quantity": quantity,
                            "exchange": exchange,
                            "strategy": strategy_name,
                            "zscore": signal.get("zscore"),
                            "correlation": signal.get("correlation"),
                            "hedge_ratio": hedge_ratio,
                        },
                        {
                            "symbol": lu_symbol,
                            "action": "BUY",
                            "quantity": round(quantity * hedge_ratio, 4),
                            "exchange": exchange,
                            "strategy": strategy_name,
                            "zscore": signal.get("zscore"),
                            "correlation": signal.get("correlation"),
                            "hedge_ratio": hedge_ratio,
                        },
                    ],
                    exchange,
                )

        # RB-CL 3:2:1 crack spread
        if strategy_name == "rb-cl-spread":
            if action == "BUY":
                # 做多 crack: 买RB(3份) + 卖CL(2份)
                return (
                    [
                        {
                            "symbol": "RB",
                            "action": "BUY",
                            "quantity": round(3.0 * quantity, 4),
                            "exchange": "IB",
                            "strategy": strategy_name,
                            "zscore": signal.get("zscore"),
                            "spread_type": "3:2:1_crack",
                        },
                        {
                            "symbol": "CL",
                            "action": "SELL",
                            "quantity": round(2.0 * quantity, 4),
                            "exchange": "IB",
                            "strategy": strategy_name,
                            "zscore": signal.get("zscore"),
                            "spread_type": "3:2:1_crack",
                        },
                    ],
                    "IB",
                )
            else:
                # 做空 crack: 卖RB(3份) + 买CL(2份)
                return (
                    [
                        {
                            "symbol": "RB",
                            "action": "SELL",
                            "quantity": round(3.0 * quantity, 4),
                            "exchange": "IB",
                            "strategy": strategy_name,
                            "zscore": signal.get("zscore"),
                            "spread_type": "3:2:1_crack",
                        },
                        {
                            "symbol": "CL",
                            "action": "BUY",
                            "quantity": round(2.0 * quantity, 4),
                            "exchange": "IB",
                            "strategy": strategy_name,
                            "zscore": signal.get("zscore"),
                            "spread_type": "3:2:1_crack",
                        },
                    ],
                    "IB",
                )

        # PL/PA 铂钯比率 — 做空比率=卖铂买钯，做多比率=买铂卖钯
        if strategy_name == "pl-pa-ratio":
            if action == "BUY":
                return (
                    [
                        {"symbol": "PL", "action": "BUY",  "quantity": quantity,
                         "exchange": "IB", "strategy": strategy_name, "zscore": signal.get("zscore")},
                        {"symbol": "PA", "action": "SELL", "quantity": quantity,
                         "exchange": "IB", "strategy": strategy_name, "zscore": signal.get("zscore")},
                    ], "IB",
                )
            else:
                return (
                    [
                        {"symbol": "PL", "action": "SELL", "quantity": quantity,
                         "exchange": "IB", "strategy": strategy_name, "zscore": signal.get("zscore")},
                        {"symbol": "PA", "action": "BUY",  "quantity": quantity,
                         "exchange": "IB", "strategy": strategy_name, "zscore": signal.get("zscore")},
                    ], "IB",
                )

        # HO/CL 3:1 柴油价差 — 做空=卖HO买CL，做多=买HO卖CL
        if strategy_name == "ho-cl-spread":
            if action == "BUY":
                return (
                    [
                        {"symbol": "HO", "action": "BUY",  "quantity": round(3.0 * quantity, 4),
                         "exchange": "IB", "strategy": strategy_name, "zscore": signal.get("zscore")},
                        {"symbol": "CL", "action": "SELL", "quantity": round(2.0 * quantity, 4),
                         "exchange": "IB", "strategy": strategy_name, "zscore": signal.get("zscore")},
                    ], "IB",
                )
            else:
                return (
                    [
                        {"symbol": "HO", "action": "SELL", "quantity": round(3.0 * quantity, 4),
                         "exchange": "IB", "strategy": strategy_name, "zscore": signal.get("zscore")},
                        {"symbol": "CL", "action": "BUY",  "quantity": round(2.0 * quantity, 4),
                         "exchange": "IB", "strategy": strategy_name, "zscore": signal.get("zscore")},
                    ], "IB",
                )

        # ── 通用配对策略（scanner / quant-agent 用）─────────────────────
        # signal["legs"] 格式: [{"symbol": "PL", "action": "SELL", "quantity": 1.0}, ...]
        # scanner 已通过 direction_legs() 计算好每条腿的 action，直接用
        if strategy_name == "pairs-spread":
            legs = signal.get("legs", [])
            if not legs:
                # Fallback: 无 legs，单腿处理
                return (
                    [{
                        "symbol": symbol,
                        "action": action,
                        "quantity": quantity,
                        "exchange": exchange,
                        "strategy": strategy_name,
                        "zscore": signal.get("zscore"),
                    }],
                    exchange,
                )
            contexts = []
            for leg in legs:
                ctx = {
                    "symbol": leg["symbol"],
                    "action": leg.get("action", action),  # 优先用 leg 指定的 action
                    "quantity": float(leg.get("quantity", quantity)),
                    "exchange": exchange,
                    "strategy": strategy_name,
                    "zscore": signal.get("zscore"),
                }
                contexts.append(ctx)
            return (contexts, exchange)

        # 单腿策略
        return (
            [
                {
                    "symbol": symbol,
                    "action": action,
                    "quantity": quantity,
                    "exchange": exchange,
                    "strategy": strategy_name,
                    "zscore": signal.get("zscore"),
                    "correlation": signal.get("correlation"),
                }
            ],
            exchange,
        )


# 全局单例
_registry: Optional[StrategyRegistry] = None


def get_registry() -> StrategyRegistry:
    global _registry
    if _registry is None:
        _registry = StrategyRegistry()
    return _registry


# ─── ApprovedStrategyCache ────────────────────────────────────────────────────
import threading
import logging

logger = logging.getLogger(__name__)


class ApprovedStrategyCache:
    """
    轮询 quant-agent GET /api/strategies?status=APPROVED
    维护已批准 strategy_id 的内存缓存。

    quant-agent 端点返回格式:
        [
            {"strategy_id": "strat-001", "name": "PL_PA_ratio", "status": "APPROVED"},
            ...
        ]
    仅 status=="APPROVED" 的条目被缓存。
    """

    def __init__(
        self,
        agent_base_url: str | None = None,
        poll_interval_seconds: int = 300,
    ):
        """
        Args:
            agent_base_url: quant-agent API 根地址，如 "http://localhost:9000"。
                           None 时 refresh() 为空操作（本地/离线模式）。
            poll_interval_seconds: 轮询间隔，默认 5 分钟。
        """
        self._base_url = agent_base_url.rstrip("/") if agent_base_url else None
        self._poll_interval = poll_interval_seconds
        self._approved_ids: set[str] = set()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._poll_thread: threading.Thread | None = None

    # ── Public read API ────────────────────────────────────────────────────────

    def is_approved(self, strategy_id: str) -> bool:
        """查询 strategy_id 是否已批准（从缓存）"""
        if not strategy_id:
            return False  # 无 strategy_id → 跳过检查
        with self._lock:
            return strategy_id in self._approved_ids

    def get_approved(self) -> set[str]:
        """返回当前已批准策略 ID 集合（副本）"""
        with self._lock:
            return set(self._approved_ids)

    # ── Cache management ───────────────────────────────────────────────────────

    def set_approved(self, ids: set[str]) -> None:
        """手动设置已批准集合（测试 / 外部注入）"""
        with self._lock:
            self._approved_ids = set(ids)

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._approved_ids.clear()

    # ── Polling ───────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """
        从 quant-agent 拉取最新批准列表并更新缓存。
        HTTP 错误时跳过更新，保留上一次缓存内容。
        """
        if not self._base_url:
            return

        url = f"{self._base_url}/api/strategies?status=APPROVED"
        try:
            import requests
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            new_ids: set[str] = set()
            for item in data:
                strategy_id = item.get("id") or item.get("strategy_id", "")
                passes = item.get("passes_gates", False)
                status = item.get("status", "")
                if (passes or status == "APPROVED") and strategy_id:
                    new_ids.add(strategy_id)
            with self._lock:
                self._approved_ids = new_ids
            logger.info("[ApprovedCache] Refreshed %d approved strategies", len(new_ids))
        except Exception as exc:
            logger.warning("[ApprovedCache] Refresh failed (keeping stale cache): %s", exc)

    def start_polling(self) -> None:
        """启动后台轮询线程"""
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._stop_event.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        logger.info("[ApprovedCache] Polling started (interval=%ds)", self._poll_interval)

    def stop_polling(self) -> None:
        """停止后台轮询"""
        self._stop_event.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
            self._poll_thread = None

    def _poll_loop(self) -> None:
        """后台轮询循环"""
        import time
        while not self._stop_event.wait(self._poll_interval):
            self.refresh()


# 全局单例（惰性初始化）
_approved_cache: ApprovedStrategyCache | None = None


def get_approved_cache() -> ApprovedStrategyCache:
    """返回全局 ApprovedStrategyCache 实例"""
    global _approved_cache
    if _approved_cache is None:
        # 从环境变量读取 quant-agent 地址（可选）
        import os as _os
        _url = _os.environ.get("QUANT_AGENT_API_URL")
        _approved_cache = ApprovedStrategyCache(agent_base_url=_url)
    return _approved_cache
