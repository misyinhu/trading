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
UW_RED = float(os.environ.get("TIME_STOP_UW_RED", "0.75"))    # underwater-time ratio -> red
UW_GREEN = float(os.environ.get("TIME_STOP_UW_GREEN", "0.25"))
GB_RED = float(os.environ.get("TIME_STOP_GB_RED", "2.0"))  # giveback ATR -> red
GB_YELLOW = float(os.environ.get("TIME_STOP_GB_YELLOW", "1.0"))  # giveback ATR -> yellow
MODE = os.environ.get("TIME_STOP_MODE", "audit").strip().lower()
STATE_PATH = Path(os.environ.get("TIME_STOP_STATE", "data/time_stop_state.json"))
AUDIT_PATH = Path(os.environ.get("TIME_STOP_AUDIT", "data/time_stop_audit.jsonl"))
# Structure alerts (added 2026-09-19, evidence: trader_agent
# range_to_breakout.md): notify-only, NEVER trigger orders in any mode.
# ATR = trailing median 5m bar range of the last 20 bars (price units).
BARS_REFRESH_SEC = int(os.environ.get("TIME_STOP_BARS_REFRESH_SEC", "300"))
MFE_YELLOW_SEC = int(os.environ.get("TIME_STOP_MFE_YELLOW_SEC", str(3600)))
MFE_RED_SEC = int(os.environ.get("TIME_STOP_MFE_RED_SEC", str(7200)))
MFE_MIN_A = float(os.environ.get("TIME_STOP_MFE_MIN_A", "0.5"))
BREAK_MIN_A = float(os.environ.get("TIME_STOP_BREAK_MIN_A", "1.0"))
BREAK_VOL_X = float(os.environ.get("TIME_STOP_BREAK_VOL_X", "1.2"))
BREAK_MIN_AGE_SEC = int(os.environ.get("TIME_STOP_BREAK_MIN_AGE_SEC", "1200"))
BREAK_MIN_BARS = 10
ATR_WIN = 20
BOX_FORM_BARS = 6   # first 30min after open define the range box

FX = {"GBP", "EUR", "JPY", "AUD", "CAD", "CHF", "NZD", "USD", "HKD",
      "CNH", "SGD", "SEK", "NOK", "MXN", "ZAR"}
INDEX = {"MNQ", "NQ", "MES", "ES", "MYM", "YM", "VXX", "VXZ"}
METAL = {"MGC", "GC", "SI", "SIL"}
COPPER = {"MHG", "HG"}
ENERGY = {"MCL", "CL"}

# CTP domestic product sectors (uppercase product code, e.g. au2610 -> AU)
CTP_SECTOR = {
    **{c: "ferrous" for c in ("RB", "HC", "I", "J", "JM", "SF", "SM")},
    **{c: "precious" for c in ("AU", "AG")},
    **{c: "nonferrous" for c in ("CU", "AL", "ZN", "NI", "PB", "SN")},
    **{c: "energy" for c in ("FU", "LU", "BU", "SC", "PG")},
    **{c: "agri" for c in ("M", "Y", "P", "OI", "RM", "CF", "SR", "AP", "C", "CS")},
}


def ctp_root(sym: str) -> str:
    import re
    m = re.match(r"^([A-Za-z]+)", str(sym or ""))
    return m.group(1).upper() if m else str(sym or "").upper()


def ctp_sector(rt: str) -> str:
    return CTP_SECTOR.get(rt, "ctp_other")


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
    if rt in FX:
        return "fx"
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


