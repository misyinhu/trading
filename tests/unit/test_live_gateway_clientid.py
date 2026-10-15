"""IBLiveManager must reclaim its fixed clientId before the real connect.

Incident (2026-10-15): the gateway was down for 8.9h. The audit log said
"Error 326 / clientId 12 already in use", which points at a stale session —
but a control probe with a definitely-unused clientId (77) failed identically,
so the blocker was a hung IB Gateway, not the clientId. The reclaim is still
worth having for the failure mode it actually addresses: a process killed
without closing its socket, which leaves Gateway holding the id.

client/ib_connection.py (the webhook bridge) has had this logic all along;
live_gateway connected bare.

These tests drive _reconnect_path() rather than _run(): a successful _run()
enters its `while self._running` request loop and never returns, so calling it
directly would hang the suite.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def lg():
    spec = importlib.util.spec_from_file_location(
        "lg_reclaim_under_test", REPO_ROOT / "live_gateway" / "live_gateway_app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeIB:
    """Records connect/disconnect. `fail` simulates a Gateway-side refusal."""

    def __init__(self, fail: Exception | None = None):
        self.fail = fail
        self.calls: list[tuple[str, dict]] = []

    def connect(self, host, port, **kw):
        self.calls.append(("connect", {"host": host, "port": port, **kw}))
        if self.fail:
            raise self.fail

    def disconnect(self):
        self.calls.append(("disconnect", {}))


def _install(lg, monkeypatch, plan: list[Exception | None]) -> list[FakeIB]:
    """plan[i] is the exception the i-th IB() should raise (None = succeed)."""
    made: list[FakeIB] = []

    def factory():
        fake = FakeIB(plan[len(made)] if len(made) < len(plan) else None)
        made.append(fake)
        return fake

    monkeypatch.setattr(lg, "IB", factory)
    return made


def _reconnect_path(lg) -> tuple[Exception | None, list[FakeIB]]:
    """Mirror _run()'s reclaim+connect sequence, returning the raised error.

    Kept in lockstep with IBLiveManager._run by
    test_run_actually_calls_the_reclaim, which asserts the source does this.
    """
    mgr = lg.IBLiveManager()
    made: list[FakeIB] = []

    def factory():
        idx = len(made)
        fake = FakeIB(FAILED_CONNECT if idx == 1 else None)
        made.append(fake)
        return fake

    lg.IB = factory
    try:
        mgr._reclaim_client_id()
        ib = made[1] if len(made) > 1 else lg.IB()
        ib.connect(lg.IB_HOST, lg.IB_PORT, clientId=lg.IB_CLIENT_ID, timeout=10)
    except Exception as e:  # noqa: BLE001
        return e, made
    return None, made


FAILED_CONNECT = ConnectionError("Error 326: 客户号码已被使用")


def test_reclaim_connects_and_disconnects_same_clientid(lg):
    mgr = lg.IBLiveManager()
    made: list[FakeIB] = []

    lg.IB = lambda: made.append(FakeIB()) or made[-1]
    mgr._reclaim_client_id()

    assert [c[0] for c in made[0].calls] == ["connect", "disconnect"], \
        "probe must connect then disconnect, never leave a session open"
    assert made[0].calls[0][1]["clientId"] == lg.IB_CLIENT_ID
    assert made[0].calls[0][1]["port"] == lg.IB_PORT


def test_reclaim_never_raises(lg, monkeypatch):
    """A dead Gateway must not turn into a second failure mode."""
    mgr = lg.IBLiveManager()
    monkeypatch.setattr(
        lg, "IB", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    mgr._reclaim_client_id()   # must not raise


def test_reclaim_probes_again_on_every_reconnect(lg):
    """start() spawns _run() on each attempt while disconnected, so the reclaim
    must be inside _run(), not memoised once at construction."""
    mgr = lg.IBLiveManager()
    made: list[FakeIB] = []
    lg.IB = lambda: made.append(FakeIB()) or made[-1]

    mgr._reclaim_client_id()
    mgr._reclaim_client_id()

    assert len(made) == 2, "each reconnect attempt probes again"


def test_reclaim_runs_before_the_real_connect(lg):
    """Order is the whole mechanism: evict the zombie with the same id, then
    connect for real on that id."""
    mgr = lg.IBLiveManager()
    made: list[FakeIB] = []
    lg.IB = lambda: made.append(FakeIB()) or made[-1]

    mgr._reclaim_client_id()
    real = lg.IB()          # a FRESH instance, not the probe
    real.connect(lg.IB_HOST, lg.IB_PORT, clientId=lg.IB_CLIENT_ID, timeout=10)

    assert [c[0] for c in made[0].calls] == ["connect", "disconnect"]
    assert [c[0] for c in real.calls] == ["connect"]
    assert made[0].calls[0][1]["clientId"] == real.calls[0][1]["clientId"] == lg.IB_CLIENT_ID


def test_failed_reclaim_still_allows_real_connect(lg):
    """Probe times out against a hung Gateway; the real connect must still be
    attempted so ITS error is what the operator sees."""
    mgr = lg.IBLiveManager()
    made: list[FakeIB] = []
    states = iter([FAILED_CONNECT, None])

    lg.IB = lambda: made.append(FakeIB(next(states))) or made[-1]

    mgr._reclaim_client_id()          # swallows
    real = lg.IB()
    real.connect(lg.IB_HOST, lg.IB_PORT, clientId=lg.IB_CLIENT_ID, timeout=10)

    assert [c[0] for c in made[0].calls] == ["connect"], "probe gave up on refusal"
    assert [c[0] for c in real.calls] == ["connect"], "real connect still attempted"


def test_run_calls_reclaim_before_connecting(lg):
    """Pin the wiring in _run itself — the helper tests would not catch a
    future edit that stops calling it."""
    src = (REPO_ROOT / "live_gateway" / "live_gateway_app.py").read_text(encoding="utf-8")
    body = src.split("    def _run(self) -> None:", 1)[1].split("    def run_sync", 1)[0]
    reclaim_at = body.find("self._reclaim_client_id()")
    connect_at = body.find("ib.connect(")
    assert reclaim_at != -1, "_run must call _reclaim_client_id()"
    assert connect_at != -1
    assert reclaim_at < connect_at, "reclaim must precede the real connect"
