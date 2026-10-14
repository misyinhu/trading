"""Regression tests for time_stop reconcile: an unreadable counter snapshot
must never be read as "flat".

Incident (2026-10-15): commit 355faf5 changed the failed-snapshot branch from
`can_trade = False` to `_reconcile([])`. An empty list makes every tracked lot
look flat, so one IB timeout deleted the live MNQ position's tracking record
and pushed a false "账户净持仓已归零" to Feishu. The position stayed open at the
counter while leaving the 2h/3h time stop, and the next adopt re-armed its
clock from zero.

Discriminator under test: IB omits flat contracts from positions(), so
"flat" and "read failed" produce identical data. Only the success/failure of
the read itself separates them — plus consecutive agreement before acting.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture()
def tsmod(monkeypatch, tmp_path):
    """time_stop module isolated onto temp state/audit files, notify captured."""
    import notify.feishu as feishu

    sent: list[str] = []

    class FakeNotifier:
        def send_message(self, text):
            sent.append(text)

    monkeypatch.setattr(feishu, "FeishuNotifier", FakeNotifier)
    monkeypatch.setenv("TIME_STOP_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("TIME_STOP_AUDIT", str(tmp_path / "audit.jsonl"))

    sys.modules.pop("live_gateway.time_stop", None)
    mod = importlib.import_module("live_gateway.time_stop")
    mod.sent = sent  # type: ignore[attr-defined]
    yield mod


def _watcher(tsmod, lots_spec):
    """Build a watcher with hand-built IB lots and no external manager."""
    w = tsmod.TimeStopWatcher.__new__(tsmod.TimeStopWatcher)
    w.lots = [dict(symbol=sym, root=sym, qty=qty, market="ib",
                   **{k: v for k, v in extra.items()})
              for sym, qty, extra in lots_spec]
    w.seen_exec = set()
    w.desync_alerted = set()
    w.manual = {f"ib:{sym}": "false" for sym, _q, _e in lots_spec}
    w._flat_confirm = {}
    w._snap_fail_notified_at = 0.0
    w._snap_fail_reason = ""
    w.last_tick = {}
    return w


def _flat_read(symbol, qty):
    """A successful snapshot row. IB omits flat contracts, so a real flat
    position is represented by the symbol being absent, not by qty=0."""
    return {"symbol": symbol, "position": qty}


# ── the incident ────────────────────────────────────────────────────
def test_failed_snapshot_does_not_clear_open_position(tsmod):
    """snapshot_ok=False must leave the MNQ lot intact and can_trade False."""
    w = _watcher(tsmod, [("MNQ", 2, {})])

    can_trade = w._reconcile([], snapshot_ok=False)

    assert len(w.lots) == 1, "failed read must not delete a live position"
    assert w.lots[0]["symbol"] == "MNQ"
    assert can_trade is False, "unknown positions must fail closed"


def test_failed_snapshot_never_says_closed(tsmod):
    """The wording must not resemble a close — that is what misled the owner."""
    w = _watcher(tsmod, [("MNQ", 2, {})])

    w._reconcile([], snapshot_ok=False)

    assert tsmod.sent, "a failed read during an open position must be reported"
    assert not any("归零" in m for m in tsmod.sent), \
        f"failed read must not claim a close: {tsmod.sent}"
    assert any("未知" in m for m in tsmod.sent), \
        f"failed read must state positions are unknown: {tsmod.sent}"


def test_failed_snapshot_is_rate_limited(tsmod):
    """A 30s tick must not produce one Feishu message per tick during an outage."""
    w = _watcher(tsmod, [("MNQ", 2, {})])

    for _ in range(10):
        w._reconcile([], snapshot_ok=False)

    assert len(tsmod.sent) == 1, f"outage should notify once, got {tsmod.sent}"


def test_failed_snapshot_makes_no_per_symbol_claim(tsmod):
    """A total read failure says nothing about any individual symbol.

    This is the assertion that pins the health gate itself. Without it, the
    debounce alone would still stop the mass delete while the code quietly
    degraded into the per-symbol evidence path — parking every symbol in
    desync_alerted and telling the operator a per-symbol 1/2 story about a feed
    that never answered at all.
    """
    w = _watcher(tsmod, [("MNQ", 2, {}), ("ES", 1, {})])

    w._reconcile([], snapshot_ok=False)

    assert w.desync_alerted == set(), \
        "an unreadable feed cannot implicate a specific symbol"
    assert w._flat_confirm == {}, "no symbol may enter the confirm chain"
    assert any("快照读取失败" in m for m in tsmod.sent), \
        f"failure must be reported as a feed outage: {tsmod.sent}"
    assert not any("快照读数为 0" in m for m in tsmod.sent), \
        "a dead feed must not masquerade as a per-symbol zero read"


# ── the debounce ────────────────────────────────────────────────────
def test_single_successful_zero_read_does_not_clear(tsmod):
    """One empty-but-successful read is not enough to drop tracking state.

    ES stays in the snapshot on purpose: the read demonstrably came back alive
    with data for a sibling symbol, which is exactly the case where MNQ's
    absence *looks* authoritative but still only warrants one confirmation.
    """
    w = _watcher(tsmod, [("MNQ", 2, {}), ("ES", 1, {})])

    can_trade = w._reconcile([_flat_read("ES", 1)], snapshot_ok=True)

    assert any(l["symbol"] == "MNQ" for l in w.lots), \
        "one confirmation must not clear"
    assert w._flat_confirm["MNQ"] == 1
    assert "MNQ" in w.desync_alerted, \
        "ambiguous state must pause that symbol's time stop"
    assert can_trade is False, "ambiguous state must fail closed"


def test_two_consecutive_zero_reads_clear(tsmod):
    """A genuine close still gets pruned — after the second confirmation."""
    w = _watcher(tsmod, [("MNQ", 2, {}), ("ES", 1, {})])

    w._reconcile([_flat_read("ES", 1)], snapshot_ok=True)
    can_trade = w._reconcile([_flat_read("ES", 1)], snapshot_ok=True)

    assert [l["symbol"] for l in w.lots] == ["ES"], "confirmed flat pruned"
    assert w._flat_confirm == {}, "confirmation must be consumed"
    assert w.manual.get("ib:MNQ") is None, "stale hedge flag must be dropped"
    assert can_trade is True
    assert any("连续 2 次快照确认" in m for m in tsmod.sent)


def test_pending_confirmation_is_announced_as_pending(tsmod):
    """The halfway alert must not read as a close either."""
    w = _watcher(tsmod, [("MNQ", 2, {}), ("ES", 1, {})])

    w._reconcile([_flat_read("ES", 1)], snapshot_ok=True)

    assert not any("归零" in m for m in tsmod.sent)
    assert any("1/2" in m for m in tsmod.sent), tsmod.sent


def test_position_returning_breaks_the_chain(tsmod):
    """A re-appearing position must reset the count, not stack on it."""
    w = _watcher(tsmod, [("MNQ", 2, {})])

    w._reconcile([], snapshot_ok=True)
    assert w._flat_confirm["MNQ"] == 1

    w._reconcile([_flat_read("MNQ", 2)], snapshot_ok=True)
    assert "MNQ" not in w._flat_confirm, "healthy read must break the chain"

    w._reconcile([], snapshot_ok=True)
    assert len(w.lots) == 1, "count must restart from 1, not resume at 2"
    assert w._flat_confirm["MNQ"] == 1


def test_failed_snapshot_between_confirmations_resets(tmp_path):
    """Failure is not evidence: it must not let a stale 1/2 become 2/2."""
    wmod = None
    sys.path.insert(0, str(_ROOT))
    import notify.feishu as feishu

    sent: list[str] = []
    monkey = pytest.MonkeyPatch()
    monkey.setattr(feishu, "FeishuNotifier",
                   type("N", (), {"send_message": lambda self, t: sent.append(t)}))
    monkey.setenv("TIME_STOP_STATE", str(tmp_path / "s.json"))
    monkey.setenv("TIME_STOP_AUDIT", str(tmp_path / "a.jsonl"))
    sys.modules.pop("live_gateway.time_stop", None)
    wmod = importlib.import_module("live_gateway.time_stop")
    wmod.sent = sent

    w = _watcher(wmod, [("MNQ", 2, {})])
    w._reconcile([], snapshot_ok=True)
    assert w._flat_confirm["MNQ"] == 1

    w._reconcile([], snapshot_ok=False)
    assert w._flat_confirm == {}, "a failed read must break the chain"

    w._reconcile([], snapshot_ok=True)
    assert len(w.lots) == 1, "count must restart, not complete"
    assert w._flat_confirm["MNQ"] == 1
    monkey.undo()


# ── real desync must still be detected ──────────────────────────────
def test_genuine_desync_still_warns(tmp_path):
    """The health gate must not swallow the real mismatch alert."""
    sent: list[str] = []
    monkey = pytest.MonkeyPatch()
    import notify.feishu as feishu
    monkey.setattr(feishu, "FeishuNotifier",
                   type("N", (), {"send_message": lambda self, t: sent.append(t)}))
    monkey.setenv("TIME_STOP_STATE", str(tmp_path / "s2.json"))
    monkey.setenv("TIME_STOP_AUDIT", str(tmp_path / "a2.jsonl"))
    sys.modules.pop("live_gateway.time_stop", None)
    mod = importlib.import_module("live_gateway.time_stop")

    w = _watcher(mod, [("MNQ", 2, {})])
    can_trade = w._reconcile([_flat_read("MNQ", 5)], snapshot_ok=True)

    assert can_trade is False
    assert "MNQ" in w.desync_alerted
    assert any("持仓数据不一致" in m for m in sent), sent
    monkey.undo()


def test_adopted_symbol_is_skipped(tmp_path):
    """A symbol adopted this tick must not be counted as flat."""
    sent: list[str] = []
    monkey = pytest.MonkeyPatch()
    import notify.feishu as feishu
    monkey.setattr(feishu, "FeishuNotifier",
                   type("N", (), {"send_message": lambda self, t: sent.append(t)}))
    monkey.setenv("TIME_STOP_STATE", str(tmp_path / "s3.json"))
    monkey.setenv("TIME_STOP_AUDIT", str(tmp_path / "a3.jsonl"))
    sys.modules.pop("live_gateway.time_stop", None)
    mod = importlib.import_module("live_gateway.time_stop")

    w = _watcher(mod, [("MNQ", 2, {})])
    w._adopted_this_tick = {"MNQ"}

    can_trade = w._reconcile([], snapshot_ok=True)

    assert len(w.lots) == 1
    assert can_trade is True
    assert w._flat_confirm == {}, "adopted symbols must not enter the chain"
    monkey.undo()
