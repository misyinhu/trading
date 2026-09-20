"""实盘网关 5006 单元测试：CTP 子进程直连（profile=live 强制）、实盘确认头、
IB 活动委托/成交映射，以及 5002 仿真桥对 live 的 fail-closed 收口。"""
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_live_gateway():
    spec = importlib.util.spec_from_file_location(
        "live_gateway_app_under_test", REPO_ROOT / "live_gateway" / "live_gateway_app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lg = _load_live_gateway()


class FakeProc:
    def __init__(self, payload=None, stdout="", returncode=0):
        if payload is not None:
            stdout = "RESULT_JSON=" + json.dumps(payload, ensure_ascii=True)
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


@pytest.fixture(autouse=True)
def _clear_ctp_query_cache():
    lg._ctp_query_cache["data"] = None
    lg._ctp_query_cache["ts"] = 0.0
    yield


@pytest.fixture
def client():
    lg.app.config["TESTING"] = True
    return lg.app.test_client()


@pytest.fixture
def captured_runs(monkeypatch):
    """拦截子进程调用，记录 (argv, env, timeout)，按队列返回结果。"""
    calls = []
    results = []

    def fake_run(argv, **kw):
        calls.append({"argv": argv, "env": kw.get("env"), "timeout": kw.get("timeout")})
        if not results:
            raise AssertionError("no fake subprocess result queued")
        item = results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(lg.subprocess, "run", fake_run)
    return calls, results


CONFIRM = {"X-Real-Money": "CONFIRM"}


# ── CTP: profile 强制与请求伪造隔离 ──

def test_ctp_account_forces_live_profile(client, captured_runs):
    calls, results = captured_runs
    results.append(FakeProc({"ok": True, "status": "logined", "account": {"Available": 1}}))
    r = client.get("/api/ctp/account?profile=simnow&account=citic")
    assert r.status_code == 200
    assert r.get_json()["profile"] == "live"
    env = calls[0]["env"]
    assert env["CTP_PROFILE"] == "live"
    assert env["CTP_ACTION"] == "query"
    assert Path(calls[0]["argv"][-1]).name == "ctp_worker.py"


def test_ctp_post_order_strips_caller_profile(client, captured_runs):
    calls, results = captured_runs
    results.append(FakeProc({"ok": True, "status": "accepted"}))
    body = {"instrument_id": "au2610", "price": 900, "volume": 1,
            "profile": "simnow", "account": "citic"}
    r = client.post("/api/ctp/order", json=body, headers=CONFIRM)
    assert r.status_code == 200
    order_json = json.loads(calls[0]["env"]["CTP_ORDER_JSON"])
    assert "profile" not in order_json and "account" not in order_json
    assert calls[0]["env"]["CTP_PROFILE"] == "live"


def test_ctp_post_requires_real_money_header(client):
    r = client.post("/api/ctp/order", json={"instrument_id": "au2610"})
    assert r.status_code == 401
    assert r.get_json()["status"] == "unauthorized"


def test_ctp_cancel_requires_real_money_header(client):
    r = client.post("/api/ctp/cancel", json={"instrument_id": "au2610", "order_ref": "7"})
    assert r.status_code == 401


def test_ctp_unknown_path_404(client):
    # 不允许 catch-all 透传到 5002
    r = client.get("/api/ctp/definitely-not-a-route")
    assert r.status_code == 404


# ── CTP: worker 结果/异常映射 ──

def test_ctp_subprocess_timeout_is_503(client, captured_runs):
    _calls, results = captured_runs
    results.append(subprocess.TimeoutExpired(cmd=["py"], timeout=40))
    r = client.get("/api/ctp/positions")
    assert r.status_code == 503
    assert r.get_json()["status"] == "timeout"


def test_ctp_subprocess_native_crash_is_503(client, monkeypatch):
    def fake_run(argv, **kw):
        class P:
            stdout = "some [ctp] native abort line"
            stderr = "[ctp] abort"
            returncode = -11
        return P()
    monkeypatch.setattr(lg.subprocess, "run", fake_run)
    r = client.get("/api/ctp/positions")
    assert r.status_code == 503
    assert r.get_json()["status"] == "crashed"


def test_ctp_orders_returns_orders_from_trades_action(client, captured_runs):
    calls, results = captured_runs
    results.append(FakeProc({"ok": True, "orders": [{"order_ref": "1"}],
                             "trades": [{"trade_id": "9"}]}))
    r = client.get("/api/ctp/orders")
    assert r.status_code == 200
    data = r.get_json()
    assert [o["order_ref"] for o in data["orders"]] == ["1"]
    assert "trades" not in data
    assert calls[0]["env"]["CTP_ACTION"] == "trades"


def test_ctp_trades_returns_both(client, captured_runs):
    _calls, results = captured_runs
    results.append(FakeProc({"ok": True, "orders": [1], "trades": [2]}))
    r = client.get("/api/ctp/trades")
    assert r.status_code == 200
    data = r.get_json()
    assert data["orders"] == [1] and data["trades"] == [2]


def test_ctp_order_validation_400(client, captured_runs):
    calls, _ = captured_runs
    r = client.post("/api/ctp/order", json={"instrument_id": "au2610", "price": 0},
                    headers=CONFIRM)
    assert r.status_code == 400
    assert calls == []


def test_ctp_query_cache_single_subprocess(client, captured_runs):
    calls, results = captured_runs
    payload = {"ok": True, "status": "logined",
               "account": {"a": 1}, "positions": [{"instrument_id": "au2610"}]}
    results.append(FakeProc(payload))
    assert client.get("/api/ctp/account").status_code == 200
    assert client.get("/api/ctp/positions").status_code == 200
    assert len(calls) == 1


# ── CTP main-board products 解析 ──

def test_parse_products_default_and_custom():
    default, err = lg._parse_products("")
    assert err is None and ("au", "SHFE") in [(p["product"], p["exchange"]) for p in default]
    products, err = lg._parse_products("au:SHFE, IC:CFFEX")
    assert err is None
    assert products == [{"product": "au", "exchange": "SHFE"},
                        {"product": "IC", "exchange": "CFFEX"}]
    _p, err = lg._parse_products("bad-item")
    assert err and "product:exchange" in err


# ── IB 路由：确认头与字段映射 ──

def test_ib_order_and_cancel_require_header(client):
    assert client.post("/api/ib/live/order", json={"symbol": "GC"}).status_code == 401
    assert client.post("/api/ib/live/cancel", json={"order_id": 1}).status_code == 401


def test_ib_open_orders_mapping(monkeypatch):
    o = SimpleNamespace(account="U8590961", orderId=55, action="BUY", totalQuantity=2,
                        orderType="LMT", lmtPrice=2500.5, tif="DAY")
    c = SimpleNamespace(symbol="GC", exchange="COMEX", currency="USD", secType="FUT",
                        conId=123, lastTradeDateOrContractMonth="202612", tradingClass="GC")
    st = SimpleNamespace(status="PreSubmitted", filled=0, remaining=2, avgFillPrice=0)
    fake_ib = SimpleNamespace(openTrades=lambda: [SimpleNamespace(order=o, contract=c,
                                                                  orderStatus=st)])
    monkeypatch.setattr(lg.manager, "start", lambda: fake_ib)
    monkeypatch.setattr(lg.manager, "run_sync", lambda fn, timeout=30: fn())
    monkeypatch.setattr(lg.manager, "_target_account", lambda ib: "U8590961")
    rows = lg.manager.open_orders()
    assert rows[0]["order_id"] == 55
    assert rows[0]["symbol"] == "GC"
    assert rows[0]["limit_price"] == 2500.5
    assert rows[0]["status"] == "PreSubmitted"


def test_ib_fills_mapping(monkeypatch):
    from datetime import datetime as dt
    e = SimpleNamespace(execId="exec-1", orderId=55, time=dt(2026, 9, 19, 12, 0),
                        acctNumber="U8590961", exchange="COMEX", side="BOT",
                        shares=2.0, price=2501.0, cumQty=2.0, avgPrice=2501.0)
    c = SimpleNamespace(symbol="GC", exchange="COMEX", currency="USD", secType="FUT",
                        conId=123, lastTradeDateOrContractMonth="202612", tradingClass="GC")
    fake_ib = SimpleNamespace(fills=lambda: [SimpleNamespace(execution=e, contract=c,
                                                             commission=4.2)])
    monkeypatch.setattr(lg.manager, "start", lambda: fake_ib)
    monkeypatch.setattr(lg.manager, "run_sync", lambda fn, timeout=30: fn())
    monkeypatch.setattr(lg.manager, "_target_account", lambda ib: "U8590961")
    rows = lg.manager.fills()
    row = rows[0]
    assert row["exec_id"] == "exec-1"
    assert row["side"] == "BOT" and row["commission"] == 4.2
    assert row["time"].startswith("2026-09-19T12:00:00")


def test_ib_orders_trades_endpoints(monkeypatch, client):
    monkeypatch.setattr(lg.manager, "open_orders", lambda: [{"order_id": 1}])
    monkeypatch.setattr(lg.manager, "fills", lambda: [{"exec_id": "x"}])
    r1 = client.get("/api/ib/live/orders")
    r2 = client.get("/api/ib/live/trades")
    assert r1.get_json()["count"] == 1 and r2.get_json()["count"] == 1


# ── 5002 仿真桥收口：profile=live fail-closed ──

def test_bridge_rejects_live_profile():
    import notify.webhook_bridge as wb
    assert wb._ctp_norm_profile("live") is None
    assert wb._ctp_norm_profile("simnow") == "simnow"
    assert wb._ctp_norm_profile("citic") == "citic"
    assert wb._ctp_norm_profile("bogus") is None
