"""Time-based protective stop watcher for IB live gateway.

Rules (set by the account owner 2026-09-19, evidence:
trader_agent reports/2026-09-19-trading-behavior-3m):
  - Pure directional lots: warn at 2h, force close at 3h.
  - Hedge legs (same sector, opposite direction, different but correlated
    symbol, holding windows overlap) are exempt while the pair is alive.
  - If a pair is unlocked (one leg closed), the surviving leg becomes a fresh
    directional lot and its clock restarts at the unlock moment.

Modes (env TIME_STOP_MODE):
  off      - watcher does nothing
  audit    - evaluate + feishu notify + audit log, never sends orders (default)
  enforce  - actually sends reduce-only close orders at the 3h limit

Only reduce-only closes via manager.order(close_position=True). Never opens,
reverses, or chases. All actions are appended to data/time_stop_audit.jsonl.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WARN_SEC = int(os.environ.get("TIME_STOP_WARN_SEC", str(2 * 3600)))
STOP_SEC = int(os.environ.get("TIME_STOP_STOP_SEC", str(3 * 3600)))
TICK_SEC = int(os.environ.get("TIME_STOP_TICK_SEC", "30"))
MODE = os.environ.get("TIME_STOP_MODE", "audit").strip().lower()
STATE_PATH = Path(os.environ.get("TIME_STOP_STATE", "data/time_stop_state.json"))
AUDIT_PATH = Path(os.environ.get("TIME_STOP_AUDIT", "data/time_stop_audit.jsonl"))

INDEX = {"MNQ", "NQ", "MES", "ES", "MYM", "YM", "VXX", "VXZ"}
METAL = {"MGC", "GC", "SI", "SIL"}
COPPER = {"MHG", "HG"}
ENERGY = {"MCL", "CL"}


def root_symbol(sym: str) -> str:
    if "." in sym:
        return sym
    i = len(sym)
    while i and sym[i - 1].isdigit():
        i -= 1
    if i and sym[i - 1] in "FGHJKMNQUVXZ":
        i -= 1
    return sym[:i]


def sector(rt: str) -> str:
    if rt in INDEX or rt[:2] in ("VX", "VF", "VG", "VV"):
        return "index"
    if rt in METAL:
        return "metal"
    if rt in COPPER:
        return "copper"
    if rt in ENERGY or rt[:2] == "RB":
        return "energy"
    if "." in rt:
        return "fx"
    return "other"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


class TimeStopWatcher:
    def __init__(self, manager) -> None:
        self.mgr = manager
        self.lots: list[dict[str, Any]] = []       # open lots
        self.seen_exec: set[str] = set()
        self.desync_alerted: set[str] = set()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_tick: dict[str, Any] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────
    def _load(self) -> None:
        try:
            d = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            self.lots = d.get("lots", [])
            self.seen_exec = set(d.get("seen_exec", []))
        except Exception:
            pass

    def _save(self) -> None:
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = STATE_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(
                {"lots": self.lots, "seen_exec": sorted(self.seen_exec)},
                ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(STATE_PATH)
        except Exception:
            pass

    def _audit(self, kind: str, payload: dict) -> None:
        rec = {"ts": _now().isoformat(), "mode": MODE, "kind": kind, **payload}
        try:
            AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass
        self.last_tick = rec

    def _notify(self, text: str) -> None:
        try:
            import sys
            sys.path.insert(0, os.getcwd())
            from notify.feishu import FeishuNotifier
            FeishuNotifier().send_message(f"[TimeStop/{MODE}] {text}")
        except Exception as e:  # noqa: BLE001
            self._audit("notify_failed", {"error": str(e)})

    # ── fill → FIFO lot book (per precise symbol) ────────────────
    def _apply_fill(self, fill: dict) -> None:
        if str(fill.get("sec_type", "")).upper() == "CASH":
            return  # IDEALPRO forex conversion, not a directional position
        sym = fill["symbol"]
        rt = root_symbol(sym)
        q = float(fill.get("shares") or 0) * (1 if fill.get("side") == "BOT" else -1)
        if q == 0:
            return
        ts = fill.get("time")
        dt = _parse_dt(ts) if isinstance(ts, str) else _now()
        exec_id = str(fill.get("exec_id") or f"{sym}-{ts}-{q}")
        bk = deque(l for l in self.lots if l["symbol"] == sym)
        rest = [l for l in self.lots if l["symbol"] != sym]
        remaining = q
        while remaining and bk and (bk[0]["qty"] > 0) != (remaining > 0):
            lot = bk[0]
            m = min(abs(lot["qty"]), abs(remaining))
            lot["qty"] += -m if lot["qty"] > 0 else m
            remaining += -m if remaining > 0 else m
            self._audit("lot_closed", {"symbol": sym, "root": rt,
                                        "dir": lot["dir"],
                                        "open_dt": lot["open_dt"],
                                        "age_h": round((dt - _parse_dt(lot["open_dt"])).total_seconds() / 3600, 2)})
            if abs(lot["qty"]) < 1e-9:
                bk.popleft()
        if abs(remaining) > 1e-9:
            bk.append({"symbol": sym, "root": rt, "grp": sector(rt),
                       "dir": "long" if remaining > 0 else "short",
                       "qty": remaining, "open_dt": dt.isoformat(),
                       "clock_dt": dt.isoformat(), "warned": False, "acted": False,
                       "exec": [exec_id]})
        self.lots = rest + list(bk)

    # ── hedge flag + unlock re-clock ─────────────────────────────
    def _refresh_hedge(self, now: datetime) -> None:
        for l in self.lots:
            hedged = any(
                l is not o and o["grp"] == l["grp"] and o["root"] != l["root"]
                and o["dir"] != l["dir"]
                for o in self.lots)
            was = l.get("hedged", False)
            if was and not hedged:
                # pair unlocked: surviving leg restarts its clock
                l["clock_dt"] = now.isoformat()
                l["warned"] = False
                l["acted"] = False
                self._audit("unlock_reclock", {"symbol": l["symbol"], "root": l["root"],
                                               "dir": l["dir"]})
                self._notify(f"pair unlocked; {l['dir']} {l['root']} clock restarted")
            l["hedged"] = hedged

    def _reconcile(self, positions: list[dict]) -> bool:
        """Compare net qty per symbol with positions. Return False if desync."""
        net: dict[str, float] = defaultdict(float)
        for l in self.lots:
            net[l["symbol"]] += l["qty"]
        pnet: dict[str, float] = defaultdict(float)
        for p in positions:
            if p.get("position"):
                pnet[p["symbol"]] += float(p["position"])
        ok = True
        for sym in set(net) | set(pnet):
            if abs(net.get(sym, 0.0) - pnet.get(sym, 0.0)) > 1e-6:
                if abs(pnet.get(sym, 0.0)) < 1e-9:
                    # actually flat: lots were closed before gateway session
                    # started or outside tracked fills; drop phantom lots
                    self.lots = [l for l in self.lots if l["symbol"] != sym]
                    self.desync_alerted.discard(sym)
                    self._audit("reconcile_flat_clear", {"symbol": sym})
                    continue
                ok = False
                if sym not in self.desync_alerted:
                    self.desync_alerted.add(sym)
                    self._notify(f"lot/position desync {sym}: lot={net.get(sym,0)} pos={pnet.get(sym,0)}; auto-stop suspended for symbol")
                    self._audit("desync", {"symbol": sym, "lot": net.get(sym, 0), "pos": pnet.get(sym, 0)})
            elif sym in self.desync_alerted:
                self.desync_alerted.discard(sym)
        return ok

    # ── evaluation ───────────────────────────────────────────────
    def _evaluate(self, now: datetime, can_trade: bool) -> None:
        for l in self.lots:
            if l.get("hedged") or l.get("acted") or l["symbol"] in self.desync_alerted:
                continue
            age = (now - _parse_dt(l["clock_dt"])).total_seconds()
            if age >= STOP_SEC:
                l["acted"] = True
                msg = (f"{l['dir']} {l['root']} {abs(l['qty']):g} aged {age/3600:.1f}h >= 3h")
                if MODE == "enforce" and can_trade:
                    try:
                        res = self.mgr.order({"symbol": l["root"], "close_position": True,
                                              "quantity": abs(l["qty"])})
                        self._notify(f"AUTO-CLOSE {msg} -> {res.get('status')}")
                        self._audit("auto_close", {"root": l["root"], "dir": l["dir"],
                                                   "qty": abs(l["qty"]), "age_h": round(age/3600, 2),
                                                   "result": res})
                    except Exception as e:  # noqa: BLE001
                        l["acted"] = False
                        self._notify(f"AUTO-CLOSE FAILED {msg}: {e}")
                        self._audit("auto_close_failed", {"root": l["root"], "error": str(e)})
                else:
                    self._notify(f"would close (dry run) {msg}")
                    self._audit("would_close", {"root": l["root"], "dir": l["dir"],
                                                "qty": abs(l["qty"]), "age_h": round(age/3600, 2)})
            elif age >= WARN_SEC and not l["warned"]:
                l["warned"] = True
                self._notify(f"WARN {l['dir']} {l['root']} aged {age/3600:.1f}h >= 2h; close due at 3h")
                self._audit("warn", {"root": l["root"], "dir": l["dir"],
                                     "age_h": round(age/3600, 2)})

    def _snapshot(self) -> dict:
        def job():
            # Single queued job: do not call manager.fills()/positions() here,
            # because they re-enqueue onto the same request queue and deadlock
            # when invoked from the watcher thread.
            ib = self.mgr.start()
            target = self.mgr._target_account(ib)
            fills, positions = [], []
            for f in ib.fills():
                e, c = f.execution, f.contract
                if e.acctNumber and e.acctNumber != target:
                    continue
                fills.append({"exec_id": e.execId, "symbol": c.symbol,
                              "side": e.side, "shares": e.shares, "sec_type": c.secType,
                              "time": e.time.isoformat() if isinstance(e.time, datetime) else str(e.time)})
            for p in ib.positions():
                if p.account != target:
                    continue
                positions.append({"symbol": p.contract.symbol, "position": p.position})
            return fills, positions
        return self.mgr.run_sync(job, 30)

    def tick(self) -> None:
        try:
            fills, positions = self._snapshot()
            with self._lock:
                for f in fills:
                    eid = str(f.get("exec_id"))
                    if eid and eid not in self.seen_exec:
                        self.seen_exec.add(eid)
                        self._apply_fill(f)
                now = _now()
                self._refresh_hedge(now)
                can_trade = self._reconcile(positions)
                if MODE != "off":
                    self._evaluate(now, can_trade)
                self._save()
                self.last_tick = {"ts": now.isoformat(), "mode": MODE,
                                  "open_lots": len(self.lots), "seen_exec": len(self.seen_exec)}
        except Exception as e:  # noqa: BLE001
            self._audit("tick_error", {"error": str(e)})

    def status(self) -> dict:
        now = _now()
        rows = []
        for l in self.lots:
            rows.append({"symbol": l["symbol"], "root": l["root"], "sector": l["grp"],
                         "dir": l["dir"], "qty": l["qty"],
                         "open_dt": l["open_dt"], "clock_dt": l["clock_dt"],
                         "age_h": round((now - _parse_dt(l["clock_dt"])).total_seconds() / 3600, 2),
                         "hedged": l.get("hedged", False), "warned": l["warned"],
                         "acted": l["acted"]})
        return {"mode": MODE, "warn_h": WARN_SEC / 3600, "stop_h": STOP_SEC / 3600,
                "last_tick": self.last_tick, "lots": rows,
                "desync_symbols": sorted(self.desync_alerted)}

    def start(self) -> None:
        if MODE == "off" or self._thread:
            return
        def loop():
            while not self._stop.wait(TICK_SEC):
                self.tick()
        self._thread = threading.Thread(target=loop, daemon=True, name="TimeStopWatcher")
        self._thread.start()
        self._audit("watcher_start", {"mode": MODE})
