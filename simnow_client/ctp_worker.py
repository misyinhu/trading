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

# CTP API 版本随账号 profile 不同：SimNow 用 6.7.11.1；中信评测柜台用 6.6.8
# （前置协议版本不匹配会握手 decode err，故中信必须加载 6.6.8 动态库/绑定）。
_CTP_SWG_PATHS = {
    "simnow": r"C:\tmp\ctp_api\ctp_swig_build-6.7.11.1\ctp_api",
    # 中信看穿式(CP)评测：必须用 CP 版交易库 v6.7.7_CP + 终端采集库 WinDataCollect.dll，
    # 否则前置握手 "Front shake hand err: decode err / Decrypt handshake data failed"。
    # 实测评测前置匹配 v6.5.1_CP 参考套件（自带同源 WinDataCollect）；6.7.7CP 会终端校验失败 [3]。
    "citic": r"C:\tmp\ctp_api\ctp_swig_build-6.5.1cp\ctp_api",
}
_profile_early = os.environ.get("CTP_PROFILE", "simnow").strip().lower()
_CTP_SWG_PATH = _CTP_SWG_PATHS.get(_profile_early, _CTP_SWG_PATHS["simnow"])
if Path(_CTP_SWG_PATH).exists():
    sys.path.insert(0, _CTP_SWG_PATH)
    try:
        os.add_dll_directory(_CTP_SWG_PATH)  # 看穿式 thosttraderapi_se 运行时加载 WinDataCollect.dll
    except (AttributeError, OSError):
        pass
    # 把绑定目录并入工作目录搜索，兼容 LoadLibrary 按 cwd 找 WinDataCollect.dll
    try:
        os.environ["PATH"] = _CTP_SWG_PATH + os.pathsep + os.environ.get("PATH", "")
    except Exception:  # noqa: BLE001
        pass

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


# CTP 多账号 profile：simnow=官方仿真；citic=中信期货仿真（独立券商通道，与 SimNow 平级）。
# 每个 profile 指定 settings.yaml 中的块名 + secrets.toml / 环境变量的键名。
_PROFILES = {
    "simnow": {
        "block": "simnow",
        "secrets": {"user": "SIMNOW_SIM_USER", "password": "SIMNOW_SIM_PASSWORD",
                    "auth_code": None, "app_id": None, "broker_id": None,
                    "td_server": None, "md_server": None},
        "env": {"user": "SIMNOW_USER", "password": "SIMNOW_PASSWORD"},
    },
    "citic": {
        "block": "citic",
        "secrets": {"user": "CITIC_CTP_USER", "password": "CITIC_CTP_PASSWORD",
                    "auth_code": "CITIC_CTP_AUTH_CODE", "app_id": "CITIC_CTP_APP_ID",
                    "broker_id": "CITIC_CTP_BROKER_ID", "td_server": "CITIC_CTP_TD_SERVER",
                    "md_server": "CITIC_CTP_MD_SERVER"},
        "env": {"user": "CITIC_CTP_USER", "password": "CITIC_CTP_PASSWORD",
                "auth_code": "CITIC_CTP_AUTH_CODE", "app_id": "CITIC_CTP_APP_ID",
                "broker_id": "CITIC_CTP_BROKER_ID", "td_server": "CITIC_CTP_TD_SERVER",
                "md_server": "CITIC_CTP_MD_SERVER"},
    },
}


