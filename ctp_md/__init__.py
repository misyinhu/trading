"""CTP MdApi 常驻行情 worker（trading 服务侧，部署到 winclaw）。

模块划分：
- schema:        OnRtnDepthMarketData 原始字段 -> 统一 tick schema
- store:         内存最新 tick 表 + 环形缓冲 + SSE 发布
- subscriptions: 每 profile 订阅集持久化
- connector:     MdApi 连接适配（真实 CTP 绑定 / 离线回放）
- worker:        每 profile 常驻 worker（登录/订阅/断线重连/状态）
- server:        Flask 蓝图（snapshot / stream / subscribe / health）
"""
from .schema import Tick, tick_from_ctp
from .store import TickStore
from .subscriptions import SubscriptionStore
from .worker import MdWorkerManager

__all__ = [
    "Tick", "tick_from_ctp", "TickStore", "SubscriptionStore", "MdWorkerManager",
]