def structure_signals(bars: list[dict], open_dt: datetime, direction: int,
                      now: datetime, open_px_actual: float | None = None) -> dict | None:
    """Range-vs-breakout structure on 5m bars (notify-only feature).

    bars: [{"ts": epoch_seconds_utc, "o","h","l","c"}] newest-last.
    direction: +1 long / -1 short. ATR = trailing median 5m range (last 20).
    Returns ATR-normalized MFE since open, current pnl, box breakout flags.
    """
    if not bars:
        return None
    ou = open_dt.astimezone(timezone.utc)
    def _bar_ts(b):
        # IB formatDate=2 理论上给 epoch 秒，部分版本仍返回 datetime，统一归一化。
        t = b["ts"]
        if isinstance(t, datetime):
            return t.astimezone(timezone.utc) if t.tzinfo else t.replace(tzinfo=timezone.utc)
        return datetime.fromtimestamp(float(t), tz=timezone.utc)
    hi = [float(b["h"]) for b in bars]
    lo = [float(b["l"]) for b in bars]
    cl = [float(b["c"]) for b in bars]
    ts = [_bar_ts(b) for b in bars]
    atr = sorted(hi[i] - lo[i] for i in range(max(0, len(bars) - ATR_WIN), len(bars)))
    if not atr or atr[len(atr) // 2] <= 0:
        return None
    atr_px = atr[len(atr) // 2]
    idx = [i for i, t in enumerate(ts) if t >= ou]
    if not idx:
        return None
    k0 = idx[0]
    seg_h, seg_l, seg_c = hi[k0:], lo[k0:], cl[k0:]
    if len(seg_c) < 3:
        return None
    open_px = open_px_actual if open_px_actual else (cl[k0 - 1] if k0 > 0 else seg_c[0])
    mfe_px = max(seg_h) - open_px if direction > 0 else open_px - min(seg_l)
    pnl_px = (seg_c[-1] - open_px) * direction
    # Underwater time share: fraction of closed bars showing an adverse mark.
    if direction > 0:
        uw = sum(1 for c in seg_c if c < open_px) / len(seg_c)
    else:
        uw = sum(1 for c in seg_c if c > open_px) / len(seg_c)
    # Kaufman efficiency ratio; denominator includes the open->first-close
    # gap so 0 <= ER <= 1 even when the first move is adverse.
    net_px = abs(seg_c[-1] - open_px)
    path_px = abs(seg_c[0] - open_px) + sum(abs(seg_c[i] - seg_c[i - 1])
                                            for i in range(1, len(seg_c)))
    er = (net_px / path_px) if path_px > 1e-12 else 0.0
    # Box breakout: first BOX_FORM_BARS after open define the range box;
    # alert once the last 3 closes escape the fixed box adverse edge.
    brk = False
    vol_x = 0.0
    if len(seg_c) >= BOX_FORM_BARS + 3 and len(seg_c) >= BREAK_MIN_BARS:
        if direction > 0:
            edge = min(seg_l[:BOX_FORM_BARS])
            brk = all(c < edge - BREAK_MIN_A * atr_px for c in seg_c[-3:])
        else:
            edge = max(seg_h[:BOX_FORM_BARS])
            brk = all(c > edge + BREAK_MIN_A * atr_px for c in seg_c[-3:])
        box_ranges = sorted(seg_h[i] - seg_l[i] for i in range(BOX_FORM_BARS))
        recent = sorted(seg_h[i] - seg_l[i] for i in range(len(seg_c) - 3, len(seg_c)))
        if box_ranges and recent:
            med = lambda a: a[len(a) // 2]
            vol_x = med(recent) / med(box_ranges) if med(box_ranges) > 0 else 0.0
    mfe_a = mfe_px / atr_px
    pnl_a = pnl_px / atr_px
    return {"atr_px": atr_px, "mfe_a": mfe_a, "pnl_a": pnl_a,
            "giveback_a": max(mfe_a - pnl_a, 0.0),
            "uw": uw, "er": er,
            "bars_since_open": len(seg_c), "breakout": brk, "vol_x": vol_x,
            "open_px": open_px, "last_px": seg_c[-1]}


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
        self.manual: dict[str, str] = {}   # key "ib:ROOT"/"ctp:ROOT" -> true|false
        self._ctp_provider = None
        self._ctp_closer = None
        self._ctp_bars_provider = None
        self._ctp_cache: tuple[float, list] | None = None
        self._bars: dict[str, dict] = {}   # root -> {"ts": epoch, "bars": [...], "mult": x}
        self._load()

    def set_ctp_provider(self, fn) -> None:
        """fn() -> list of CTP live position dicts or None. 60s local cache."""
        self._ctp_provider = fn

    def set_ctp_closer(self, fn) -> None:
        """fn(symbol, side('long'|'short'), volume) -> result dict.
        Enforce mode only; counter-verified reduce-only close. Must raise on
        failure so the lot keeps its 3h action pending."""
        self._ctp_closer = fn

    def set_ctp_bars_provider(self, fn) -> None:
        """fn(symbol) -> list of 5m bars [{ts epoch UTC,o,h,l,c}] or []."""
        self._ctp_bars_provider = fn

    @staticmethod
    def _mkey(l: dict) -> str:
        return f"{l.get('market', 'ib')}:{l['root']}"

    # ── persistence ──────────────────────────────────────────────
    def _load(self) -> None:
        try:
            d = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            self.lots = d.get("lots", [])
            self.seen_exec = set(d.get("seen_exec", []))
            self.manual = {}
            for l in self.lots:
                l["adopted"] = True  # lots from previous session are already tracked
            for k, v in dict(d.get("manual", {})).items():
                self.manual[k if ":" in k else f"ib:{k}"] = v
        except Exception:
            pass

    def _save(self) -> None:
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = STATE_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(
                {"lots": self.lots, "seen_exec": sorted(self.seen_exec),
                 "manual": self.manual},
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
        if not bk:
            self.manual.pop(f"ib:{rt}", None)
        if abs(remaining) > 1e-9:
            # Same-direction: accumulate into existing lot instead of creating
            # a new lot. This handles repeated fills on the same side (e.g.
            # two GBP buys) without inflating the lot count.
            if bk:
                existing = bk[0]
                existing["qty"] += remaining
                existing["exec"].append(exec_id)
                # keep earliest open_dt as the true open time
            else:
                bk.append({"symbol": sym, "root": rt, "grp": sector(rt),
                           "dir": "long" if remaining > 0 else "short",
                           "qty": remaining, "open_dt": dt.isoformat(),
                           "clock_dt": dt.isoformat(), "warned": False, "acted": False,
                           "uw": 0, "tot": 0, "last_pnl": None, "light": None,
                           "open_px": fill.get("price"), "exec": [exec_id]})
        self.lots = rest + list(bk)

    # ── hedge flag + unlock re-clock ─────────────────────────────
    def _refresh_hedge(self, now: datetime) -> None:
        for l in self.lots:
            mk = l.get("market", "ib")
            auto = any(
                l is not o and o.get("market", "ib") == mk
                and o["grp"] == l["grp"] and o["root"] != l["root"]
                and o["dir"] != l["dir"]
                for o in self.lots)
            mv = self.manual.get(self._mkey(l))
            if mv == "true":
                hedged = True
            elif mv == "false":
                hedged = False
            else:
                hedged = auto
            was = l.get("hedged", False)
            if was and not hedged:
                # No longer protected: judge by true age. Auto unlock restarts
                # the clock (surviving leg); a human "not a hedge" override uses
                # the real open time so an already-old lot goes red immediately.
                if mv == "false":
                    l["clock_dt"] = l["open_dt"]
                else:
                    l["clock_dt"] = now.isoformat()
                l["warned"] = False
                l["acted"] = False
                l["uw"] = 0
                l["tot"] = 0
                l["light"] = None
                self._audit("unlock_reclock", {"symbol": l["symbol"], "root": l["root"],
                                               "dir": l["dir"], "cause": mv or "auto"})
                why = "manual override: not a hedge" if mv == "false" else "pair unlocked"
                mk = "IB" if l.get('market','ib')=='ib' else "CTP"
                dir_cn = "做多" if l['dir']=='long' else "做空"
                self._notify(f"[UNLOCK] {mk} {l['root']} {dir_cn} {abs(l['qty']):g}：{why}；时间规则已生效，2h 警戒 / 3h 离场")
            l["hedged"] = hedged
            l["auto_hedged"] = auto
            l["manual_default"] = bool(l.get("manual_default")) and mv == "true"

    def set_manual(self, root: str, value, market: str = "ib") -> dict:
        """value: True=force hedge exempt, False=force directional (never
        exempt), None=remove override and follow that market's default."""
        market = market.lower()
        key = f"{market}:{root}"
        with self._lock:
            if value is None:
                self.manual.pop(key, None)
            else:
                self.manual[key] = "true" if value else "false"
            self._refresh_hedge(_now())
            self._save()
            self._audit("manual_hedge", {"market": market, "root": root, "value": value})
        return {"market": market, "root": root, "manual": value, "lots": [
            {"root": l["root"], "hedged": l.get("hedged"),
             "auto_hedged": l.get("auto_hedged", False)}
            for l in self.lots if l["root"] == root and l.get("market", "ib") == market]}

    # ── underwater-time sampling (per-lot unrealized pnl) ───────
    @staticmethod
    def _light(ratio: float, pnl: float) -> str:
        if ratio >= UW_RED:
            return "[RED]"
        if ratio < UW_GREEN and pnl > 0:
            return "[GREEN]"
        return "[YELLOW]"

    def _sample_underwater(self, pnl_map: dict) -> None:
        """Each 30s tick is one sample; symbol-level unrealizedPNL is allocated
        to lots by qty share (same-direction adds only)."""
        ib_lots = [l for l in self.lots if l.get("market", "ib") == "ib"]
        net = defaultdict(float)
        for l in ib_lots:
            if not l.get("hedged"):
                net[l["symbol"]] += abs(l["qty"])
        for l in ib_lots:
            if l.get("hedged") or l.get("acted"):
                continue
            p = pnl_map.get(l["symbol"])
            if not p:
                continue
            mp, upnl, net_qty = p.get("market_price"), p.get("unrealized_pnl"), p.get("position")
            if mp is None or not net_qty:
                continue
            denom = net.get(l["symbol"], 0.0) or abs(net_qty)
            share = abs(l["qty"]) / denom if denom else 0.0
            same_dir = (l["qty"] > 0) == (float(net_qty) > 0)
            lot_pnl = float(upnl) * share * (1.0 if same_dir else -1.0)
            l["last_pnl"] = round(lot_pnl, 2)
            l["tot"] = int(l.get("tot", 0)) + 1
            if lot_pnl < 0:
                l["uw"] = int(l.get("uw", 0)) + 1
            ratio = l["uw"] / l["tot"] if l["tot"] else 0.0
            light = self._light(ratio, lot_pnl)
            prev = l.get("light")
            l["light"] = light
            if l.get("warned") and prev and prev != "[RED]" and light == "[RED]":
                age = (_now() - _parse_dt(l["clock_dt"])).total_seconds() / 3600
                mk = "IB" if l.get('market','ib')=='ib' else "CTP"
                dir_cn = "做多" if l['dir']=='long' else "做空"
                self._notify(
                    f"[RED] 灯号转红：{mk} {l['root']} {dir_cn} {abs(l['qty']):g}，已持有 {age:.1f} 小时，"
                    f"浮亏时间占比 {ratio*100:.0f}%，当前浮盈亏 {lot_pnl:+.0f}；注意 3 小时离场线")
                self._audit("red_escalate", {"market": l.get("market", "ib"), "root": l["root"], "age_h": round(age, 2),
                                             "uw_ratio": round(ratio, 3),
                                             "floating": round(lot_pnl, 2)})

    # ── CTP live (5004/citic): score + checkbox; default-hedged, no auto-close ──
    def _fetch_ctp(self) -> list | None:
        """60s cache around the injected provider; None on failure keeps stale."""
        import time as _t
        if not self._ctp_provider:
            return None
        now_t = _t.time()
        if self._ctp_cache and now_t - self._ctp_cache[0] < 60:
            return self._ctp_cache[1]
        try:
            pos = self._ctp_provider()
            if pos is not None:
                self._ctp_cache = (now_t, list(pos))
                return self._ctp_cache[1]
        except Exception as e:  # noqa: BLE001
            self._audit("ctp_provider_error", {"error": str(e)[:200]})
        return self._ctp_cache[1] if self._ctp_cache else None

    def _sync_ctp(self, positions: list, now: datetime) -> None:
        seen = set()
        for p in positions:
            sym = str(p.get("symbol") or "").strip()
            vol = int(float(p.get("volume") or 0))
            if not sym or vol == 0:
                continue
            rt = ctp_root(sym)
            seen.add(rt)
            key = f"ctp:{rt}"
            qty = vol * (-1 if str(p.get("direction")) == "1" else 1)
            existing = next((l for l in self.lots
                             if l.get("market") == "ctp" and l["root"] == rt), None)
            if existing is None:
                # CTP positions default to "hedge/exempt" until the human unchecks
                od = str(p.get("open_date") or "")
                avg_px = p.get("avg_price") or 0.0
                try:  # yyyyMMdd Beijing date -> UTC 01:00 (day session proxy)
                    odt = (datetime(int(od[:4]), int(od[4:6]), int(od[6:8]), 1, 0,
                                    tzinfo=timezone.utc) if od else now)
                except Exception:  # noqa: BLE001
                    odt = now
                lot = {"symbol": sym, "root": rt, "grp": ctp_sector(rt),
                       "dir": "long" if qty > 0 else "short", "qty": qty,
                       "market": "ctp", "open_dt": odt.isoformat(),
                       "clock_dt": odt.isoformat(), "warned": False, "acted": False,
                       "uw": 0, "tot": 0, "last_pnl": None, "light": None,
                       "manual_default": True, "exec": ["ctp-position"],
                       "open_px": float(avg_px) if avg_px else None}
                self.lots.append(lot)
                if key not in self.manual:
                    self.manual[key] = "true"   # default checkbox ON
                    self._audit("ctp_default_hedge", {"root": rt})
            else:
                # qty/direction follows counter truth; symbol may roll month
                existing["qty"] = qty
                existing["symbol"] = sym
                existing["dir"] = "long" if qty > 0 else "short"
                existing["manual_default"] = self.manual.get(key) == "true"
                avg_px = p.get("avg_price") or 0.0
                if not existing.get("open_px") and avg_px:
                    existing["open_px"] = float(avg_px)
        gone = [l for l in self.lots if l.get("market") == "ctp" and l["root"] not in seen]
        for l in gone:
            self.manual.pop(f"ctp:{l['root']}", None)
            self._audit("ctp_lot_closed", {"root": l["root"]})
        self.lots = [l for l in self.lots if not (l.get("market") == "ctp" and l["root"] not in seen)]

    def _sample_ctp(self, positions: list) -> None:
        """CTP counter gives float_pnl per net position: one sample per fetch."""
        by_root = {ctp_root(str(p.get("symbol") or "")): p for p in positions}
        for l in self.lots:
            if l.get("market") != "ctp":
                continue
            p = by_root.get(l["root"])
            if not p:
                continue
            lot_pnl = float(p.get("float_pnl") or 0.0)
            l["last_pnl"] = round(lot_pnl, 2)
            l["tot"] = int(l.get("tot", 0)) + 1
            if lot_pnl < 0:
                l["uw"] = int(l.get("uw", 0)) + 1
            ratio = l["uw"] / l["tot"] if l["tot"] else 0.0
            l["light"] = self._light(ratio, lot_pnl)  # score even while default-hedged

    def _cn_detail(self, l: dict) -> str:
        ratio = l["uw"] / l["tot"] if l.get("tot") else None
        light = l.get("light") or ""
        pnl = l.get("last_pnl")
        if isinstance(pnl, (int, float)):
            pnl_txt = f"当前浮盈 {pnl:+.0f}" if pnl >= 0 else f"当前浮亏 {pnl:+.0f}"
        else:
            pnl_txt = "浮盈亏暂缺"
        if ratio is None:
            uw_txt = "浮亏时间占比采样中"
        else:
            mins = l["tot"] * TICK_SEC / 60
            span = f"{mins:.0f}分钟" if mins >= 1 else f"{l['tot']*TICK_SEC}秒"
            uw_txt = f"浮亏时间占比 {ratio*100:.0f}%（{span}采样）"
        return f"{light} {uw_txt}；{pnl_txt}".strip()

    def _lot_tag(self, l: dict) -> str:
        ratio = l["uw"] / l["tot"] if l.get("tot") else 0.0
        light = l.get("light") or "⚪"
        pnl = l.get("last_pnl")
        pnl_txt = f" | floating {pnl:+.0f}" if isinstance(pnl, (int, float)) else ""
        mins = l["tot"] * TICK_SEC / 60
        span = f"{mins:.0f}m" if mins >= 1 else f"{l['tot']*TICK_SEC}s"
        sample = f" | underwater {ratio*100:.0f}% over {span}" if l.get("tot") else ""
        return f"{light}{sample}{pnl_txt}"

    def _adopt_positions(self, positions: list, portfolio: dict, now: datetime) -> None:
        """接入监控启动前已持有、且无成交记录的仓位（如重启后仍持有的外汇）。
        仅处理完全没有 lot 的品种；建一条存量 lot，计时从接入时刻起算。"""
        self._adopted_this_tick: set[str] = set()
        tracked = defaultdict(float)
        for l in self.lots:
            if l.get("market", "ib") == "ib":
                tracked[l["symbol"]] += l["qty"]
        for p in positions:
            pos = float(p.get("position") or 0.0)
            sym = str(p.get("symbol") or "")
            if not sym or abs(pos) < 1e-9 or abs(tracked[sym]) > 1e-9:
                continue
            info = portfolio.get(sym) or {}
            rt = root_symbol(sym)
            sec_type = str(p.get("sec_type") or "")
            lot = {"symbol": sym, "root": rt, "grp": sector(rt),
                   "dir": "long" if pos > 0 else "short", "qty": pos,
                   "market": "ib", "sec_type": sec_type,
                   "open_dt": now.isoformat(), "clock_dt": now.isoformat(),
                   "warned": False, "acted": False, "uw": 0, "tot": 0,
                   "last_pnl": None, "light": None, "adopted": True,
                   "open_px": info.get("market_price"), "exec": []}
            self.lots.append(lot)
            self._adopted_this_tick.add(sym)
            self.desync_alerted.discard(sym)
            self._audit("adopt_existing_position",
                        {"symbol": sym, "root": rt, "qty": pos,
                         "sec_type": sec_type, "market_price": info.get("market_price")})
            kind_txt = "外汇" if sec_type == "CASH" else (sec_type or "未知类型")
            self._notify(f"[INFO] 已接入存量持仓：{rt}（{kind_txt}）"
                         f"{'做多' if pos > 0 else '做空'} {abs(pos):g}；"
                         "监控时长自现在起算（接入前真实持有时长未知），2h 警戒 / 3h 离场规则即刻生效")

    def _reconcile(self, positions: list[dict]) -> bool:
        """Compare net qty per symbol with positions. Return False if desync."""
        net: dict[str, float] = defaultdict(float)
        for l in self.lots:
            if l.get("market", "ib") != "ib":
                continue
            net[l["symbol"]] += l["qty"]
        pnet: dict[str, float] = defaultdict(float)
        for p in positions:
            if p.get("position"):
                pnet[p["symbol"]] += float(p["position"])
        ok = True
        adopted = getattr(self, "_adopted_this_tick", set())
        for sym in set(net) | set(pnet):
            # Skip symbols just adopted this tick; they are new to lots and may
            # have been in the counter but not tracked before this session.
            if sym in adopted:
                self.desync_alerted.discard(sym)
                continue
            if abs(net.get(sym, 0.0) - pnet.get(sym, 0.0)) > 1e-6:
                if abs(pnet.get(sym, 0.0)) < 1e-9:
                    # position is flat: close all lots for this symbol (close orders
                    # may have been filled outside tracked fills, or position was
                    # closed manually in IB)
                    roots = [self._mkey(l) for l in self.lots if l["symbol"] == sym]
                    self.lots = [l for l in self.lots if l["symbol"] != sym]
                    self.desync_alerted.discard(sym)
                    for k in roots:
                        self.manual.pop(k, None)
                    self._notify(f"[INFO] 品种 {sym} 账户净持仓已归零，watcher 同步清除对应的持仓记录")
                    self._audit("reconcile_flat_clear", {"symbol": sym})
                    continue
                ok = False
                if sym not in self.desync_alerted:
                    self.desync_alerted.add(sym)
                    self._notify(f"[WARN] 持仓数据不一致：品种 {sym}，watcher 记录净持仓 {net.get(sym,0):g}，"
                                 f"账户实际净持仓 {pnet.get(sym,0):g}（差额 {pnet.get(sym,0)-net.get(sym,0):+g}）；"
                                 f"该品种时间止损已暂停，请人工核对后通过手动接口清除告警")
                    self._audit("desync", {"symbol": sym, "lot": net.get(sym, 0), "pos": pnet.get(sym, 0)})
            elif sym in self.desync_alerted:
                self.desync_alerted.discard(sym)
        return ok

    # ── evaluation ───────────────────────────────────────────────
    def _structure_alert(self, l: dict, now: datetime, age: float,
                         bars_pack: dict | None) -> None:
        """Notify-only range/breakout alerts. NEVER orders.
        bars_pack for IB; CTP uses its aggregated 5m bars via provider."""
        market = l.get("market", "ib")
        if market == "ctp":
            if not self._ctp_bars_provider or not l.get("open_px"):
                return
            try:
                bars_list = self._ctp_bars_provider(l["symbol"])
            except Exception:  # noqa: BLE001
                return
            bars_pack = {"bars": bars_list, "mult": 1.0}
        if not bars_pack or not l.get("open_px"):
            return
        sig = structure_signals(
            bars_pack.get("bars", []), _parse_dt(l["clock_dt"]),
            1 if l["dir"] == "long" else -1, now, l.get("open_px"))
        if sig is None:
            return
        mult = float(bars_pack.get("mult") or 1.0)
        usd = sig["pnl_a"] * sig["atr_px"] * abs(l["qty"]) * mult
        l["metrics"] = {"mfe_a": round(sig["mfe_a"], 2), "pnl_a": round(sig["pnl_a"], 2),
                        "uw": round(sig["uw"], 3), "er": round(sig["er"], 3),
                        "giveback_a": round(sig["giveback_a"], 2),
                        "atr_usd": round(sig["atr_px"] * abs(l["qty"]) * mult, 1),
                        "pnl_usd": round(usd, 1), "breakout": sig["breakout"],
                        "vol_x": round(sig["vol_x"], 2),
                        "bars": sig["bars_since_open"],
                        "ts": now.isoformat()}
        dir_cn0 = "做多" if l['dir']=='long' else "做空"
        tag = f"{l['root']} {dir_cn0} {abs(l['qty']):g}，已持 {age/3600:.1f}h"
        if (not l.get("mfe60_alerted") and age >= MFE_YELLOW_SEC
                and sig["mfe_a"] < MFE_MIN_A):
            l["mfe60_alerted"] = True
            self._notify(f"[WARN] 区间思路未兑现：{tag}；1 小时最大浮盈仅 {sig['mfe_a']:.2f}ATR"
                         f"（<{MFE_MIN_A}），区间交易没有带来收益，考虑评估离场")
            self._audit("mfe60_alert", {"root": l["root"], "mfe_a": round(sig["mfe_a"], 2)})
        if (not l.get("mfe120_alerted") and age >= MFE_RED_SEC
                and sig["mfe_a"] < MFE_MIN_A and sig["pnl_a"] < 0):
            l["mfe120_alerted"] = True
            self._notify(f"[RED] 区间思路持续未兑现：{tag}；2 小时最大浮盈仅 {sig['mfe_a']:.2f}ATR，"
                         f"当前浮亏 ${usd:+.0f}；行情可能已走出区间")
            self._audit("mfe120_alert", {"root": l["root"], "mfe_a": round(sig["mfe_a"], 2),
                                          "pnl_usd": round(usd, 1)})
        # Giveback alert: fires once when peak profit has been given back by ≥ N ATR.
        # gb_a = giveback_atr already stored in metrics; arm requires mfe_a ≥ 1 ATR.
        gb = sig.get("giveback_a", 0.0) or 0.0
        mfe_a = sig.get("mfe_a", 0.0) or 0.0
        if (not l.get("gb_alerted")
                and mfe_a >= 1.0          # trailing must be armed
                and gb >= GB_RED):
            l["gb_alerted"] = True
            self._notify(
                f"[RED] 盈利大幅回吐：{tag}；峰值浮盈 {mfe_a:.2f}ATR，"
                f"已回吐 {gb:.2f}ATR（≥{GB_RED:g}），当前 ${usd:+.0f}；"
                f"峰值利润基本消失，应收紧止损或离场")
            self._audit("gb_alert", {"root": l["root"],
                                    "mfe_a": round(mfe_a, 2),
                                    "giveback_a": round(gb, 2),
                                    "pnl_usd": round(usd, 1)})
        elif (not l.get("gb_yellow_alerted")
               and mfe_a >= 1.0
               and gb >= GB_YELLOW):
            l["gb_yellow_alerted"] = True
            self._notify(
                f"[WARN] 盈利回吐预警：{tag}；峰值浮盈 {mfe_a:.2f}ATR，"
                f"已回吐 {gb:.2f}ATR（≥{GB_YELLOW:g}），当前 ${usd:+.0f}；"
                f"请盯紧止损")
            self._audit("gb_yellow", {"root": l["root"],
                                       "mfe_a": round(mfe_a, 2),
                                       "giveback_a": round(gb, 2),
                                       "pnl_usd": round(usd, 1)})
        if (not l.get("break_alerted") and age >= BREAK_MIN_AGE_SEC
                and sig["breakout"] and sig["vol_x"] >= BREAK_VOL_X and sig["pnl_a"] < 0):
            l["break_alerted"] = True
            self._notify(f"[RED] 区间被突破：{tag}；连续 3 根 5m 收在区间外"
                         f"（>{BREAK_MIN_A}ATR），放量 {sig['vol_x']:.1f} 倍，当前 ${usd:+.0f}；"
                         f"区间假设已失效，需要人工决策")
            self._audit("breakout_alert", {"root": l["root"], "vol_x": round(sig["vol_x"], 2),
                                            "pnl_usd": round(usd, 1)})

    def _metrics_only(self, l: dict, now: datetime, age: float,
                      bars_pack: dict | None) -> None:
        """对冲腿专用：只计算并写入 UW/ER/MFE/GB，绝不通知、绝不动作。"""
        market = l.get("market", "ib")
        if market == "ctp":
            if not self._ctp_bars_provider or not l.get("open_px"):
                return
            try:
                bars_list = self._ctp_bars_provider(l["symbol"])
            except Exception:  # noqa: BLE001
                return
            bars_pack = {"bars": bars_list, "mult": 1.0}
        if not bars_pack or not l.get("open_px"):
            return
        sig = structure_signals(
            bars_pack.get("bars", []), _parse_dt(l["clock_dt"]),
            1 if l["dir"] == "long" else -1, now, l.get("open_px"))
        if sig is None:
            return
        mult = float(bars_pack.get("mult") or 1.0)
        usd = sig["pnl_a"] * sig["atr_px"] * abs(l["qty"]) * mult
        l["metrics"] = {"mfe_a": round(sig["mfe_a"], 2), "pnl_a": round(sig["pnl_a"], 2),
                        "uw": round(sig["uw"], 3), "er": round(sig["er"], 3),
                        "giveback_a": round(sig["giveback_a"], 2),
                        "atr_usd": round(sig["atr_px"] * abs(l["qty"]) * mult, 1),
                        "pnl_usd": round(usd, 1), "breakout": sig["breakout"],
                        "vol_x": round(sig["vol_x"], 2),
                        "bars": sig["bars_since_open"],
                        "ts": now.isoformat()}

    def _evaluate(self, now: datetime, can_trade: bool, bars: dict | None = None,
                  only_market: str | None = None) -> None:
        for l in self.lots:
            if l.get("acted") or l["symbol"] in self.desync_alerted:
                continue
            market = l.get("market", "ib")
            if only_market and market != only_market:
                continue
            age = (now - _parse_dt(l["clock_dt"])).total_seconds()
            # 内盘交易时段短，时间止损（含提醒）不适用：CTP 一律只计算并
            # 展示 UW/ER/MFE/GB 供观察，绝不告警、绝不动作。
            if market == "ctp":
                self._metrics_only(l, now, age, None)
                continue
            # 外盘对冲腿：照常展示指标，但跳过全部告警与 2h/3h 平仓动作。
            if l.get("hedged"):
                self._metrics_only(l, now, age, (bars or {}).get(l["root"]))
                continue
            if market == "ib":
                self._structure_alert(l, now, age, (bars or {}).get(l["root"]))
            if age >= STOP_SEC:
                dir_cn = "做多" if l["dir"] == "long" else "做空"
                base = (f"IB {l['root']} {dir_cn} {abs(l['qty']):g}，已持有 {age/3600:.1f} 小时，"
                        f"触及 3 小时离场线；{self._cn_detail(l)}")
                if not l.get("_3h_notified"):
                    l["_3h_notified"] = True
                if MODE == "enforce" and can_trade:
                    try:
                        res = self.mgr.order({"symbol": l["root"], "close_position": True,
                                              "quantity": abs(l["qty"])})
                        l["acted"] = True
                        l["_3h_notified_sent"] = True
                        self._notify(f"[OK] 已自动平仓：{base}；下单结果 {res.get('status')}")
                        self._audit("auto_close", {"market": market, "root": l["root"],
                                                   "symbol": l.get("symbol"), "dir": l["dir"],
                                                   "qty": abs(l["qty"]), "age_h": round(age/3600, 2),
                                                   "result": res})
                    except Exception as e:  # noqa: BLE001
                        l["acted"] = False
                        self._notify(f"[FAIL] 自动平仓失败：{base}；错误 {e}；将持续重试")
                        self._audit("auto_close_failed", {"market": market, "root": l["root"],
                                                          "error": str(e)})
                else:
                    enforce_txt = "当前为仅提醒模式，不会实际平仓" if MODE != "enforce" else "当前不可交易，已暂停自动平仓"
                    if not l.get("_3h_notified_sent"):
                        l["_3h_notified_sent"] = True
                        self._notify(f"[AUDIT] 3 小时离场提醒：{base}；{enforce_txt}")
                    else:
                        self._notify(f"[AUDIT] 再次到达 3 小时离场线（watcher 已记录，将持续提醒直至平仓或解除）：{base}")
                    self._audit("would_close", {"root": l["root"], "dir": l["dir"],
                                                "qty": abs(l["qty"]), "age_h": round(age/3600, 2),
                                                "uw_ratio": round(l["uw"]/l["tot"], 3) if l.get("tot") else None,
                                                "floating": l.get("last_pnl"),
                                                "light": l.get("light")})
            elif age >= WARN_SEC and not l["warned"]:
                l["warned"] = True
                m = l.get("metrics") or {}
                if m:
                    extra = (f"；1h 最大浮盈 {m.get('mfe_a')}ATR，"
                             f"当前浮动 ${m.get('pnl_usd'):+,.0f}")
                else:
                    extra = "；5m 结构暂缺"
                self._notify(
                    f"[WARN] 2 小时警戒：IB {l['root']} {('做多' if l['dir']=='long' else '做空')} "
                    f"{abs(l['qty']):g}，已持有 {age/3600:.1f} 小时；3 小时为离场线{extra}。"
                    f"{self._cn_detail(l)}")
                self._audit("warn", {"root": l["root"], "dir": l["dir"],
                                     "age_h": round(age/3600, 2),
                                     "uw_ratio": round(l["uw"]/l["tot"], 3) if l.get("tot") else None,
                                     "floating": l.get("last_pnl"),
                                     "light": l.get("light")})

    def _snapshot(self, roots: set[str]) -> dict:
        def job():
            # Single queued job: do not call manager.fills()/positions() here,
            # because they re-enqueue onto the same request queue and deadlock
            # when invoked from the watcher thread.
            ib = self.mgr.start()
            target = self.mgr._target_account(ib)
            fills, positions, portfolio, bars_by_root = [], [], {}, {}
            # ib.fills() only returns fills from the current session. Use
            # reqExecutions to also pull historical fills (up to 7 days back),
            # then deduplicate by execId using self.seen_exec.
            seen_ids = self.seen_exec.copy()
            def _add_fill(exec_, contract_):
                e = exec_; c = contract_
                eid = str(e.execId)
                if eid and eid not in seen_ids:
                    seen_ids.add(eid)
                    if (e.acctNumber or "") and e.acctNumber != target:
                        return
                    fills.append({"exec_id": eid, "symbol": c.symbol,
                                  "side": e.side, "shares": e.shares,
                                  "sec_type": c.secType, "price": e.price,
                                  "time": e.time.isoformat() if isinstance(e.time, datetime) else str(e.time)})
            for f in ib.fills():
                _add_fill(f.execution, f.contract)
            for p in ib.positions():
                if p.account != target:
                    continue
                positions.append({"symbol": p.contract.symbol,
                                  "sec_type": p.contract.secType,
                                  "position": p.position})
            # 5m bars for structure alerts (IB directional lots only); a
            # single contract failure is audited, never fatal to the tick.
            for p in ib.positions():
                if p.account != target or root_symbol(p.contract.symbol) not in roots:
                    continue
                try:
                    c = p.contract
                    ib.qualifyContracts(c)
                    rows = ib.reqHistoricalData(
                        c, "", durationStr="2 D", barSizeSetting="5 mins",
                        whatToShow="TRADES", useRTH=False, formatDate=2)
                    bars_by_root[root_symbol(c.symbol)] = {
                        "mult": float(c.multiplier or 1),
                        "bars": [{"ts": r.date, "o": r.open, "h": r.high,
                                  "l": r.low, "c": r.close} for r in rows]}
                except Exception as e:  # noqa: BLE001
                    self._audit("bars_failed", {"symbol": p.contract.symbol,
                                                 "error": str(e)[:200]})
            for item in ib.portfolio():
                if item.account != target:
                    continue
                portfolio[item.contract.symbol] = {
                    "position": item.position,
                    "market_price": item.marketPrice or None,
                    "avg_cost": item.averageCost or None,
                    "unrealized_pnl": item.unrealizedPNL}
            return fills, positions, portfolio, bars_by_root
        return self.mgr.run_sync(job, 45)

    def tick(self) -> None:
        try:
            now0 = _now()
            # ── 1) CTP FIRST: fully independent of the flaky IB connection.
            # A blocking/deadlocked IB snapshot must never starve the
            # internal-feed metrics path.
            ctp_positions = self._fetch_ctp()
            now = _now()
            if ctp_positions is not None:
                with self._lock:
                    self._sync_ctp(ctp_positions, now)
                if MODE != "off":
                    with self._lock:
                        self._sample_ctp(ctp_positions)
                    self._evaluate(now, False, None, only_market="ctp")
                self._save()
                self.last_tick = {"ts": now.isoformat(), "mode": MODE,
                                  "open_lots": len(self.lots),
                                  "seen_exec": len(self.seen_exec)}

            # ── 2) IB LAST: snapshot may throw or block; CTP above is already
            # done and persisted, so a hang here cannot hide internal alerts.
            roots = {l["root"] for l in self.lots
                     if l.get("market", "ib") == "ib"
                     and not l.get("hedged") and not l.get("acted")
                     and l["symbol"] not in self.desync_alerted}
            stale = {r for r in roots
                     if now0.timestamp() - self._bars.get(r, {}).get("ts", 0) > BARS_REFRESH_SEC}
            try:
                fills, positions, portfolio, fresh = self._snapshot(stale)
            except Exception as snap_err:  # noqa: BLE001
                self._audit("ib_snapshot_skip", {"error": str(snap_err)[:120]})
                fills, positions, portfolio, fresh = [], [], {}, {}
            for r, pack in fresh.items():
                pack["ts"] = now0.timestamp()
                self._bars[r] = pack
            self._bars = {r: p for r, p in self._bars.items() if r in roots}
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
                    self._sample_underwater(portfolio)
                    self._evaluate(now, can_trade, self._bars, only_market="ib")
                self._save()
                self.last_tick = {"ts": now.isoformat(), "mode": MODE,
                                  "open_lots": len(self.lots),
                                  "seen_exec": len(self.seen_exec)}
        except Exception as e:  # noqa: BLE001
            self._audit("tick_error", {"error": str(e)})

    def clear_desync(self, symbol: str) -> dict:
        """Manually clear a desync alert after human verification.
        Returns the updated desync list."""
        with self._lock:
            sym = str(symbol or "").strip()
            if sym in self.desync_alerted:
                self.desync_alerted.discard(sym)
                self._save()
                self._audit("desync_cleared_manual", {"symbol": sym})
                return {"ok": True, "symbol": sym, "desync_symbols": sorted(self.desync_alerted)}
            return {"ok": False, "symbol": sym, "reason": "not in desync list",
                    "desync_symbols": sorted(self.desync_alerted)}

    def status(self) -> dict:
        now = _now()
        rows = []
        for l in self.lots:
            ratio = round(l["uw"] / l["tot"], 3) if l.get("tot") else None
            rows.append({"symbol": l["symbol"], "root": l["root"], "sector": l["grp"],
                         "market": l.get("market", "ib"),
                         "default_hedge": l.get("manual_default", False),
                         "dir": l["dir"], "qty": l["qty"],
                         "open_dt": l["open_dt"], "clock_dt": l["clock_dt"],
                         "age_h": round((now - _parse_dt(l["clock_dt"])).total_seconds() / 3600, 2),
                         "hedged": l.get("hedged", False),
                         "auto_hedged": l.get("auto_hedged", False),
                         "manual": self.manual.get(self._mkey(l)),
                         "warned": l["warned"],
                         "acted": l["acted"], "uw_ratio": ratio,
                         "samples": l.get("tot", 0), "floating": l.get("last_pnl"),
                         "light": l.get("light"),
                         "mfe60": l.get("mfe60_alerted", False),
                         "mfe120": l.get("mfe120_alerted", False),
                         "break_alert": l.get("break_alerted", False),
                         "metrics": l.get("metrics")})
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