def _read_yaml_block(block: str) -> dict:
    """读取 settings.yaml 顶层 `block:` 下一层缩进的 key: value（纯 stdlib，去注释/引号）。"""
    root = Path(__file__).resolve().parent.parent
    yaml_path = root / "config" / "settings.yaml"
    out: dict = {}
    if not yaml_path.exists():
        return out
    in_block = False
    for raw in open(yaml_path, encoding="utf-8"):
        body = raw.split("#", 1)[0]
        kv = body.strip()
        if raw.startswith(f"{block}:"):
            in_block = True
            continue
        if in_block:
            if kv and not raw[:1].isspace() and ":" in kv:
                break
            if kv and ":" in kv:
                k, _, v = kv.partition(":")
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _load_config(profile: str = "simnow") -> dict:
    """按 profile 从 settings.yaml 块 + .streamlit/secrets.toml + 环境变量 组装 CTP 配置。"""
    prof = _PROFILES.get(profile, _PROFILES["simnow"])
    blk = _read_yaml_block(prof["block"])
    sec: dict = {}
    secrets_path = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
    if secrets_path.exists():
        try:
            import tomllib
            sec = tomllib.load(open(secrets_path, "rb"))
        except Exception as e:  # noqa: BLE001
            _log(f"secrets read fail: {e}")

    def _val(field: str, default: str = ""):
        env_key = prof["env"].get(field)
        if env_key and os.environ.get(env_key):
            return os.environ[env_key].strip()
        sec_key = prof["secrets"].get(field)
        if sec_key and sec.get(sec_key):
            return str(sec[sec_key]).strip()
        return blk.get(field, default)

    cfg = {
        "profile": profile,
        "md_server": _val("md_server", "tcp://182.254.243.31:30011"),
        "td_server": _val("td_server", "tcp://182.254.243.31:30001"),
        "broker_id": _val("broker_id", "9999"),
        "auth_code": _val("auth_code", "0000000000000000"),
        "app_id": _val("app_id", "simnow_client_test"),
        "user": _val("user", ""),
        "password": _val("password", ""),
        "label": blk.get("label", profile),
    }
    if profile != "simnow":
        # 非 SimNow 账号不给 SimNow 默认值，缺什么报什么，避免误连
        for k in ("td_server", "broker_id", "app_id", "auth_code", "user", "password"):
            if not cfg[k] or cfg[k] in ("9999", "simnow_client_test", "0000000000000000"):
                cfg.setdefault("_missing", []).append(k)
    return cfg


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

    def __init__(self, api, cfg, state, action="query", order=None):
        if T is not None:
            super().__init__()
        self.api = api
        self.cfg = cfg
        self.state = state
        self.action = action              # query / order / cancel / instruments
        self.order = order or {}
        self._rid = 100
        self._order_ref = ""
        self._settled_fired = False
        self._instr_done = False
        self._md_done = False
        self._pos_mult_queue = []
        self._pos_mult_map = {}
        self._detail_rows = []
        self._detail_deadline = 0.0
        self._detail_merged = False

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
            self.state["front_id"] = int(getattr(p, "FrontID", 0) or 0)
            self.state["session_id"] = int(getattr(p, "SessionID", 0) or 0)
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
            _log("settlement confirmed")
        self._settled_fired = True
        if self.action == "depth":
            try:
                self._do_depth_one()
            except Exception as e:
                _log(f"depth query submit error: {type(e).__name__}: {e}")
                self.state["depth_done"] = True
            return
        if self.action in ("instruments", "main_contract"):
            try:
                self._do_query_instruments()
            except Exception as e:  # noqa: BLE001
                _log(f"instrument query submit error: {type(e).__name__}: {e}")
                self._instr_done = True
            return
        if self.action == "trades":
            try:
                self._do_query_trades()
            except Exception as e:  # noqa: BLE001
                _log(f"trades query submit error: {type(e).__name__}: {e}")
                self.state["trades_done"] = True
            return
        if self.action in ("order", "cancel"):
            try:
                if self.action == "order":
                    self._do_order()
                else:
                    self._do_cancel()
            except Exception as e:  # noqa: BLE001
                _log(f"action submit error: {type(e).__name__}: {e}")
                self.state["action_done"] = True
                self.state["action_result"] = {"ok": False, "error": f"submit error: {e}"}
            return
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
                        # OpenCost=开仓总额(价×量×乘数)；均价待查到合约乘数后换算
                        "open_cost": float(getattr(p, "OpenCost", 0) or 0),
                        "avg_price": 0.0,
                        "float_pnl": float(getattr(p, "PositionProfit", 0) or 0),
                    })
            except Exception as e:  # noqa: BLE001
                _log(f"position parse fail: {e}")
        if last:
            self._start_position_detail()

    def _start_position_detail(self):
        # 快照路径：净持仓模式下聚合持仓的 PosiDirection='3'(净) 无法区分多空，
        # 且 OpenCost/PositionCost 为盯市口径。逐笔持仓明细(PositionDetail)
        # 权威给出 开仓方向(0买/1卖)、开仓价(OpenPrice)、开仓日期(OpenDate)。
        # 一次空合约号查询返回全部明细。
        if self.action in ("instruments", "main_contract"):
            self.state["pos_done"] = True
            return
        self._detail_rows = []
        f = T.CThostFtdcQryInvestorPositionDetailField()
        f.BrokerID = self.cfg["broker_id"]
        f.InvestorID = self.state["investor"]
        rc = self.api.ReqQryInvestorPositionDetail(f, self._nrid())
        self._detail_deadline = time.time() + 5.0  # 兜底：明细回调不来也强制收口
        if rc != 0:
            _log(f"ReqQryInvestorPositionDetail ret={rc} -> fallback to aggregate fields")
            self._merge_position_detail()

    def OnRspQryInvestorPositionDetail(self, p, info, n, last):
        if p is not None:
            try:
                vol = int(float(getattr(p, "Volume", 0) or 0))
                iid = str(getattr(p, "InstrumentID", "") or "")
                if iid and vol:
                    self._detail_rows.append({
                        "symbol": iid,
                        "direction": str(getattr(p, "Direction", "") or ""),
                        "volume": vol,
                        "open_price": float(getattr(p, "OpenPrice", 0) or 0),
                        "open_date": str(getattr(p, "OpenDate", "") or ""),
                    })
            except Exception as e:  # noqa: BLE001
                _log(f"position detail parse fail: {type(e).__name__}: {e}")
        if last:
            self._merge_position_detail()

    def _merge_position_detail(self):
        if self._detail_merged:
            return
        self._detail_merged = True
        # 按合约聚合明细：净多空方向 + 手数加权开仓均价 + 最早开仓日期
        agg = {}
        for r in getattr(self, "_detail_rows", []):
            d = agg.setdefault(r["symbol"], {"buy": 0, "sell": 0, "pv": 0.0,
                                             "dates": []})
            if r["direction"] == "1":
                d["sell"] += r["volume"]
            else:
                d["buy"] += r["volume"]
            d["pv"] += r["open_price"] * r["volume"]
            if r["open_date"]:
                d["dates"].append(r["open_date"])
        for pos in self.state.get("positions", []):
            sym = pos.get("symbol")
            d = agg.get(sym)
            pos.pop("open_cost", None)
            if d and (d["buy"] + d["sell"]) > 0:
                total = d["buy"] + d["sell"]
                pos["direction"] = "1" if d["sell"] > d["buy"] else "0"
                pos["avg_price"] = round(d["pv"] / total, 4)
                pos["open_date"] = min(d["dates"]) if d["dates"] else ""
            else:
                # 明细缺失：方向置空，均价回退为 0（避免把盯市总额误显示成单价）
                pos.setdefault("direction", "")
                pos["avg_price"] = 0.0
                pos["open_date"] = ""
        self.state["pos_done"] = True
        _log(f"positions done: {len(self.state.get('positions', []))} "
             f"(detail rows: {len(getattr(self, '_detail_rows', []))})")

    # ── 报单 / 撤单 ──────────────────────────────────────────────
    def _gen_order_ref(self) -> str:
        ref = f"{int(time.time() * 1000) % 100000000:08d}"
        self._order_ref = ref
        return ref

    def _do_order(self):
        o = self.order
        ref = self._gen_order_ref()
        f = T.CThostFtdcInputOrderField()
        f.BrokerID = self.cfg["broker_id"]
        f.InvestorID = self.state["investor"]
        f.UserID = self.cfg["user"]
        f.InstrumentID = str(o["instrument_id"])
        f.ExchangeID = str(o.get("exchange_id", ""))
        f.OrderRef = ref
        f.LimitPrice = float(o.get("price", 0.0))
        f.VolumeTotalOriginal = int(float(o.get("volume", 1)))
        f.Direction = str(o.get("direction", "0"))          # 0 买 / 1 卖
        f.CombOffsetFlag = str(o.get("offset_flag", "0"))   # 0 开 / 1 平 / 3 平今 / 4 平昨
        f.CombHedgeFlag = str(o.get("hedge_flag", "1"))     # 1 投机
        f.OrderPriceType = str(o.get("price_type", "2"))   # 2 限价 / 1 市价
        f.TimeCondition = "3"                               # GFD
        f.VolumeCondition = "1"                             # 任意数量
        f.MinVolume = 1
        f.ContingentCondition = "1"
        f.ForceCloseReason = "0"
        self.state["order_ref"] = ref
        self.state["action_result"] = {"ok": False, "order_ref": ref,
                                       "instrument_id": f.InstrumentID,
                                       "exchange_id": f.ExchangeID}
        _log(f"insert order ref={ref} {f.InstrumentID} dir={f.Direction} "
             f"off={f.CombOffsetFlag} px={f.LimitPrice} vol={f.VolumeTotalOriginal}")
        rc = self.api.ReqOrderInsert(f, self._nrid())
        if rc != 0:
            self.state["action_done"] = True
            self.state["action_result"] = {"ok": False, "order_ref": ref,
                                           "error": f"ReqOrderInsert ret={rc}"}

    def _do_query_trades(self):
        self.state["_trades_q_done"] = False
        self.state["_orders_q_done"] = False
        q = T.CThostFtdcQryTradeField()
        q.BrokerID = self.cfg["broker_id"]
        q.InvestorID = self.state["investor"]
        if self.order and str(self.order.get("instrument_id", "")).strip():
            q.InstrumentID = str(self.order["instrument_id"]).strip()
        _log("trades: ReqQryTrade today")
        rc = self.api.ReqQryTrade(q, self._nrid())
        if rc != 0:
            self.state["trades_done"] = True
            self.state["trades_error"] = f"ReqQryTrade ret={rc}"

    def _do_query_orders_only(self):
        q = T.CThostFtdcQryOrderField()
        q.BrokerID = self.cfg["broker_id"]
        q.InvestorID = self.state["investor"]
        if self.order and str(self.order.get("instrument_id", "")).strip():
            q.InstrumentID = str(self.order["instrument_id"]).strip()
        _log("trades: ReqQryOrder today")
        rc = self.api.ReqQryOrder(q, self._nrid())
        if rc != 0:
            self.state["_orders_q_done"] = True

    def OnRspQryTrade(self, p, info, n, last):
        if p is not None:
            try:
                rec = {
                    "trade_id": str(getattr(p, "TradeID", "") or ""),
                    "order_ref": str(getattr(p, "OrderRef", "") or ""),
                    "order_sys_id": str(getattr(p, "OrderSysID", "") or "").strip(),
                    "instrument_id": str(getattr(p, "InstrumentID", "") or ""),
                    "exchange_id": str(getattr(p, "ExchangeID", "") or ""),
                    "direction": str(getattr(p, "Direction", "") or ""),
                    "offset_flag": str(getattr(p, "OffsetFlag", "") or ""),
                    "price": _num(p, "Price"),
                    "volume": int(float(getattr(p, "Volume", 0) or 0)),
                    "trade_time": str(getattr(p, "TradeTime", "") or ""),
                }
                self.state.setdefault("trades", []).append(rec)
            except Exception as e:  # noqa: BLE001
                _log(f"qry trade parse fail: {e}")
        if last:
            self.state["_trades_q_done"] = True
            _log(f"qry trades done: {len(self.state.get('trades', []))}")
            self._do_query_orders_only()

    def _do_cancel(self):
        o = self.order
        sysid = str(o.get("order_sys_id", "") or "").strip()
        ref = str(o.get("order_ref", "") or "").strip()
        front = o.get("front_id")
        sess = o.get("session_id")
        # 跨连接撤单：若只有 order_ref、没有有效 sysid/session，先查当日委托补全。
        if not sysid and (ref or o.get("instrument_id")) and (not sess or int(sess or 0) == 0):
            self.state["_cancel_pending"] = {"ref": ref, "sysid": sysid}
            q = T.CThostFtdcQryOrderField()
            q.BrokerID = self.cfg["broker_id"]
            q.InvestorID = self.state["investor"]
            if o.get("instrument_id"):
                q.InstrumentID = str(o["instrument_id"])
            _log(f"cancel: query orders first to locate ref={ref}")
            rc = self.api.ReqQryOrder(q, self._nrid())
            if rc != 0:
                self.state["action_done"] = True
                self.state["action_result"] = {"ok": False,
                                               "error": f"ReqQryOrder ret={rc}"}
            return
        self._send_cancel(o, sysid=sysid, ref=ref, front=front, sess=sess)

    def _send_cancel(self, o, *, sysid, ref, front, sess):
        f = T.CThostFtdcInputOrderActionField()
        f.BrokerID = self.cfg["broker_id"]
        f.InvestorID = self.state["investor"]
        f.UserID = self.cfg["user"]
        f.InstrumentID = str(o["instrument_id"])
        f.ExchangeID = str(o.get("exchange_id", ""))
        f.ActionFlag = "0"  # 撤单
        # CTP 撤单标准键 = FrontID+SessionID+OrderRef（跨连接可靠）；
        # OrderSysID 撤单在 SimNow 跨连接偶发 [25]，仅作最后备选。
        have_ref = bool(ref) and (sess not in (None, 0, "0"))
        if have_ref:
            f.FrontID = int(front or self.state.get("front_id", 0))
            f.SessionID = int(sess)
            f.OrderRef = str(ref)
        elif sysid:
            f.OrderSysID = sysid
        else:
            f.FrontID = int(front or self.state.get("front_id", 0))
            f.SessionID = int(sess or self.state.get("session_id", 0))
            f.OrderRef = str(ref)
        self.state["action_result"] = {"ok": False, "cancel_for": ref or sysid,
                                       "instrument_id": f.InstrumentID}
        _log(f"cancel order ref={ref} sysid={sysid} front={f.FrontID if not sysid else '-'} sess={f.SessionID if not sysid else '-'} {f.InstrumentID}")
        rc = self.api.ReqOrderAction(f, self._nrid())
        if rc != 0:
            self.state["action_done"] = True
            self.state["action_result"] = {"ok": False,
                                           "error": f"ReqOrderAction ret={rc}"}

    def OnRspQryOrder(self, p, info, n, last):
        if p is not None:
            try:
                rec = {
                    "order_ref": str(getattr(p, "OrderRef", "") or ""),
                    "order_sys_id": str(getattr(p, "OrderSysID", "") or "").strip(),
                    "front_id": int(getattr(p, "FrontID", 0) or 0),
                    "session_id": int(getattr(p, "SessionID", 0) or 0),
                    "instrument_id": str(getattr(p, "InstrumentID", "") or ""),
                    "exchange_id": str(getattr(p, "ExchangeID", "") or ""),
                    "status": str(getattr(p, "OrderStatus", "") or ""),
                    "status_msg": str(getattr(p, "StatusMsg", "") or ""),
                    "direction": str(getattr(p, "Direction", "") or ""),
                    "offset_flag": str(getattr(p, "CombOffsetFlag", "") or ""),
                    "limit_price": _num(p, "LimitPrice"),
                    "volume_total": int(float(getattr(p, "VolumeTotal", 0) or 0)),
                    "volume_traded": int(float(getattr(p, "VolumeTraded", 0) or 0)),
                    "insert_time": str(getattr(p, "InsertTime", "") or ""),
                }
                self.state["orders"].append(rec)
            except Exception as e:  # noqa: BLE001
                _log(f"qry order parse fail: {e}")
        if last and self.action == "trades":
            self.state["_orders_q_done"] = True
            _log(f"qry orders done: {len(self.state.get('orders', []))}")
            return
        if last and self.state.get("_cancel_pending"):
            pend = self.state.pop("_cancel_pending")
            want_ref = pend.get("ref", "")
            want_iid = str(self.order.get("instrument_id", ""))
            # 找未成交/部分成交（status 1/2/3，'1'=PartTradedQueueing '2'=PartTradedNotQueueing '3'=NoTradeQueueing）
            active = [r for r in self.state["orders"]
                      if r["status"] in ("1", "2", "3", "a") and
                      (not want_ref or r["order_ref"] == want_ref) and
                      (not want_iid or r["instrument_id"] == want_iid)]
            _log(f"qry orders done: {len(self.state['orders'])} total, {len(active)} active")
            if not active:
                self.state["action_done"] = True
                self.state["action_result"] = {
                    "ok": False,
                    "error": f"未找到可撤挂单(ref={want_ref or 'any'}, {want_iid})；"
                             f"当日委托 {len(self.state['orders'])} 条"}
                return
            tgt = active[-1]
            self._send_cancel(self.order, sysid=tgt["order_sys_id"],
                              ref=tgt["order_ref"], front=tgt["front_id"],
                              sess=tgt["session_id"])

    def _do_query_instruments(self):
        # 按品种前缀查合约。order 里传 product（如 "IC"）/exchange（如 "CFFEX"）。
        f = T.CThostFtdcQryInstrumentField()
        prod = str(self.order.get("product", "")).strip()
        exch = str(self.order.get("exchange_id", "")).strip()
        if exch:
            f.ExchangeID = exch
        if prod:
            f.InstrumentID = prod  # CTP 支持按合约代码模糊匹配；下面再用前缀过滤
        _log(f"query instruments product={prod} exchange={exch}")
        self.state["instruments"] = []
        self.api.ReqQryInstrument(f, self._nrid())

    def OnRspQryInstrument(self, p, info, n, last):
        # 持仓均价换算路径：只取合约乘数，不写入 instruments 列表
        if self.action not in ("instruments", "main_contract"):
            if p is not None:
                iid = str(getattr(p, "InstrumentID", "") or "")
                if iid:
                    try:
                        self._pos_mult_map[iid] = int(float(getattr(p, "VolumeMultiple", 0) or 0))
                    except Exception:  # noqa: BLE001
                        pass
            if last:
                time.sleep(0.4)  # 查询流控：串行查下一合约
                self._query_next_pos_mult()
            return
        if p is not None:
            try:
                prod = str(self.order.get("product", "")).strip().upper()
                iid = str(getattr(p, "InstrumentID", "") or "")
                base = iid
                # 只保留字母前缀匹配 product 的合约（如 IC 开头）
                import re as _re
                m = _re.match(r"^([A-Za-z]+)([0-9]+)$", iid)
                ok = True
                if prod:
                    ok = bool(m) and m.group(1).upper() == prod
                if ok and iid:
                    self.state["instruments"].append({
                        "instrument_id": iid,
                        "exchange_id": str(getattr(p, "ExchangeID", "") or ""),
                        "product_id": str(getattr(p, "ProductID", "") or ""),
                        "name": str(getattr(p, "InstrumentName", "") or ""),
                        "volume_multiple": int(float(getattr(p, "VolumeMultiple", 0) or 0)),
                        "price_tick": _num(p, "PriceTick"),
                        "expire_date": str(getattr(p, "ExpireDate", "") or ""),
                        "open_date": str(getattr(p, "OpenDate", "") or ""),
                        "is_trading": int(getattr(p, "IsTrading", 0) or 0),
                    })
            except Exception as e:  # noqa: BLE001
                _log(f"instrument parse fail: {type(e).__name__}: {e}")
        if last:
            self._instr_done = True
            _log(f"instruments done: {len(self.state['instruments'])}")
            if self.action == "main_contract":
                try:
                    self._do_query_market_data()
                except Exception as e:  # noqa: BLE001
                    _log(f"market data query submit error: {type(e).__name__}: {e}")
                    self._md_done = True

    def _do_depth_one(self):
        iid = str(self.order.get("instrument_id", "") or "").strip()
        if not iid:
            self.state["depth_done"] = True
            return
        f = T.CThostFtdcQryDepthMarketDataField()
        f.InstrumentID = iid
        rc = self.api.ReqQryDepthMarketData(f, self._nrid())
        _log(f"depth query {iid} ret={rc}")

    def _do_query_market_data(self):
        # 行情深度查询 CThostFtdcQryDepthMarketDataField 仅支持按 InstrumentID 精确查
        # （空合约号会拉全市场数千合约，回调洪流导致超时）。因此对可交易月份逐个查，
        # 串行 + 查询流控间隔（CTP 查询类接口约 1 次/秒）。
        tradable = [x["instrument_id"] for x in self.state.get("instruments", [])
                    if x.get("is_trading")]
        self.state["_md_queue"] = list(tradable)
        self.state["market"] = {}
        _log(f"query depth market data one-by-one for {len(tradable)} instruments")
        self._query_next_market()

    def _query_next_market(self):
        queue = self.state.get("_md_queue", [])
        if not queue:
            self._md_done = True
            _log(f"market data done: {len(self.state.get('market', {}))} quotes")
            return
        iid = queue.pop(0)
        f = T.CThostFtdcQryDepthMarketDataField()
        f.InstrumentID = iid
        rc = self.api.ReqQryDepthMarketData(f, self._nrid())
        if rc != 0:
            _log(f"ReqQryDepthMarketData({iid}) ret={rc}")
            # 流控/失败：跳过该合约，继续下一个
            self._query_next_market()

    def OnRspQryDepthMarketData(self, p, info, n, last):
        if p is not None:
            try:
                iid = str(getattr(p, "InstrumentID", "") or "")
                if iid:
                    self.state["market"][iid] = {
                        "last_price": _num(p, "LastPrice"),
                        "open_interest": int(float(getattr(p, "OpenInterest", 0) or 0)),
                        "volume": int(float(getattr(p, "Volume", 0) or 0)),
                        "upper_limit": _num(p, "UpperLimitPrice"),
                        "lower_limit": _num(p, "LowerLimitPrice"),
                        "bid_price1": _num(p, "BidPrice1"),
                        "ask_price1": _num(p, "AskPrice1"),
                    }
                    if (self.action == "depth" and iid
                            and iid == str(self.order.get("instrument_id", "")).strip()):
                        self.state["depth"] = dict(self.state["market"].get(iid, {}))
                        self.state["depth"]["instrument_id"] = iid
                        self.state["depth_done"] = True
                        _log(f"depth {iid}: {self.state['depth']}")
            except Exception as e:  # noqa: BLE001
                _log(f"depth market parse fail: {type(e).__name__}: {e}")
        if last:
            # 查询流控：串行查下一合约前稍作等待（worker 独立进程，短暂阻塞回调线程可接受）
            time.sleep(0.8)
            self._query_next_market()

    def _rsp_info(self, info):
        if info is None:
            return 0, ""
        return getattr(info, "ErrorID", 0) or 0, getattr(info, "ErrorMsg", "") or ""

    def OnRspOrderInsert(self, p, info, n, b):
        err, msg = self._rsp_info(info)
        _log(f"OnRspOrderInsert [{err}] {msg}")
        if err:
            self.state["action_done"] = True
            r = self.state.setdefault("action_result", {})
            r.update({"ok": False, "error": f"order rejected [{err}] {msg}",
                      "error_id": err})

    def OnErrRtnOrderInsert(self, p, info):
        err, msg = self._rsp_info(info)
        _log(f"OnErrRtnOrderInsert [{err}] {msg}")
        self.state["action_done"] = True
        r = self.state.setdefault("action_result", {})
        r.update({"ok": False, "error": f"exchange reject [{err}] {msg}",
                  "error_id": err})

    def OnRtnOrder(self, p):
        if p is None:
            return
        try:
            status = str(getattr(p, "OrderStatus", ""))
            ref = str(getattr(p, "OrderRef", ""))
            ev = {
                "order_ref": ref,
                "order_sys_id": str(getattr(p, "OrderSysID", "") or "").strip(),
                "status": status,
                "status_msg": str(getattr(p, "StatusMsg", "") or ""),
                "instrument_id": str(getattr(p, "InstrumentID", "") or ""),
                "exchange_id": str(getattr(p, "ExchangeID", "") or ""),
                "front_id": int(getattr(p, "FrontID", 0) or 0),
                "session_id": int(getattr(p, "SessionID", 0) or 0),
                "volume_total": int(float(getattr(p, "VolumeTotal", 0) or 0)),
                "volume_traded": int(float(getattr(p, "VolumeTraded", 0) or 0)),
                "limit_price": _num(p, "LimitPrice"),
            }
            self.state["order_events"].append(ev)
            _log(f"OnRtnOrder ref={ref} status={status} traded={ev['volume_traded']}/{ev['volume_total']} sysid={ev['order_sys_id']}")
            r = self.state.setdefault("action_result", {})
            if ev.get("status_msg"):
                r["last_status_msg"] = ev["status_msg"]
            if self.action == "cancel":
                if status == "5":  # 已撤
                    r.update({"ok": True, "status": "canceled", **{k: ev[k] for k in ("order_ref", "order_sys_id", "instrument_id", "exchange_id")}})
                    self.state["action_done"] = True
                elif status in ("0", "1"):
                    r.update({"ok": True, "status": "still_active", "order_status": status})
            else:
                r.update({"order_sys_id": ev["order_sys_id"] or r.get("order_sys_id", ""),
                          "front_id": ev["front_id"], "session_id": ev["session_id"],
                          "exchange_id": ev["exchange_id"] or r.get("exchange_id", ""),
                          "order_status": status, "volume_traded": ev["volume_traded"]})
                if status == "0":  # 全部成交
                    r.update({"ok": True, "status": "filled"})
                    self.state["action_done"] = True
                elif status == "5":  # 已撤/被拒
                    msg = ev.get("status_msg", "") or ""
                    if "拒" in msg:
                        r.update({"ok": False, "status": "rejected",
                                  "error": msg or "order rejected by exchange"})
                    else:
                        r.update({"ok": True, "status": "canceled"})
                    self.state["action_done"] = True
                elif status in ("3", "1"):  # 未成交/部分成交（挂单成功）
                    r.update({"ok": True, "status": "accepted" if status == "3" else "partial"})
        except Exception as e:  # noqa: BLE001
            _log(f"OnRtnOrder parse fail: {type(e).__name__}: {e}")

    def OnRtnTrade(self, p):
        if p is None:
            return
        try:
            tr = {
                "order_ref": str(getattr(p, "OrderRef", "")),
                "order_sys_id": str(getattr(p, "OrderSysID", "") or "").strip(),
                "trade_id": str(getattr(p, "TradeID", "") or ""),
                "instrument_id": str(getattr(p, "InstrumentID", "") or ""),
                "direction": str(getattr(p, "Direction", "")),
                "offset_flag": str(getattr(p, "OffsetFlag", "")),
                "price": _num(p, "Price"),
                "volume": int(float(getattr(p, "Volume", 0) or 0)),
            }
            self.state["trade_events"].append(tr)
            _log(f"OnRtnTrade ref={tr['order_ref']} px={tr['price']} vol={tr['volume']}")
        except Exception as e:  # noqa: BLE001
            _log(f"OnRtnTrade parse fail: {e}")

    def OnRspOrderAction(self, p, info, n, b):
        err, msg = self._rsp_info(info)
        _log(f"OnRspOrderAction [{err}] {msg}")
        if err:
            self.state["action_done"] = True
            r = self.state.setdefault("action_result", {})
            r.update({"ok": False, "error": f"cancel rejected [{err}] {msg}",
                      "error_id": err})

    def OnErrRtnOrderAction(self, p, info):
        err, msg = self._rsp_info(info)
        _log(f"OnErrRtnOrderAction [{err}] {msg}")
        self.state["action_done"] = True
        r = self.state.setdefault("action_result", {})
        r.update({"ok": False, "error": f"cancel exchange reject [{err}] {msg}",
                  "error_id": err})

    def OnRspError(self, info, n, b):
        err = getattr(info, "ErrorID", None)
        msg = getattr(info, "ErrorMsg", None)
        _log(f"OnRspError [{err}] {msg}")
        if not self.state.get("logined"):
            self.state["phase"] = "error"
            self.state["error"] = f"rsp error [{err}] {msg}"


