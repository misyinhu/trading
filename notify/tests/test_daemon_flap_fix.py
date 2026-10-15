"""2026-10-16 8h daemon 抽风修复回归：
- daemon 登录超时/断线不再 Release api（跨线程 Release 原生 abort 是抽风根因）
- bridge 重启 daemon 有 60s backoff
- event_writer 按 order_id/trade_id 参与幂等（多笔成交不丢）
"""
from __future__ import annotations

import inspect
import json, os


def test_daemon_connect_never_releases_api():
    from ctp_client import ctp_daemon
    src = inspect.getsource(ctp_daemon._Session._connect)
    assert ".Release(" not in src, "_connect 不得再调用 api.Release()"


def test_force_reconnect_never_releases_api():
    from ctp_client import ctp_daemon
    src = inspect.getsource(ctp_daemon._Session._force_reconnect)
    assert ".Release(" not in src, "_force_reconnect 不得再调用 api.Release()"


def test_bridge_daemon_restart_has_backoff():
    from notify import webhook_bridge
    src = inspect.getsource(webhook_bridge._ctp_daemon_ensure)
    assert "_ctp_daemon_last_start" in src
    assert webhook_bridge._CTP_DAEMON_RESTART_BACKOFF >= 60.0


def test_on_rtn_trade_writes_back():
    from ctp_client import ctp_worker
    src = inspect.getsource(ctp_worker.TraderSpi.OnRtnTrade)
    assert "write_event_callback" in src
    assert "ORDER_FILLED" in src


class TestDedupWithOrderKey:
    def test_same_order_deduped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EVENT_WRITE_PATH", str(tmp_path / "e.jsonl"))
        monkeypatch.setenv("EVENT_SEQ_FILE", str(tmp_path / "e.seq"))
        from notify.event_writer import write_event
        write_event("sig1", "ORDER_FILLED", {"order_id": "A", "price": 1})
        r = write_event("sig1", "ORDER_FILLED", {"order_id": "A", "price": 2})
        assert r["already_recorded"] is True

    def test_different_orders_both_recorded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EVENT_WRITE_PATH", str(tmp_path / "e.jsonl"))
        monkeypatch.setenv("EVENT_SEQ_FILE", str(tmp_path / "e.seq"))
        from notify.event_writer import write_event
        write_event("sig1", "ORDER_FILLED", {"order_id": "A", "price": 1})
        r = write_event("sig1", "ORDER_FILLED", {"order_id": "B", "price": 2})
        assert r["already_recorded"] is False
        assert r["recorded"] is True
