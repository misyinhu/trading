"""每 profile 一个常驻 MdApi worker：登录、订阅、断线重连+补订阅、健康状态。"""
from __future__ import annotations

import threading
import time
from typing import Any

from .connector import BaseConnector, create_connector
from .schema import Tick
from .store import TickStore
from .subscriptions import SubscriptionStore

_RECONNECT_MIN = 1.0
_RECONNECT_MAX = 30.0


class _ProfileWorker:
    def __init__(self, profile: str, cfg: dict, store: TickStore,
                 subs: SubscriptionStore) -> None:
        self.profile = profile
        self.cfg = cfg
        self.store = store
        self.subs = subs
        self.state = "init"
        self.state_msg = ""
        self.last_state_at = time.time()
        self.last_tick_at: float | None = None
        self.last_tick_iid = ""
        self.tick_count = 0
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._connector: BaseConnector | None = None
        self._monitor: threading.Thread | None = None

    # ── 状态 ────────────────────────────────────────────
    def _set_state(self, state: str, msg: str = "") -> None:
        with self._lock:
            self.state, self.state_msg, self.last_state_at = state, msg, time.time()

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self.state,
                "message": self.state_msg,
                "subscriptions": sorted(self.subs.get(self.profile)),
                "tick_count": self.tick_count,
                "last_tick_at": self.last_tick_at,
                "last_tick_instrument": self.last_tick_iid,
                "last_state_at": self.last_state_at,
            }

    # ── 生命周期 ────────────────────────────────────────
    def start(self) -> None:
        self._stop.clear()
        self._monitor = threading.Thread(target=self._run_forever, daemon=True,
                                         name=f"md-{self.profile}")
        self._monitor.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._connector is not None:
                self._connector.stop()
        except Exception:
            pass

    def _new_connector(self) -> BaseConnector:
        conn = create_connector(self.cfg.get("kind", "ctp"), self.profile, self.cfg)
        conn.on_status = self._on_status
        conn.on_tick = self._on_tick
        return conn

    def _run_forever(self) -> None:
        backoff = _RECONNECT_MIN
        while not self._stop.is_set():
            try:
                conn = self._new_connector()
                self._connector = conn
                conn.subscribe(list(self.subs.get(self.profile)))
                conn.start()
            except Exception as e:  # 绑定缺失/前置错误
                self._set_state("error", f"start failed: {e}")
            # 监控循环：连接存活且已登录时等待；掉线后退避重连
            while not self._stop.is_set():
                time.sleep(1.0)
                # idle=回放播完保活；只有真实掉线/错误才重连
                if self.state in ("disconnected", "error"):
                    break
                # 心跳：logined 但长时间无 tick 不主动断（非交易时段无推送属正常）
            try:
                if self._connector is not None:
                    self._connector.stop()
            except Exception:
                pass
            self._set_state("disconnected", f"reconnect in {backoff:.0f}s")
            self._stop.wait(backoff)
            backoff = min(_RECONNECT_MAX, backoff * 2)
            # 连上一次后重置退避
            if self.state == "logined":
                backoff = _RECONNECT_MIN

    def _on_status(self, state: str, msg: str) -> None:
        self._set_state(state, msg)

    def _on_tick(self, tick: Tick) -> None:
        with self._lock:
            self.last_tick_at = time.time()
            self.last_tick_iid = tick.instrument_id
            self.tick_count += 1
        self.store.publish(tick)

    # ── 订阅变更（对外）────────────────────────────────
    def set_subscriptions(self, add=None, remove=None) -> set[str]:
        new_set = self.subs.update(self.profile, add, remove)
        conn = self._connector
        if conn is not None and self.state == "logined":
            if add:
                conn.subscribe(list(add))
            if remove and hasattr(conn, "unsubscribe"):
                conn.unsubscribe(list(remove))
        return new_set


class MdWorkerManager:
    def __init__(self, profiles_cfg: dict, store: TickStore,
                 state_path: str) -> None:
        self.store = store
        self.subs = SubscriptionStore(state_path)
        self.workers: dict[str, _ProfileWorker] = {}
        for profile, cfg in profiles_cfg.items():
            self.workers[profile] = _ProfileWorker(profile, cfg, store, self.subs)

    def start(self) -> None:
        for w in self.workers.values():
            w.start()

    def stop(self) -> None:
        for w in self.workers.values():
            w.stop()

    def profiles(self) -> list[str]:
        return list(self.workers)

    def subscribe(self, profile: str, instruments: list[str]) -> set[str]:
        return self._require(profile).set_subscriptions(add=instruments)

    def unsubscribe(self, profile: str, instruments: list[str]) -> set[str]:
        return self._require(profile).set_subscriptions(remove=instruments)

    def health(self) -> dict[str, Any]:
        return {p: w.health() for p, w in self.workers.items()}

    def _require(self, profile: str) -> _ProfileWorker:
        if profile not in self.workers:
            raise KeyError(f"unknown profile: {profile}")
        return self.workers[profile]