def run(action: str = "query", order: dict | None = None, timeout: float = 30.0,
        profile: str | None = None) -> dict:
    global _API, _SPI, _STATE
    if not Path(_CTP_SWG_PATH).exists():
        return {"ok": False, "status": "unavailable", "error": f"CTP SWIG not found: {_CTP_SWG_PATH}"}
    if T is None:
        return {"ok": False, "status": "unavailable", "error": f"import thosttraderapi fail: {_IMP_ERR}"}

    profile = (profile or os.environ.get("CTP_PROFILE", "simnow")).strip().lower()
    if profile not in _PROFILES:
        return {"ok": False, "status": "bad_profile", "profile": profile,
                "error": f"未知 CTP profile={profile}，可选：{', '.join(_PROFILES)}"}
    cfg = _load_config(profile)
    if cfg.get("_missing"):
        return {"ok": False, "status": "not_configured", "profile": profile, "label": cfg.get("label", profile),
                "error": f"中信/CTP profile={profile} 缺少配置：{', '.join(cfg['_missing'])}"
                         f"（交易前置 td_server / broker_id / app_id / 账号 / 密码 / 认证码需向券商索取后填入 secrets/环境变量）"}
    _STATE = state = {"phase": "init", "error": "", "investor": "", "trading_day": "",
                      "account": None, "positions": [], "logined": False,
                      "settled": False, "acct_done": False, "pos_done": False,
                      "front_id": 0, "session_id": 0,
                      "order_events": [], "trade_events": [], "instruments": [], "orders": [],
                      "trades": [], "trades_done": False, "trades_error": "",
                      "_trades_q_done": False, "_orders_q_done": False,
                      "market": {},
                      "action_done": False, "action_result": None, "order_ref": "",
                      "profile": profile, "label": cfg.get("label", profile)}

    api = T.CThostFtdcTraderApi.CreateFtdcTraderApi("")
    spi = TraderSpi(api, cfg, state, action=action, order=order)
    _API, _SPI = api, spi
    api.RegisterSpi(spi)
    api.SubscribePrivateTopic(2)
    api.SubscribePublicTopic(2)
    api.RegisterFront(cfg["td_server"])
    api.Init()

    deadline = time.time() + timeout
    action_wait = 6.0  # 报单/撤单后额外等待回报的宽限
    action_deadline = None
    while time.time() < deadline:
        if state["phase"] == "error":
            break
        if action in ("order", "cancel"):
            if state["settled"] and action_deadline is None:
                action_deadline = time.time() + action_wait
            if state["action_done"]:
                break
            if action_deadline is not None and time.time() > action_deadline:
                _log(f"action wait timeout ({action_wait}s) -> return current result")
                break
        elif action == "trades":
            if state.get("trades_done") or (state.get("_trades_q_done") and state.get("_orders_q_done")):
                break
        elif action == "depth":
            if state.get("depth_done"):
                break
        elif action == "instruments":
            if spi._instr_done:
                break
        elif action == "main_contract":
            if spi._md_done:
                break
        else:
            if (state["logined"] and not state["pos_done"] and spi._detail_deadline
                    and time.time() > spi._detail_deadline):
                # 明细回调缺失（如部分柜台/绑定不支持）时，按聚合字段兜底收口
                spi._merge_position_detail()
            if state["logined"] and state["pos_done"]:
                break
        time.sleep(0.1)

    try:
        api.Release()
    except Exception:  # noqa: BLE001
        pass

    if state["phase"] == "error":
        return {"ok": False, "status": "error", "profile": profile, "error": state["error"] or "unknown"}
    if not state["logined"]:
        return {"ok": False, "status": "timeout", "profile": profile,
                "error": f"login timeout (phase={state['phase']})"}
    out = {
        "ok": True, "status": "logined",
        "profile": profile, "label": cfg.get("label", profile),
        "investor": state["investor"], "trading_day": state["trading_day"],
        "settled": state["settled"], "account": state["account"],
        "positions": state["positions"],
        "front_id": state["front_id"], "session_id": state["session_id"],
    }
    if action == "main_contract":
        insts = state.get("instruments", [])
        market = state.get("market", {})
        for x in insts:
            q = market.get(x["instrument_id"]) or {}
            x.update({"open_interest": q.get("open_interest", 0),
                      "volume": q.get("volume", 0),
                      "last_price": q.get("last_price"),
                      "upper_limit": q.get("upper_limit"),
                      "lower_limit": q.get("lower_limit")})
        tradable = [x for x in insts if x.get("is_trading")] or insts
        with_oi = [x for x in tradable if x.get("open_interest")]
        # 主力 = 持仓量最大；行情缺失时回退近月
        if with_oi:
            main = max(with_oi, key=lambda x: x["open_interest"])
        else:
            main = sorted(tradable, key=lambda x: (x.get("expire_date") or "99999999"))[0] if tradable else None
        front = sorted(tradable, key=lambda x: (x.get("expire_date") or "99999999"))
        out["instruments"] = insts
        out["tradable_count"] = len(tradable)
        out["main_contract"] = main
        out["front_contract"] = front[0] if front else None
        out["main_by"] = "open_interest" if with_oi else "nearest_expiry_fallback"
        out["status"] = "main_contract"
        out["ok"] = bool(main)
        return out
    if action == "trades":
        out["trades"] = state.get("trades", [])
        out["orders"] = state.get("orders", [])
        out["trades_error"] = state.get("trades_error", "")
        out["status"] = "trades"
        out["ok"] = True
        return out
    if action == "depth":
        out["depth"] = state.get("depth")
        out["status"] = "depth"
        out["ok"] = bool(state.get("depth"))
        return out
    if action == "instruments":
        insts = state.get("instruments", [])
        tradable = [x for x in insts if x.get("is_trading")] or insts
        # 主力合约：可交易中按 expire_date 最近（次近月通常即主力的简单启发；
        # 真实主力按持仓量，需行情/持仓查询——这里给出可交易月份列表供上层选择）。
        out["instruments"] = insts
        out["tradable_count"] = len(tradable)
        # 选“最近到期且可交易”的月份作为默认主力候选
        future = sorted(tradable, key=lambda x: (x.get("expire_date") or "99999999"))
        out["front_contract"] = future[0] if future else None
        out["status"] = "instruments"
        out["ok"] = bool(insts)
        return out
    if action in ("order", "cancel"):
        r = state.get("action_result") or {}
        out["action"] = action
        out["action_result"] = r
        out["order_events"] = state["order_events"]
        out["trade_events"] = state["trade_events"]
        out["orders"] = state.get("orders", [])
        # 报单/撤单以柜台回报为准；挂单成功（accepted/partial/filled/canceled）即 ok
        out["ok"] = bool(r.get("ok"))
        out["status"] = r.get("status", "no_report")
        if not r.get("ok") and not r.get("error"):
            out["ok"] = False
    return out


if __name__ == "__main__":
    _action = os.environ.get("CTP_ACTION", "query").strip().lower()
    _order = {}
    _oj = os.environ.get("CTP_ORDER_JSON", "").strip()
    if _oj:
        try:
            _order = json.loads(_oj)
        except Exception as e:  # noqa: BLE001
            print("RESULT_JSON=" + json.dumps(
                {"ok": False, "status": "bad_order_json", "error": str(e)},
                ensure_ascii=False), flush=True)
            sys.exit(2)
    try:
        result = run(action=_action, order=_order)
    except Exception as e:  # noqa: BLE001  # 兜底（原生崩溃不走这里）
        result = {"ok": False, "status": "crash_py", "error": f"{type(e).__name__}: {e}"}
    print("RESULT_JSON=" + json.dumps(result, ensure_ascii=False), flush=True)
    sys.exit(0 if result.get("ok") else 2)
