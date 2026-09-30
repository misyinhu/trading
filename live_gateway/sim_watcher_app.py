#!/usr/bin/env python3
"""CTP simulation watcher (read-only).

Shares the same TimeStopWatcher factor semantics, but watches simnow/citic
positions through the local simulation bridge. Data-source priority is read
from the shared services.yaml; this process never imports quant-agent and
never places orders.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from datetime import timedelta
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
from flask import Flask, jsonify
import yaml

from live_gateway.time_stop import structure_signals

ROOT = Path(__file__).resolve().parents[1]
BRIDGE_URL = os.environ.get("SIM_BRIDGE_URL", "http://127.0.0.1:5002")
SERVICES_PATH = Path(os.environ.get(
    "SERVICES_YAML",
    str(ROOT / "config" / "services.yaml")))
STATE_PATH = ROOT / "data" / "sim_watcher_state.json"
PROFILES = ("simnow", "citic")
CTP_MD_PORTS = {"simnow": 5003, "citic": 5004}
MAX_BARS = 700
TICK_SEC = 30
BEIJING = timezone(timedelta(hours=8))


def source_priority() -> list[str]:
    try:
        data = yaml.safe_load(SERVICES_PATH.read_text(encoding="utf-8")) or {}
        primary = str((data.get("paper") or {}).get(
            "onshore_data_primary", "tqsdk")).strip().lower()
    except Exception:
        primary = "tqsdk"
    primary = os.environ.get("PAPER_ONSHORE_DATA_PRIMARY", primary).strip().lower()
    return ["tqsdk", "ctp"] if primary == "tqsdk" else ["ctp", "tqsdk"]


def floor_5m(ts: float) -> int:
    return int(ts // 300) * 300


class CtpSseBars:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.bars: dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_BARS))
        self.cur: dict[str, dict] = {}
        self.threads: dict[str, threading.Thread] = {}
        self.status = {}

    def start(self) -> None:
        for profile, port in CTP_MD_PORTS.items():
            thread = threading.Thread(
                target=self._run, args=(profile, port),
                daemon=True, name=f"sim-md-{profile}")
            self.threads[profile] = thread
            thread.start()

    def _run(self, profile: str, port: int) -> None:
        url = (f"http://127.0.0.1:{port}/api/ctp/md/stream"
               f"?profile={profile}")
        while True:
            try:
                with requests.get(url, stream=True, timeout=(5, 30)) as resp:
                    self.status[profile] = f"connected http={resp.status_code}"
                    payload = ""
                    for line in resp.iter_lines(decode_unicode=True):
                        if line and line.startswith("data: "):
                            payload = line[6:]
                        elif line == "" and payload:
                            self._consume(profile, payload)
                            payload = ""
            except Exception as exc:  # noqa: BLE001
                self.status[profile] = f"reconnect: {str(exc)[:100]}"
                time.sleep(3)

    def _consume(self, profile: str, payload: str) -> None:
        try:
            tick = json.loads(payload)
            symbol = tick["instrument_id"]
            price = float(tick["last_price"])
            ts_text = tick.get("ts_exchange") or ""
            # ts_exchange is Beijing wall-clock: either
            # "YYYY-MM-DD HH:MM:SS" or compact "YYYYMMDD HH:MM:SS.mmm".
            date_part, _, time_part = ts_text[:19].partition(" ")
            if "-" in date_part:
                day = datetime.strptime(date_part, "%Y-%m-%d")
            else:
                day = datetime.strptime(date_part, "%Y%m%d")
            clock = datetime.strptime(time_part[:8], "%H:%M:%S")
            ts = day.replace(hour=clock.hour, minute=clock.minute,
                             second=clock.second, tzinfo=BEIJING
                             ).astimezone(timezone.utc).timestamp()
        except Exception:
            return
        if price <= 0:
            return
        bucket = floor_5m(ts)
        key = f"{profile}:{symbol}"
        with self.lock:
            bar = self.cur.get(key)
            if bar is None or bar["ts"] != bucket:
                if bar is not None:
                    self.bars[key].append(bar)
                bar = {"ts": bucket, "o": price, "h": price,
                       "l": price, "c": price}
                self.cur[key] = bar
            else:
                bar["h"] = max(bar["h"], price)
                bar["l"] = min(bar["l"], price)
                bar["c"] = price

    def bars_for(self, profile: str, symbol: str) -> list[dict]:
        key = f"{profile}:{symbol}"
        with self.lock:
            out = list(self.bars[key])
            cur = self.cur.get(key)
            if cur is not None:
                out.append(cur)
        return [{"ts": b["ts"], "o": b["o"], "h": b["h"],
                 "l": b["l"], "c": b["c"]} for b in out]


class SimWatcher:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.lots: list[dict] = []
        self.md = CtpSseBars()
        self.last_update = None

    def start(self) -> None:
        self.md.start()
        thread = threading.Thread(target=self._loop, daemon=True, name="sim-watcher")
        thread.start()

    def _loop(self) -> None:
        while True:
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001
                # Never let the watcher thread die; log and retry.
                print(f"[sim-watcher] tick error: {exc!r}", flush=True)
                time.sleep(min(TICK_SEC, 10))
            else:
                time.sleep(TICK_SEC)

    def fetch_positions(self) -> list[dict]:
        rows = []
        for profile in PROFILES:
            try:
                resp = requests.get(
                    f"{BRIDGE_URL}/api/ctp/positions",
                    params={"profile": profile}, timeout=12)
                data = resp.json()
                for position in data.get("positions") or []:
                    position["_profile"] = profile
                    rows.append(position)
            except Exception:  # noqa: BLE001
                continue
        return rows

    @staticmethod
    def lot_key(position: dict) -> tuple[str, str, str]:
        profile = position["_profile"]
        symbol = str(position.get("symbol") or "")
        direction = "long" if str(position.get("direction")) == "0" else "short"
        return profile, symbol, direction

    @staticmethod
    def open_dt(position: dict, fallback: datetime) -> datetime:
        raw = str(position.get("open_date") or "")
        try:
            # CTP trade date is a Beijing date; midnight BJ -> UTC.
            return datetime.strptime(raw, "%Y%m%d").replace(
                tzinfo=BEIJING).astimezone(timezone.utc)
        except Exception:
            return fallback

    def tick(self) -> None:
        positions = self.fetch_positions()
        active = {self.lot_key(p) for p in positions}
        now = datetime.now(timezone.utc)
        with self.lock:
            self.lots = [lot for lot in self.lots
                         if tuple(lot[k] for k in ("profile", "symbol", "dir")) in active]
            for position in positions:
                key = self.lot_key(position)
                lot = next((item for item in self.lots
                            if tuple(item[k] for k in ("profile", "symbol", "dir")) == key), None)
                if lot is None:
                    odt = self.open_dt(position, now)
                    lot = {"profile": key[0], "symbol": key[1], "dir": key[2],
                           "root": "".join(ch for ch in key[1] if ch.isalpha()).upper(),
                           "qty": float(position.get("volume") or 0),
                           "open_dt": odt.isoformat(), "open_px": position.get("avg_price"),
                           "metrics": None}
                    self.lots.append(lot)
                lot["qty"] = float(position.get("volume") or lot["qty"])
                if not lot.get("open_px") and position.get("avg_price"):
                    lot["open_px"] = position.get("avg_price")
                bars = self._bars_for_priority(lot)
                if bars:
                    sig = structure_signals(
                        bars, datetime.fromisoformat(lot["open_dt"]),
                        1 if lot["dir"] == "long" else -1,
                        now, lot.get("open_px"))
                    if sig:
                        lot["metrics"] = {
                            "mfe_a": round(sig["mfe_a"], 2),
                            "pnl_a": round(sig["pnl_a"], 2),
                            "uw": round(sig["uw"], 3),
                            "er": round(sig["er"], 3),
                            "giveback_a": round(sig["giveback_a"], 2),
                            "bars": sig["bars_since_open"],
                            "source": self._selected_source}
            self.last_update = now.isoformat()

    def _bars_for_priority(self, lot: dict) -> list[dict] | None:
        for source in source_priority():
            self._selected_source = source
            if source == "ctp":
                bars = self.md.bars_for(lot["profile"], lot["symbol"])
                if len(bars) >= 3:
                    return bars
            # tqsdk source can be added here without changing callers; CTP is
            # used as automatic fallback when unavailable.
        return None

    def status(self) -> dict[str, Any]:
        thread = next((t for t in threading.enumerate()
                       if t.name == "sim-watcher"), None)
        with self.lock:
            return {"updated_at": self.last_update,
                    "watcher_alive": thread.is_alive() if thread else False,
                    "source_priority": source_priority(),
                    "md": self.md.status,
                    "lots": [dict(lot) for lot in self.lots]}


app = Flask(__name__)
watcher = SimWatcher()


@app.get("/api/sim/time-stop/status")
def status():
    return jsonify(watcher.status())


@app.get("/api/sim/time-stop/health")
def health():
    return jsonify({"ok": True, "source_priority": source_priority()})


if __name__ == "__main__":
    watcher.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("SIM_WATCHER_PORT", "5007")))
