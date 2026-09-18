"""内存 tick 存储：最新价表 + 环形缓冲 + SSE 订阅者发布。

读快照不加锁竞争热路径外的 IO（微秒级）；SSE 用 queue 广播，
慢消费者按队列容量自动丢弃旧 tick（不阻塞行情回调线程）。
"""
from __future__ import annotations

import queue
import threading
import time
from collections import defaultdict, deque
from typing import Iterable

from .schema import Tick

_RING = 2048          # 每合约环形缓冲
_SSE_QUEUE = 4096     # 每个 SSE 消费者最多缓存 tick 数
_CATCHUP = 300        # SSE 新连接每合约补发近期 tick 上限（客户端按 ts 去重）


class TickStore:
    def __init__(self, ring: int = _RING) -> None:
        self._lock = threading.RLock()
        self._latest: dict[tuple[str, str], Tick] = {}
        self._rings: dict[tuple[str, str], deque[Tick]] = defaultdict(lambda: deque(maxlen=ring))
        self._subscribers: list[queue.Queue] = []

    # ── 写入（MdApi 回调线程）────────────────────────────
    def publish(self, tick: Tick) -> None:
        with self._lock:
            self._latest[tick.key] = tick
            self._rings[tick.key].append(tick)
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(tick)
            except queue.Full:
                try:
                    q.get_nowait()       # 丢最旧，保最新
                    q.put_nowait(tick)
                except queue.Empty:
                    pass

    # ── 读快照（无流控、微秒级）──────────────────────────
    def snapshot(self, profile: str, instrument: str) -> Tick | None:
        with self._lock:
            return self._latest.get((profile, instrument))

    def latest(self, profile: str, instruments: Iterable[str] | None = None) -> list[dict]:
        with self._lock:
            if instruments is None:
                return [t.to_dict() for (p, _i), t in self._latest.items() if p == profile]
            wanted = set(instruments)
            return [t.to_dict() for (p, iid), t in self._latest.items()
                    if p == profile and iid in wanted]

    def recent(self, profile: str, instrument: str, limit: int = 100) -> list[dict]:
        with self._lock:
            dq = self._rings.get((profile, instrument))
            if dq is None:
                return []
            return [t.to_dict() for t in list(dq)[-limit:]]

    # ── SSE 订阅 ────────────────────────────────────────
    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=_SSE_QUEUE)
        with self._lock:
            self._subscribers.append(q)
        return q

    def catch_up(self, wanted: set[tuple[str, str]] | None = None,
                 limit: int = _CATCHUP) -> list["Tick"]:
        """SSE 新连接补发：按时间顺序返回各合约环形缓冲内最近的 tick。

        解决「连接建立前/瞬间错过 tick 突发」竞态；与实时帧的重叠由客户端去重。
        """
        with self._lock:
            ticks: list[Tick] = []
            for (profile, iid), dq in self._rings.items():
                if wanted is not None and (profile, iid) not in wanted:
                    continue
                ticks.extend(list(dq)[-limit:])
        ticks.sort(key=lambda t: (t.ts_recv or 0.0, t.instrument_id))
        return ticks

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def drain(self, q: queue.Queue, instruments: set[tuple[str, str]] | None,
              timeout: float = 15.0) -> list[Tick]:
        """阻塞等一批 tick；instruments 为 None 时不过滤。返回列表（心跳时为空）。"""
        try:
            first = q.get(timeout=timeout)
        except queue.Empty:
            return []
        batch = [first]
        while True:
            try:
                batch.append(q.get_nowait())
            except queue.Empty:
                break
        if instruments is None:
            return batch
        return [t for t in batch if t.key in instruments]

    def stats(self) -> dict:
        with self._lock:
            return {"instruments": len(self._latest), "sse_clients": len(self._subscribers)}
