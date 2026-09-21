#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CTP 实时 5m bar 聚合（单常驻 MdApi 线程，仅订阅当前持仓品种）。

性能设计：
- 一个 MdApi 连接 + 一个回调线程；tick 回调 O(1) 更新当前 bar（dict 查找），
  不存 tick 历史、不落盘、不做重计算。
- 订阅集合由 set_targets() 按当前持仓动态增删，非持仓品种零流量。
- bars 存内存 deque（每品种 maxlen 上限），供 watcher 只读快照；
  线程边界：MdApi 线程写，watcher tick 线程读，deque/bar 用单锁保护，
  读路径只做一次浅拷贝（根数少，开销可忽略）。

bar 时间戳为 UTC，右标签对齐 5 分钟（00,05,...,55）。
夜盘跨零点时按交易所 tick 的自然时间切桶，不依赖交易日历。
"""
from __future__ import annotations

import os
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

MAX_BARS_PER_SYM = int(os.environ.get("CTP_BARS_MAX", "600"))
REMOVE_GRACE_SEC = float(os.environ.get("CTP_REMOVE_GRACE_SEC", "90"))


def _floor_5m(epoch_ms: int) -> int:
    return (int(epoch_ms) // 300000) * 300000


class CtpBarsFeed:
    """对外：start(config) / set_targets(symbols) / bars(sym)。"""

    def __init__(self):
        self._lock = threading.RLock()
        self._targets: set[str] = set()
        self._wanted: set[str] = set()
        self._missing_since: dict[str, float] = {}
        self._cur: dict[str, dict] = {}          # sym -> 进行中 bar
        self._done: dict[str, deque] = {}        # sym -> 已收盘 bar deque
        self._conn = None
        self._cfg = None
        self._started = False
        self._last_tick_at = 0.0
        self._status = "idle"
        self._error = ""
        self._tick_error = ""
        self._push_count = 0

    # ── 生命周期 ──────────────────────────────────────────────────────────
    def start(self, cfg: dict):
        if self._started:
            return
        self._cfg = cfg
        self._started = True
        worker = threading.Thread(target=self._run, name="CtpBarsMd", daemon=True)
        worker.start()

    def stop(self):
        with self._lock:
            conn = self._conn
        if conn is not None:
            try:
                conn._api.Release()
            except Exception:  # noqa: BLE001
                pass

    def _run(self):
        # 在 MdApi 线程内完成连接建立（SWIG 回调与创建同线程更稳）
        try:
            self._connect()
        except Exception as e:  # noqa: BLE001
            with self._lock:
                self._status = "error"
                self._error = str(e)
            return
        while True:
            time.sleep(1.0)

    def _connect(self):
        root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(root / "ctp_client"))
        from ctp_connector import CtpConfig, CtpMdConnector

        cfg = self._cfg
        ctpcfg = CtpConfig(
            md_server=cfg["md_server"], td_server=cfg.get("td_server", ""),
            broker_id=cfg["broker_id"], user_id=cfg.get("user", ""),
            password=cfg.get("password", ""),
            auth_code=cfg.get("auth_code", ""), app_id=cfg.get("app_id", ""))
        with self._lock:
            self._status = "connecting"
        conn = CtpMdConnector(ctpcfg)
        conn.add_tick_handler(self._on_tick)
        with self._lock:
            self._conn = conn
            # 连接建立后若已有目标，订阅在登录回调里补发
            conn.subscribe(list(self._targets))

    # ── 订阅管理（watcher 按持仓调用）────────────────────────────────────
    def set_targets(self, symbols) -> None:
        """按当前持仓更新订阅。

        持仓查询走柜台单交易连接，偶发返回空时不能立刻退订——否则 bar 桶被
        反复清空重建，永远无法跨 5 分钟切桶。缺失品种进入宽限计时，连续缺失
        超过 REMOVE_GRACE_SEC 才真正 UnSubscribe 并丢弃 bar。
        """
        wanted = {str(s) for s in symbols if s}
        now = time.time()
        with self._lock:
            self._wanted = set(wanted)
            conn = self._conn

            added = [s for s in wanted if s not in self._targets]
            if added and conn is not None:
                conn.subscribe(added)
            self._targets.update(added)

            for s in list(self._missing_since):
                if s in wanted:
                    self._missing_since.pop(s, None)

            for s in list(self._targets - wanted):
                since = self._missing_since.get(s)
                if since is None:
                    self._missing_since[s] = now
                    continue
                if now - since < REMOVE_GRACE_SEC:
                    continue
                if conn is not None:
                    try:
                        from ctp_connector import _norm_md_symbols
                        conn._api.UnSubscribeMarketData(
                            _norm_md_symbols([s]), 1)
                    except Exception:  # noqa: BLE001
                        pass
                self._cur.pop(s, None)
                self._targets.discard(s)
                self._missing_since.pop(s, None)

    # ── tick → bar（O(1)）───────────────────────────────────────────────
    def _on_tick(self, p):
        try:
            sym = str(getattr(p, "InstrumentID"))
            px = float(getattr(p, "LastPrice"))
            if not (px > 0):
                return
            # CTP tick 无直接毫秒时间戳字段，用本机墙钟（交易线程，足够准）
            now_ms = int(time.time() * 1000)
        except Exception as tick_exc:  # noqa: BLE001
            self._tick_error = str(tick_exc)
            return

        bucket = _floor_5m(now_ms)
        with self._lock:
            self._last_tick_at = time.time()
            bar = self._cur.get(sym)
            if bar is None or bar["bucket"] != bucket:
                if bar is not None:
                    self._push_done(sym, bar)
                bar = {"bucket": bucket, "o": px, "h": px, "l": px, "c": px}
                self._cur[sym] = bar
            else:
                if px > bar["h"]:
                    bar["h"] = px
                if px < bar["l"]:
                    bar["l"] = px
                bar["c"] = px

    def _push_done(self, sym: str, bar: dict):
        self._push_count += 1
        dq = self._done.get(sym)
        if dq is None:
            dq = deque(maxlen=MAX_BARS_PER_SYM)
            self._done[sym] = dq
        dq.append(bar)

    # ── 只读快照（watcher 用）───────────────────────────────────────────
    def bars(self, sym: str):
        """返回 [{ts(epoch s UTC),o,h,l,c}] newest-last；含进行中 bar。"""
        with self._lock:
            out = []
            dq = self._done.get(sym)
            if dq is not None:
                out.extend(dq)
            cur = self._cur.get(sym)
            if cur is not None:
                out.append(cur)
        return [{
            "ts": b["bucket"] // 1000,
            "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"],
        } for b in out]

    def stats(self) -> dict:
        with self._lock:
            now = time.time()
            return {
                "status": (self._conn.status.value
                           if self._conn is not None else self._status),
                "wanted": sorted(self._wanted),
                "targets": sorted(self._targets),
                "missing": {s: round(now - t, 1)
                            for s, t in self._missing_since.items()},
                "symbols_bars": {s: len(dq) for s, dq in self._done.items()},
                "last_tick_at": self._last_tick_at or None,
                "tick_error": self._tick_error or None,
                "cur_keys": sorted(self._cur.keys()),
                "done_keys": {k: len(v) for k, v in self._done.items()},
                "push_count": self._push_count,
                "error": self._error,
            }
