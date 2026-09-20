"""signal-callback-writeback（H8）测试：trading 事件回写幂等验证。"""
from __future__ import annotations

import json, os, tempfile
from pathlib import Path
import pytest
from notify.event_writer import write_event

class TestIdempotency:
    @pytest.fixture
    def env(self, tmp_path):
        p = tmp_path / "e.jsonl"
        s = tmp_path / "e.seq"
        os.environ["EVENT_WRITE_PATH"] = str(p)
        os.environ["EVENT_SEQ_FILE"] = str(s)
        yield p
        for k in ("EVENT_WRITE_PATH", "EVENT_SEQ_FILE"):
            os.environ.pop(k, None)

    def test_first_write_recorded(self, env):
        r = write_event("sig_001", "ORDER_FILLED", {"price": 100.0})
        assert r["recorded"] is True
        assert r["already_recorded"] is False

    def test_duplicate_rejected(self, env):
        write_event("sig_001", "ORDER_FILLED", {})
        r = write_event("sig_001", "ORDER_FILLED", {})
        assert r["already_recorded"] is True
        lines = [l for l in env.read_text().strip().split("\n") if l]
        assert len(lines) == 1

    def test_different_event_not_idempotent(self, env):
        write_event("sig_001", "ORDER_PLACED", {})
        r = write_event("sig_001", "ORDER_FILLED", {})
        assert r["already_recorded"] is False

    def test_format_fields(self, env):
        write_event("sig_001", "TRIGGER_FIRED", {"trigger": "daily_loss"})
        data = json.loads(env.read_text().split("\n")[0])
        assert data["type"] == "TRIGGER_FIRED"
        assert data["data"]["signal_id"] == "sig_001"
        assert "seq" in data
        assert "ts" in data
