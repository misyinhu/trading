#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CTP/SimNow 子进程 worker（独立进程运行，原生崩溃只杀自己）。

Flask 主服务以 subprocess 方式调起本脚本：连接前置 → 认证 → 登录 → 结算单
确认 → 查询账户资金 → 查询持仓，结果以 RESULT_JSON=... 单行打到 stdout 后退出。
CTP SWIG 原生层（.pyd，仅 cp313）若在某回调崩溃，只会终止本 worker，
主服务读到非零退出/无 JSON 即按"柜台不可用"降级，绝不拖垮 Flask。

关键实现约定（避免原生 abort）：
- thosttraderapi 在模块级导入；Spi 回调类也定义在模块级。CTP 在自己的工作
  线程回调，若类/模块是函数内局部对象，SWIG 类型解析异常会引发原生 abort。
- api/spi 保持模块级强引用，防止 GC 悬空。
- 不导入 yaml（libyaml C 扩展与 CTP 回调线程的 GIL 交互不稳），配置用 stdlib 解析。
"""
from __future__ import annotations

import json
import os
import sys
import time
import faulthandler
from pathlib import Path

faulthandler.enable()

_CTP_SWG_PATH = r"C:\tmp\ctp_api\ctp_swig_build-6.7.11.1\ctp_api"
if Path(_CTP_SWG_PATH).exists():
    sys.path.insert(0, _CTP_SWG_PATH)

try:
    import thosttraderapi as T  # noqa: E402
except Exception as _imp_err:  # noqa: BLE001
    T = None
    _IMP_ERR = str(_imp_err)
else:
    _IMP_ERR = ""

_API = None
_STATE: dict = {}


def _log(msg: str) -> None:
    print(f"[ctp] {msg}", file=sys.stderr, flush=True)


def _load_config() -> dict:
    """从 settings.yaml(simnow 块) + .streamlit/secrets.toml 读取（纯 stdlib）。"""
    root = Path(__file__).resolve().parent.parent
    yaml_path = root / "config" / "settings.yaml"
    secrets_path = root / ".streamlit" / "secrets.toml"
    sn: dict = {}
    if yaml_path.exists():
        in_block = False
        for raw in open(yaml_path, encoding="utf-8"):
            body = raw.split("#", 1)[0]
            kv = body.strip()
            if raw.startswith("simnow:"):
                in_block = True
                continue
            if in_block:
                if kv and not raw[:1].isspace() and ":" in kv:
                    break
                if kv and ":" in kv:
                    k, _, v = kv.partition(":")
                    sn[k.strip()] = v.strip().strip('"').strip("'")
    user = password = ""
    if secrets_path.exists():
        try:
            import tomllib
            sec = tomllib.load(open(secrets_path, "rb"))
            user = sec.get("SIMNOW_SIM_USER", "")
            password = sec.get("SIMNOW_SIM_PASSWORD", "")
        except Exception as e:  # noqa: BLE001
            _log(f"secrets read fail: {e}")
    return {
        "md_server": sn.get("md_server", "tcp://182.254.243.31:30011"),
        "td_server": sn.get("td_server", "tcp://182.254.243.31:30001"),
        "broker_id": sn.get("broker_id", "9999"),
        "auth_code": sn.get("auth_code", "0000000000000000"),
        "app_id": sn.get("app_id", "simnow_client_test"),
        "user": os.environ.get("SIMNOW_USER", user),
        "password": os.environ.get("SIMNOW_PASSWORD", password),
    }


def _num(p, *names):
    for nm in names:
        try:
            v = getattr(p, nm)
            if v not in (None, ""):
                return float(v)
        except Exception:  # noqa: BLE001
            pass
    return None


class TraderSpi(T.CThostFtdcTraderSpi if T is not None else object):
    """交易 SPI 回调（模块级类，CTP 工作线程驱动）。"""

    def __init__(self, api, cfg, state):
        if T is not None:
            super().__init__()
        self.api = api
        self.cfg = cfg
        self.state = state
        self._rid = 100

    def _nrid(self):
        self._rid += 1
        return self._rid

    def OnFrontConnected(self):
        self.state["phase"] = "authenticating"
        _log("front connected -> authenticate")
        f = T.CThostFtdcReqAuthenticateField()
        f.BrokerID = self.cfg["broker_id"]
        f.UserID = self.cfg["user"]
        f.AppID = self.cfg["app_id"]
        f.AuthCode = self.cfg["auth_code"]
        self.api.ReqAuthenticate(f, self._nrid())

    def OnFrontDisConnected(self, reason):
        self.state["phase"] = "disconnected"
        self.state["error"] = f"front disconnected reason={reason}"
        _log(self.state["error"])

    def OnRspAuthenticate(self, p, info, n, b):
        err = getattr(info, "ErrorID", 0) if info else 0
        if err:
            self.state["phase"] = "error"
            self.state["error"] = f"auth failed [{err}] {getattr(info,'ErrorMsg','')}"
            _log(self.state["error"])
            return
        _log("auth ok -> login")
        self.state["phase"] = "logging_in"
        f = T.CThostFtdcReqUserLoginField()
        f.BrokerID = self.cfg["broker_id"]
        f.UserID = self.cfg["user"]
        f.Password = self.cfg["password"]
        self.api.ReqUserLogin(f, self._nrid())

    def OnRspUserLogin(self, p, info, n, b):
        err = getattr(info, "ErrorID", 0) if info else 0
        if err:
            self.state["phase"] = "error"
            self.state["error"] = f"login failed [{err}] {getattr(info,'ErrorMsg','')}"
            _log(self.state["error"])
            return
        try:
            # 登录响应 CThostFtdcRspUserLoginField 用 UserID（非 InvestorID）；
            # 直接访问不存在的 SWIG 字段会触发原生 abort，故用 getattr 兜底。
            inv = getattr(p, "UserID", None) or self.cfg["user"]
            _log(f"login ok user={inv} trading_day={getattr(p,'TradingDay',None)} -> settlement confirm")
            self.state["investor"] = inv
            self.state["trading_day"] = getattr(p, "TradingDay", "")
            self.state["logined"] = True
            sc = T.CThostFtdcSettlementInfoConfirmField()
            sc.BrokerID = self.cfg["broker_id"]
            sc.InvestorID = inv
            self.api.ReqSettlementInfoConfirm(sc, self._nrid())
        except Exception as e:  # noqa: BLE001
            _log(f"post-login handler error: {type(e).__name__}: {e}")
            self.state["phase"] = "error"
            self.state["error"] = f"post-login error: {e}"

    def OnRspSettlementInfoConfirm(self, p, info, n, last):
        err = getattr(info, "ErrorID", 0) if info else 0
        if err:
            _log(f"settlement confirm [{err}] {getattr(info,'ErrorMsg','')}（继续尝试查询）")
        else:
            self.state["settled"] = True
            _log("settlement confirmed -> query account")
        q = T.CThostFtdcQryTradingAccountField()
        q.BrokerID = self.cfg["broker_id"]
        q.InvestorID = self.state["investor"]
        self.api.ReqQryTradingAccount(q, self._nrid())

    def OnRspQryTradingAccount(self, p, info, n, last):
        if p is not None:
            self.state["account"] = {
                "account_id": getattr(p, "AccountID", self.state["investor"]),
                "balance": _num(p, "Balance"),
                "available": _num(p, "Available", "AvailableFunds"),
                "margin": _num(p, "CurrMargin", "Margin"),
                "frozen_margin": _num(p, "FrozenMargin", "FrozenCash"),
                "position_pnl": _num(p, "PositionProfit"),
                "close_pnl": _num(p, "CloseProfit"),
                "commission": _num(p, "Commission"),
                "currency": "CNY",
            }
            acc = self.state["account"]
            _log(f"account: balance={acc['balance']} available={acc['available']}")
        self.state["acct_done"] = True
        if last:
            _log("account done -> query positions")
            q = T.CThostFtdcQryInvestorPositionField()
            q.BrokerID = self.cfg["broker_id"]
            q.InvestorID = self.state["investor"]
            self.api.ReqQryInvestorPosition(q, self._nrid())

    def OnRspQryInvestorPosition(self, p, info, n, last):
        if p is not None:
            try:
                vol = getattr(p, "Position", 0) or 0
                if float(vol) != 0:
                    self.state["positions"].append({
                        "symbol": getattr(p, "InstrumentID", ""),
                        "direction": str(getattr(p, "Direction", "")),
                        "volume": int(float(vol)),
                        "avg_price": float(getattr(p, "PositionCost", 0) or 0),
                        "float_pnl": float(getattr(p, "PositionProfit", 0) or 0),
                    })
            except Exception as e:  # noqa: BLE001
                _log(f"position parse fail: {e}")
        if last:
            self.state["pos_done"] = True
            _log(f"positions done: {len(self.state['positions'])}")

    def OnRspError(self, info, n, b):
        err = getattr(info, "ErrorID", None)
        msg = getattr(info, "ErrorMsg", None)
        _log(f"OnRspError [{err}] {msg}")
        if not self.state.get("logined"):
            self.state["phase"] = "error"
            self.state["error"] = f"rsp error [{err}] {msg}"


def run(timeout: float = 25.0) -> dict:
    global _API, _SPI, _STATE
    if not Path(_CTP_SWG_PATH).exists():
        return {"ok": False, "status": "unavailable", "error": f"CTP SWIG not found: {_CTP_SWG_PATH}"}
    if T is None:
        return {"ok": False, "status": "unavailable", "error": f"import thosttraderapi fail: {_IMP_ERR}"}

    cfg = _load_config()
    _STATE = state = {"phase": "init", "error": "", "investor": "", "trading_day": "",
                      "account": None, "positions": [], "logined": False,
                      "settled": False, "acct_done": False, "pos_done": False}

    api = T.CThostFtdcTraderApi.CreateFtdcTraderApi("")
    spi = TraderSpi(api, cfg, state)
    _API, _SPI = api, spi
    api.RegisterSpi(spi)
    api.SubscribePrivateTopic(2)
    api.SubscribePublicTopic(2)
    api.RegisterFront(cfg["td_server"])
    api.Init()

    deadline = time.time() + timeout
    while time.time() < deadline:
        if state["phase"] == "error":
            break
        if state["logined"] and state["pos_done"]:
            break
        time.sleep(0.2)

    try:
        api.Release()
    except Exception:  # noqa: BLE001
        pass

    if state["phase"] == "error":
        return {"ok": False, "status": "error", "error": state["error"] or "unknown"}
    if not state["logined"]:
        return {"ok": False, "status": "timeout", "error": f"login timeout (phase={state['phase']})"}
    return {
        "ok": True, "status": "logined",
        "investor": state["investor"], "trading_day": state["trading_day"],
        "settled": state["settled"], "account": state["account"],
        "positions": state["positions"],
    }


if __name__ == "__main__":
    try:
        result = run()
    except Exception as e:  # noqa: BLE001  # 兜底（原生崩溃不走这里）
        result = {"ok": False, "status": "crash_py", "error": f"{type(e).__name__}: {e}"}
    print("RESULT_JSON=" + json.dumps(result, ensure_ascii=False), flush=True)
    sys.exit(0 if result.get("ok") else 2)
