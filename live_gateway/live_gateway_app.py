#!/usr/bin/env python3
"""Winclaw real-money gateway — the ONLY live-money entry point.

- IB live: local IB Gateway/TWS port 4001, funded U account only.
- CTP live: spawns an isolated ``ctp_client/ctp_worker.py`` subprocess with
  ``CTP_PROFILE=live`` forced server-side. It never proxies to the simulation
  bridge (:5002) and never accepts a caller-supplied profile.

The service intentionally has no simulation routes. Callers must complete their
own risk gate, manual confirmation, audit, and notification before sending an
order, and must send X-Real-Money: CONFIRM for write operations.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from flask import Flask, jsonify, request
from ib_insync import IB, LimitOrder, MarketOrder, Stock, util

HOST = os.environ.get("LIVE_GATEWAY_HOST", "0.0.0.0")
PORT = int(os.environ.get("LIVE_GATEWAY_PORT", "5006"))
IB_HOST = os.environ.get("IB_LIVE_HOST", "127.0.0.1")
IB_PORT = int(os.environ.get("IB_LIVE_PORT", "4001"))
IB_CLIENT_ID = int(os.environ.get("IB_LIVE_CLIENT_ID", "12"))
IB_ACCOUNT = os.environ.get("IB_LIVE_ACCOUNT", "U8590961").strip()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CTP_WORKER = PROJECT_ROOT / "ctp_client" / "ctp_worker.py"
CTP_PROFILE = "live"
CTP_QUERY_TTL = float(os.environ.get("CTP_LIVE_QUERY_TTL", "10") or "10")

FUT_EXCHANGE = {
    "ES": "CME", "MES": "CME", "NQ": "CME", "MNQ": "CME",
    "YM": "CBOT", "MYM": "CBOT",
    "GC": "COMEX", "MGC": "COMEX", "SI": "COMEX", "HG": "COMEX",
    "CL": "NYMEX",
}
app = Flask(__name__)


# ───────────────────────── CTP live (isolated subprocess) ─────────────────────────

_ctp_query_lock = threading.Lock()
_ctp_query_cache: dict[str, Any] = {"ts": 0.0, "data": None}


def _ctp_worker(action: str, order: dict | None = None, timeout: float = 40.0,
                use_cache: bool = False) -> tuple[bool, dict]:
    """Run ctp_worker.py in a subprocess with CTP_PROFILE=live forced.

    A native SWIG crash only kills the subprocess, never this Flask service.
    Returns (ok, payload).
    """
    order = dict(order or {})
    # profile/account are server-controlled for the live gateway; never trust
    # caller-supplied values.
    order.pop("profile", None)
    order.pop("account", None)

    if use_cache:
        now = time.time()
        with _ctp_query_lock:
            cached = _ctp_query_cache["data"]
            if cached is not None and now - _ctp_query_cache["ts"] < CTP_QUERY_TTL:
                return bool(cached.get("ok")), cached

    env = {
        **os.environ,
        "CTP_PROFILE": CTP_PROFILE,
        "CTP_ACTION": action,
        "CTP_ORDER_JSON": json.dumps(order, ensure_ascii=False),
        "CTP_TIMEOUT": str(timeout),
    }
    python_exe = os.environ.get("CTP_PYTHON") or sys.executable
    try:
        proc = subprocess.run(
            [python_exe, "-u", str(CTP_WORKER)],
            cwd=PROJECT_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        return False, {"ok": False, "status": "timeout", "profile": CTP_PROFILE,
                       "error": f"CTP live 子进程超时（{timeout}s）"}
    except Exception as e:  # noqa: BLE001
        return False, {"ok": False, "status": "error", "profile": CTP_PROFILE,
                       "error": f"启动 CTP live 子进程失败: {e}"}

    result = None
    for line in (proc.stdout or "").splitlines():
        if line.startswith("RESULT_JSON="):
            try:
                result = json.loads(line[len("RESULT_JSON="):])
            except Exception:  # noqa: BLE001
                result = None
    if result is None:
        tail = (proc.stderr or "").strip().splitlines()
        tail = [t for t in tail if "[ctp]" in t][-4:] or tail[-3:]
        return False, {"ok": False, "status": "crashed", "profile": CTP_PROFILE,
                       "error": f"CTP live 原生子进程异常退出（exit={proc.returncode}）"
                                + (f"；日志: {' | '.join(tail)}" if tail else "")}
    result.setdefault("profile", CTP_PROFILE)
    if use_cache and result.get("ok") and action == "query":
        with _ctp_query_lock:
            _ctp_query_cache["ts"] = time.time()
            _ctp_query_cache["data"] = result
    return bool(result.get("ok")), result


def _ctp_http_code(ok: bool, payload: dict) -> int:
    if ok:
        return 200
    status = payload.get("status")
    if status in ("timeout", "crashed", "disabled", "not_configured",
                  "unavailable", "logined_false"):
        return 503
    if status in ("bad_profile", "bad_order_json", "bad_products"):
        return 400
    return 502


def _parse_products(raw: str) -> tuple[list[dict] | None, str | None]:
    default_products = [
        ("au", "SHFE"), ("ag", "SHFE"), ("cu", "SHFE"), ("al", "SHFE"),
        ("rb", "SHFE"), ("hc", "SHFE"), ("fu", "SHFE"), ("lu", "INE"),
        ("sc", "INE"), ("i", "DCE"), ("jm", "DCE"), ("j", "DCE"),
        ("IF", "CFFEX"), ("IC", "CFFEX"), ("IH", "CFFEX"), ("IM", "CFFEX"),
    ]
    raw = (raw or "").strip()
    if not raw:
        return [{"product": p, "exchange": e} for p, e in default_products], None
    products = []
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        if ":" not in item:
            return None, f"products 项格式应为 product:exchange，收到 {item}"
        product, exchange = item.split(":", 1)
        products.append({"product": product.strip(), "exchange": exchange.strip()})
    return products, None


class IBLiveManager:
    def __init__(self) -> None:
        self._ib: IB | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._error: Exception | None = None
        self._requests: queue.Queue = queue.Queue()
        self._running = False

    def start(self) -> IB:
        if self._thread and self._thread.is_alive() and self._ib and self._ib.isConnected():
            return self._ib
        self._ready.clear()
        self._error = None
        self._thread = threading.Thread(target=self._run, daemon=True, name="IB-Live-Gateway")
        self._thread.start()
        if not self._ready.wait(12):
            raise TimeoutError("IB live Gateway connect timeout")
        if self._error:
            raise self._error
        return self._ib  # type: ignore[return-value]

    def _run(self) -> None:
        try:
            util.patchAsyncio()
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            ib = IB()
            ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID, timeout=10, readonly=False)
            self._ib = ib
            self._running = True
            self._ready.set()
            while self._running:
                try:
                    item = self._requests.get(timeout=0.5)
                except queue.Empty:
                    self._loop.run_until_complete(asyncio.sleep(0))
                    continue
                if item is None:
                    break
                fn, out = item
                try:
                    out.put(("ok", fn()))
                except Exception as e:  # noqa: BLE001
                    out.put(("error", e))
        except Exception as e:  # noqa: BLE001
            self._error = e
            self._ready.set()

    def run_sync(self, fn: Callable[[], Any], timeout: float = 30) -> Any:
        self.start()
        out: queue.Queue = queue.Queue()
        self._requests.put((fn, out))
        kind, value = out.get(timeout=timeout)
        if kind == "error":
            raise value
        return value

    def account(self) -> dict:
        def job():
            ib = self.start()
            managed = list(ib.managedAccounts() or [])
            by_account = {a: {} for a in managed}
            for row in ib.accountSummary():
                if row.account in by_account:
                    by_account[row.account][row.tag] = {"value": row.value, "currency": row.currency}

            def nav(a: str) -> float:
                try:
                    return float(by_account.get(a, {}).get("NetLiquidation", {}).get("value", 0) or 0)
                except ValueError:
                    return 0.0

            if IB_ACCOUNT in by_account:
                target = IB_ACCOUNT
            else:
                funded = [a for a in managed if a.startswith("U") and nav(a) > 0]
                if not funded:
                    raise RuntimeError(f"no funded U account; managed={managed}")
                target = sorted(funded, key=nav, reverse=True)[0]
            pnl = []
            for p in ib.pnl():
                if p.account != target:
                    continue
                pnl.append({"daily": p.dailyPnL, "total": p.value})
            return {"account": by_account.get(target, {}), "pnl": pnl,
                    "account_id": target, "managed": managed}
        return self.run_sync(job, 20)

    def positions(self) -> list[dict]:
        def job():
            ib = self.start()
            target = self._target_account(ib)
            rows = []
            for p in ib.positions():
                if p.account != target:
                    continue
                c = p.contract
                rows.append({"symbol": c.symbol, "position": p.position, "avgCost": p.avgCost,
                             "account": p.account, "currency": c.currency, "exchange": c.exchange,
                             "sec_type": c.secType, "con_id": c.conId,
                             "last_trade": c.lastTradeDateOrContractMonth,
                             "trading_class": c.tradingClass, "contract": str(c)})
            return rows
        return self.run_sync(job, 20)

    def open_orders(self) -> list[dict]:
        def job():
            ib = self.start()
            target = self._target_account(ib)
            rows = []
            for tr in ib.openTrades():
                o, c, st = tr.order, tr.contract, tr.orderStatus
                if o.account and o.account != target:
                    continue
                rows.append({
                    "order_id": o.orderId, "symbol": c.symbol, "exchange": c.exchange,
                    "currency": c.currency, "sec_type": c.secType, "con_id": c.conId,
                    "last_trade": c.lastTradeDateOrContractMonth,
                    "trading_class": c.tradingClass,
                    "action": o.action, "quantity": o.totalQuantity,
                    "order_type": o.orderType, "limit_price": o.lmtPrice,
                    "tif": o.tif, "account": o.account or target,
                    "status": st.status, "filled": st.filled, "remaining": st.remaining,
                    "avg_fill_price": st.avgFillPrice,
                })
            return rows
        return self.run_sync(job, 20)

    def fills(self) -> list[dict]:
        def job():
            ib = self.start()
            target = self._target_account(ib)
            rows = []
            for f in ib.fills():
                e, c = f.execution, f.contract
                if e.acctNumber and e.acctNumber != target:
                    continue
                commission = getattr(f, "commission", None)
                rows.append({
                    "exec_id": e.execId, "order_id": e.orderId,
                    "time": e.time.isoformat() if isinstance(e.time, datetime) else str(e.time),
                    "account": e.acctNumber or target, "exchange": e.exchange,
                    "side": e.side, "shares": e.shares, "price": e.price,
                    "cum_qty": e.cumQty, "avg_price": e.avgPrice,
                    "commission": commission,
                    "symbol": c.symbol, "currency": c.currency, "sec_type": c.secType,
                    "con_id": c.conId, "last_trade": c.lastTradeDateOrContractMonth,
                    "trading_class": c.tradingClass,
                })
            return rows
        return self.run_sync(job, 20)

    def cancel_order(self, body: dict) -> dict:
        def job():
            ib = self.start()
            target = self._target_account(ib)
            try:
                order_id = int(body.get("order_id"))
            except (TypeError, ValueError):
                raise ValueError("order_id required (int)")
            trade = next((t for t in ib.openTrades()
                          if t.order.orderId == order_id
                          and (not t.order.account or t.order.account == target)), None)
            if trade is None:
                raise RuntimeError(f"no open order order_id={order_id} in {target}")
            ib.cancelOrder(trade.order)
            ib.sleep(1)
            st = trade.orderStatus
            return {"ok": True, "account": target, "order_id": order_id,
                    "status": st.status, "filled": st.filled, "remaining": st.remaining}
        return self.run_sync(job, 20)

    def _target_account(self, ib: IB) -> str:
        managed = list(ib.managedAccounts() or [])
        if IB_ACCOUNT in managed:
            return IB_ACCOUNT
        funded = [a for a in managed if a.startswith("U")]
        if not funded:
            raise RuntimeError(f"no U account; managed={managed}")
        return funded[0]

    def _resolve_contract(self, ib: IB, body: dict, account: str):
        from ib_insync import Contract
        symbol = str(body.get("symbol", "")).strip().upper()
        sec_type = str(body.get("sec_type", "FUT")).strip().upper()
        if not symbol:
            raise ValueError("symbol required")
        if body.get("close_position"):
            qty = float(body.get("quantity", 0) or 0)
            for p in ib.positions():
                c = p.contract
                if p.account == account and c.symbol == symbol and abs(p.position) >= qty:
                    ib.qualifyContracts(c)
                    return c
            raise RuntimeError(f"no position {symbol} qty>={qty} in {account}")
        if sec_type == "STK":
            c = Stock(symbol, str(body.get("exchange") or "SMART"),
                      str(body.get("currency") or "USD"))
            ib.qualifyContracts(c)
            return c
        exchange = str(body.get("exchange") or FUT_EXCHANGE.get(symbol, "")).strip().upper()
        if not exchange:
            raise ValueError(f"default exchange unknown for {symbol}; exchange required")
        month = str(body.get("contract_month", "") or "")
        details = ib.reqContractDetails(Contract(
            symbol=symbol, secType="FUT", exchange=exchange,
            currency=str(body.get("currency") or "USD"),
            lastTradeDateOrContractMonth=month))
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        candidates = []
        for d in details:
            c = d.contract
            expiry = str(c.lastTradeDateOrContractMonth or "")
            if len(expiry) >= 8 and expiry[:8] < today:
                continue
            candidates.append((expiry, c))
        if not candidates:
            raise RuntimeError(f"no tradable future {symbol} {exchange} {month}")
        c = sorted(candidates, key=lambda x: x[0])[0][1]
        ib.qualifyContracts(c)
        return c

    def order(self, body: dict) -> dict:
        def job():
            ib = self.start()
            account = self._target_account(ib)
            contract = self._resolve_contract(ib, body, account)
            side = str(body.get("side", "buy")).strip().lower()
            if side not in ("buy", "sell"):
                raise ValueError("side must be buy/sell")
            qty = float(body.get("quantity", 0) or 0)
            if qty <= 0:
                raise ValueError("quantity must be positive")
            otype = str(body.get("order_type", "MKT")).strip().upper()
            if otype == "LMT":
                px = float(body.get("limit_price", 0) or 0)
                if px <= 0:
                    raise ValueError("limit_price required for LMT")
                order = LimitOrder("BUY" if side == "buy" else "SELL", qty, px,
                                   account=account, tif="DAY")
            else:
                order = MarketOrder("BUY" if side == "buy" else "SELL", qty,
                                    account=account, tif="DAY")
            trade = ib.placeOrder(contract, order)
            ib.sleep(3)
            st = trade.orderStatus
            result = {"ok": True, "account": account, "order_id": trade.order.orderId,
                      "status": st.status, "filled": st.filled, "remaining": st.remaining,
                      "avg_fill_price": st.avgFillPrice,
                      "contract": {"symbol": contract.symbol, "sec_type": contract.secType,
                                   "exchange": contract.exchange, "currency": contract.currency,
                                   "last_trade": contract.lastTradeDateOrContractMonth,
                                   "con_id": contract.conId,
                                   "trading_class": contract.tradingClass}}
            if str(st.status or "").lower() in ("inactive", "apicancelled", "cancelled", "error"):
                result["ok"] = False
                result["error"] = st.whyHeld or st.status or "order inactive"
            return result
        return self.run_sync(job, 45)


manager = IBLiveManager()

# Time-based protective stop watcher (2h warn / 3h close; hedge legs exempt).
# Modes via TIME_STOP_MODE: off | audit(default) | enforce
try:
    from live_gateway.time_stop import TimeStopWatcher  # type: ignore
except ImportError:  # running as a single-file script from live_gateway/
    from time_stop import TimeStopWatcher  # type: ignore
# CTP 5m bar aggregation feed: created and connected BEFORE the watcher
# starts, so every tick has a ready feed (avoids import-order races).
try:
    from live_gateway.ctp_bars_feed import CtpBarsFeed
except ImportError:
    from ctp_bars_feed import CtpBarsFeed

ctp_bars_feed = CtpBarsFeed()

try:
    from ctp_client.ctp_worker import _load_config
    _feed_cfg = _load_config(CTP_PROFILE)
except Exception:  # noqa: BLE001
    _feed_cfg = None
if _feed_cfg and _feed_cfg.get("md_server"):
    ctp_bars_feed.start(_feed_cfg)

time_stop = TimeStopWatcher(manager)

# CTP live positions feed for the watcher: read-only. No closer is wired,
# so even in enforce mode CTP lots can only notify, never auto-close.
# Gives CTP lots underwater-time sampling (float_pnl based); ER/MFE/giveback
# stay n/a until a 5m bar source for CTP is available.
def _ctp_positions_for_watcher():
    try:
        ok, snap = _ctp_worker("positions", timeout=30)
        if not ok:
            return None
        positions = snap.get("positions") or []
        try:
            if not getattr(ctp_bars_feed, "_started", False):
                _proj_root = Path(__file__).resolve().parents[1]
                if str(_proj_root) not in sys.path:
                    sys.path.insert(0, str(_proj_root))
                from ctp_client.ctp_worker import _load_config
                lazy_cfg = _load_config(CTP_PROFILE)
                if lazy_cfg and lazy_cfg.get("md_server"):
                    ctp_bars_feed.start(lazy_cfg)
                    time_stop._audit("ctp_feed_lazy_start",
                                     {"root_list": [pp.get("symbol") for pp in positions]})
            ctp_bars_feed.set_targets(p.get("symbol") for p in positions)
        except Exception as feed_err:  # noqa: BLE001
            time_stop._audit("ctp_feed_lazy_failed", {"error": str(feed_err)[:200]})
        return positions
    except Exception:  # noqa: BLE001
        return None


time_stop.set_ctp_provider(_ctp_positions_for_watcher)
time_stop.set_ctp_bars_provider(lambda sym: ctp_bars_feed.bars(sym))
time_stop.start()



def _real_money_denied() -> str | None:
    if request.headers.get("X-Real-Money") != "CONFIRM":
        return "missing X-Real-Money: CONFIRM header"
    return None


def _denied_response():
    return jsonify({"ok": False, "status": "unauthorized",
                    "error": "missing X-Real-Money: CONFIRM header"}), 401


# ───────────────────────── health + IB live routes ─────────────────────────

@app.get("/health")
def health():
    try:
        info = manager.account()
        return jsonify({"ok": True, "service": "live-gateway", "ib_live": True,
                        "account_id": info["account_id"], "managed": info["managed"]})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)}), 503


@app.get("/api/ib/live/account")
def ib_live_account():
    try:
        return jsonify(manager.account())
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 503


@app.get("/api/ib/live/positions")
def ib_live_positions():
    try:
        rows = manager.positions()
        return jsonify({"positions": rows, "count": len(rows)})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 503


@app.get("/api/ib/live/orders")
def ib_live_orders():
    try:
        rows = manager.open_orders()
        return jsonify({"orders": rows, "count": len(rows)})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 503


@app.get("/api/ib/live/trades")
def ib_live_trades():
    try:
        rows = manager.fills()
        return jsonify({"trades": rows, "count": len(rows)})
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 503


@app.get("/api/ib/live/time-stop/status")
def ib_live_time_stop_status():
    try:
        return jsonify(time_stop.status())
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 503


@app.post("/api/ib/live/time-stop/desync-clear")
def ib_live_time_stop_desync_clear():
    """清除指定品种的 desync 告警（人工核查持仓一致后调用）。
    body: {"symbol": "GBP"}"""
    body = request.get_json(force=True, silent=True) or {}
    sym = str(body.get("symbol") or "").strip()
    if not sym:
        return jsonify({"error": "symbol required"}), 400
    result = time_stop.clear_desync(sym)
    return jsonify(result)

@app.post("/api/ib/live/time-stop/tick")
def ib_live_time_stop_tick():
    """Manual evaluation tick (useful for checks). Never places orders unless
    TIME_STOP_MODE=enforce and a lot actually breaches the 3h limit."""
    try:
        time_stop.tick()
        return jsonify(time_stop.status())
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 503


@app.post("/api/ib/live/order")
def ib_live_order():
    if _real_money_denied():
        return _denied_response()
    body = request.get_json(force=True, silent=True) or {}
    try:
        result = manager.order(body)
        return jsonify(result), 200 if result.get("ok") else 503
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "status": "error", "error": str(e)}), 500


@app.post("/api/ib/live/cancel")
def ib_live_cancel():
    if _real_money_denied():
        return _denied_response()
    body = request.get_json(force=True, silent=True) or {}
    try:
        result = manager.cancel_order(body)
        return jsonify(result)
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "status": "error", "error": str(e)}), 500


# ───────────────────────── CTP live routes (explicit, no proxy fallback) ─────────────────────────

@app.get("/api/ctp/account")
def ctp_live_account():
    ok, snap = _ctp_worker("query", use_cache=True, timeout=30.0)
    if not ok:
        return jsonify({"error": snap.get("error") or "account data not available", **{
            k: snap.get(k) for k in ("status", "profile")}}), _ctp_http_code(ok, snap)
    return jsonify({"account": snap.get("account"), "status": snap.get("status"),
                    "investor": snap.get("investor"), "trading_day": snap.get("trading_day"),
                    "profile": CTP_PROFILE, "label": snap.get("label", CTP_PROFILE)})


@app.get("/api/ctp/feed-debug")
def ctp_feed_debug():
    out = ctp_bars_feed.stats()
    out["bars_fu2611"] = ctp_bars_feed.bars("fu2611")[-3:]
    return jsonify(out)


@app.get("/api/ctp/positions")
def ctp_live_positions():
    ok, snap = _ctp_worker("query", use_cache=True, timeout=30.0)
    if not ok:
        return jsonify({"error": snap.get("error") or "positions not available",
                        "positions": [], **{k: snap.get(k) for k in ("status", "profile")}},
                       ), _ctp_http_code(ok, snap)
    positions = snap.get("positions", [])
    return jsonify({"positions": positions, "count": len(positions),
                    "status": snap.get("status"), "profile": CTP_PROFILE})


@app.get("/api/ctp/trades")
def ctp_live_trades():
    instrument = (request.args.get("instrument", "") or "").strip()
    order = {"instrument_id": instrument} if instrument else {}
    ok, res = _ctp_worker("trades", order, timeout=40.0)
    if not ok:
        return jsonify(res), _ctp_http_code(ok, res)
    return jsonify({"ok": True, "profile": CTP_PROFILE,
                    "investor": res.get("investor"), "trading_day": res.get("trading_day"),
                    "trades": res.get("trades", []), "orders": res.get("orders", [])})


@app.get("/api/ctp/orders")
def ctp_live_orders():
    instrument = (request.args.get("instrument", "") or "").strip()
    order = {"instrument_id": instrument} if instrument else {}
    ok, res = _ctp_worker("trades", order, timeout=40.0)
    if not ok:
        return jsonify(res), _ctp_http_code(ok, res)
    return jsonify({"ok": True, "profile": CTP_PROFILE,
                    "investor": res.get("investor"), "trading_day": res.get("trading_day"),
                    "orders": res.get("orders", [])})


@app.get("/api/ctp/depth")
def ctp_live_depth():
    instrument = (request.args.get("instrument", "") or "").strip()
    if not instrument:
        return jsonify({"ok": False, "error": "缺少 instrument（合约代码，如 au2610）"}), 400
    ok, res = _ctp_worker("depth", {"instrument_id": instrument}, timeout=40.0)
    if not ok or not res.get("depth"):
        return jsonify(res), _ctp_http_code(ok, res) if not ok else 502
    return jsonify({"ok": True, "profile": CTP_PROFILE, "depth": res.get("depth")})


@app.get("/api/ctp/instruments")
def ctp_live_instruments():
    product = (request.args.get("product", "") or "").strip()
    exchange = (request.args.get("exchange", "") or "").strip()
    if not product:
        return jsonify({"ok": False, "error": "缺少 product（品种字母代码，如 IC/IF/AU）"}), 400
    ok, res = _ctp_worker("instruments", {"product": product, "exchange_id": exchange},
                          timeout=40.0)
    return jsonify(res), _ctp_http_code(ok, res) if not ok else 200


@app.get("/api/ctp/main-contract")
def ctp_live_main_contract():
    product = (request.args.get("product", "") or "").strip()
    exchange = (request.args.get("exchange", "") or "").strip()
    if not product:
        return jsonify({"ok": False, "error": "缺少 product（如 IC）"}), 400
    ok, res = _ctp_worker("main_contract", {"product": product, "exchange_id": exchange},
                          timeout=45.0)
    if not ok:
        return jsonify(res), _ctp_http_code(ok, res)
    return jsonify({"ok": True, "product": product.upper(),
                    "exchange": exchange.upper() or None, "profile": CTP_PROFILE,
                    "main_by": res.get("main_by", "open_interest"),
                    "main_contract": res.get("main_contract"),
                    "front_contract": res.get("front_contract"),
                    "instruments": res.get("instruments", []),
                    "tradable_count": res.get("tradable_count", 0)})


@app.get("/api/ctp/main-board")
def ctp_live_main_board():
    products, err = _parse_products(request.args.get("products", ""))
    if err:
        return jsonify({"ok": False, "status": "bad_products", "error": err}), 400
    force_refresh = str(request.args.get("refresh", "") or "").lower() in ("1", "true", "yes")
    if force_refresh:
        with _ctp_query_lock:
            _ctp_query_cache["data"] = None
    ok, res = _ctp_worker("main_board", {"products": products}, timeout=75.0)
    if not ok:
        return jsonify(res), _ctp_http_code(ok, res)
    return jsonify(res), 200


@app.post("/api/ctp/order")
def ctp_live_order():
    if _real_money_denied():
        return _denied_response()
    body = request.get_json(force=True, silent=True) or {}
    if not body.get("instrument_id"):
        return jsonify({"ok": False, "error": "缺少必填字段: ['instrument_id']"}), 400
    if str(body.get("price_type", "2")) == "2" and not float(body.get("price", 0) or 0) > 0:
        return jsonify({"ok": False, "error": "限价单必须提供 price>0"}), 400
    if int(float(body.get("volume", 0) or 0)) <= 0:
        return jsonify({"ok": False, "error": "volume 必须为正整数"}), 400
    ok, res = _ctp_worker("order", body, timeout=40.0)
    return jsonify(res), _ctp_http_code(ok, res)


@app.post("/api/ctp/cancel")
def ctp_live_cancel():
    if _real_money_denied():
        return _denied_response()
    body = request.get_json(force=True, silent=True) or {}
    if not body.get("instrument_id"):
        return jsonify({"ok": False, "error": "缺少 instrument_id"}), 400
    if not (body.get("order_sys_id") or body.get("order_ref")):
        return jsonify({"ok": False,
                        "error": "需提供 order_ref(+front_id/session_id)（推荐）或 order_sys_id"}), 400
    ok, res = _ctp_worker("cancel", body, timeout=40.0)
    return jsonify(res), _ctp_http_code(ok, res)


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, threaded=True, debug=False, use_reloader=False)
