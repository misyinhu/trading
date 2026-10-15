"""The 3h time-stop reminder must be an event, not a per-tick state dump.

Incident (2026-10-15): the audit-mode branch re-sent a Feishu message on every
30s tick with no cap ("将持续提醒直至平仓或解除"). Two lots sitting past the line
produced ~240 messages/hour; the audit log held 18,030 duplicate `would_close`
rows since 2026-09-21.

The storm was previously masked: the false-flat reconcile bug reset every lot's
clock before it ever reached 3h. Once that was fixed the latent bug surfaced, so
this pins the behaviour independently of the reconcile fix.
"""
from __future__ import annotations

import importlib
import sys
from datetime import timedelta
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture()
def tsmod(monkeypatch, tmp_path):
    import notify.feishu as feishu

    sent: list[str] = []
    monkeypatch.setattr(feishu, "FeishuNotifier",
                        type("N", (), {"send_message": lambda self, t: sent.append(t)}))
    monkeypatch.setenv("TIME_STOP_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("TIME_STOP_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("TIME_STOP_MODE", "audit")
    monkeypatch.setenv("TIME_STOP_TICK_SEC", "30")

    sys.modules.pop("live_gateway.time_stop", None)
    mod = importlib.import_module("live_gateway.time_stop")
    mod.sent = sent  # type: ignore[attr-defined]
    mod.AUDITED = []    # type: ignore[attr-defined]
    # Patch on the CLASS: _evaluate calls self._audit(...), which resolves to
    # the class attribute, not the module-level name.
    mod.TimeStopWatcher._audit = (  # type: ignore[attr-defined]
        lambda self, kind, payload: mod.AUDITED.append((kind, payload)))
    yield mod


def _base_lot(now, symbol="MNQ", root="MNQ", qty=1.0, hours=9):
    """A fresh lot dict. Never copy an existing one — that carries the
    _3h_notified_sent flag across and silently disables the test."""
    dt = (now - timedelta(hours=hours)).isoformat()
    return {"symbol": symbol, "root": root, "grp": "index", "dir": "long",
            "qty": qty, "market": "ib", "sec_type": "FUT",
            "open_dt": dt, "clock_dt": dt,
            "warned": True, "acted": False, "uw": 0, "tot": 0,
            "last_pnl": None, "light": None, "exec": []}


def _watcher(tsmod, now, lots=None):
    w = tsmod.TimeStopWatcher.__new__(tsmod.TimeStopWatcher)
    w.lots = lots if lots is not None else [_base_lot(now)]
    w.desync_alerted = set()
    w.manual = {}
    w.mgr = None
    return w


def test_three_hour_alert_fires_once(tsmod):
    now = tsmod._now()
    w = _watcher(tsmod, now)

    w._evaluate(now, can_trade=True, bars={}, only_market="ib")

    assert len(tsmod.sent) == 1, f"expected one alert, got {tsmod.sent}"
    assert "3 小时离场提醒" in tsmod.sent[0]
    assert [k for k, _ in tsmod.AUDITED] == ["would_close"]


def test_storm_does_not_resume_on_later_ticks(tsmod):
    """The regression itself: 200 ticks must not become 200 messages."""
    now = tsmod._now()
    w = _watcher(tsmod, now)

    w._evaluate(now, can_trade=True, bars={}, only_market="ib")   # cross the line
    for i in range(200):
        w._evaluate(now + timedelta(seconds=30 * (i + 1)),
                    can_trade=True, bars={}, only_market="ib")

    assert len(tsmod.sent) == 1, \
        f"one crossing must not become {len(tsmod.sent)} messages"
    assert len(tsmod.AUDITED) == 1, \
        f"audit must record the crossing once, got {len(tsmod.AUDITED)}"


def test_two_lots_each_alert_once_not_per_pair(tsmod):
    now = tsmod._now()
    w = _watcher(tsmod, now, lots=[_base_lot(now),
                                  _base_lot(now, "XAGUSD", "XAGUSD", 200.0)])

    for i in range(50):
        w._evaluate(now + timedelta(seconds=30 * i),
                    can_trade=True, bars={}, only_market="ib")

    assert len(tsmod.sent) == 2, f"one per lot expected, got {len(tsmod.sent)}"
    assert len(tsmod.sent) == 2, f"one per lot expected, got {tsmod.sent}"
    assert sum("MNQ" in m for m in tsmod.sent) == 1
    assert sum("XAGUSD" in m for m in tsmod.sent) == 1


def test_flag_survives_restart(tsmod, monkeypatch, tmp_path):
    """_save()/_load() must carry the flag, or every restart re-spikes it."""
    now = tsmod._now()
    w = _watcher(tsmod, now)
    w._evaluate(now, can_trade=True, bars={}, only_market="ib")
    assert len(tsmod.sent) == 1

    w.seen_exec = set()
    w._flat_confirm = {}
    w._snap_down = False
    w._snap_fail_reason = ""
    w._adopted_this_tick = set()
    w._save()

    fresh = tsmod.TimeStopWatcher.__new__(tsmod.TimeStopWatcher)
    fresh.lots = []
    fresh.seen_exec = set()
    fresh.manual = {}
    fresh.desync_alerted = set()
    fresh._flat_confirm = {}
    fresh._snap_down = False
    fresh._snap_fail_reason = ""
    fresh.last_tick = {}
    fresh._load()

    assert fresh.lots[0].get("_3h_notified_sent") is True, \
        "crossing marker must survive a restart"
    fresh._evaluate(now, can_trade=True, bars={}, only_market="ib")
    assert len(tsmod.sent) == 1, "restart must not re-alert an already-alerted lot"


def test_fresh_lot_still_alerts(tsmod):
    """Silencing must be scoped to the lot, not global."""
    now = tsmod._now()
    w = _watcher(tsmod, now)
    w._evaluate(now, can_trade=True, bars={}, only_market="ib")
    assert len(tsmod.sent) == 1

    w.lots.append(_base_lot(now, "ES", "ES", 1.0))
    w._evaluate(now, can_trade=True, bars={}, only_market="ib")

    assert len(tsmod.sent) == 2, "a newly crossed lot must still alert"
    assert "ES" in tsmod.sent[1]


def test_two_hour_warn_still_fires_once(tsmod):
    """The 2h guard must keep working; only the 3h repeat was the defect."""
    now = tsmod._now()
    w = _watcher(tsmod, now)
    w.lots[0]["clock_dt"] = (now - timedelta(hours=2, minutes=5)).isoformat()
    w.lots[0]["open_dt"] = w.lots[0]["clock_dt"]
    w.lots[0]["warned"] = False

    for i in range(20):
        w._evaluate(now + timedelta(seconds=30 * i),
                    can_trade=True, bars={}, only_market="ib")

    warns = [m for m in tsmod.sent if "2 小时警戒" in m]
    assert len(warns) == 1, f"2h warn must fire once, got {len(warns)}"
