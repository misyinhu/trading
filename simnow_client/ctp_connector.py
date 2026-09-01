#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CTP connector -- wraps CTP SWIG API (thosttraderapi / thostmduserapi).
Winclaw 专用：C:\tmp\ctp_api\ctp_swig_build-6.7.11.1\ctp_api

设计原则：模块加载时零 CTP 依赖，仅在 CtpTdConnector/CtpMdConnector
实例化时做运行时导入。这样 Flask（Python 3.12）可以安全导入本模块，
只有实际使用时才触发 cp313 .pyd 加载。

SWIG 关键规则：
  1. field 构造器不接受关键字参数，必须先 () 再逐字段赋值
  2. CThostFtdcTraderSpi.__init__() 必须先 super().__init__() 再存 self.api
  3. CreateFtdcTraderApi/MdApi 第一个参数传空字符串（内存模式）
  4. 所有 THOST_FTDC_* 常量直接从 thosttraderapi 导入
"""

import sys
import threading
import time
import os
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Optional

_CTP_SWG_PATH = r"C:\tmp\ctp_api\ctp_swig_build-6.7.11.1\ctp_api"


def _check_ctp() -> bool:
    """运行时验证 CTP SWIG .pyd 是否可用（需 cp313 Python）。"""
    if not os.path.exists(_CTP_SWG_PATH):
        return False
    try:
        sys.path.insert(0, _CTP_SWG_PATH)
        from thosttraderapi import CThostFtdcTraderApi
        api = CThostFtdcTraderApi.CreateFtdcTraderApi("")
        api.Release()
        return True
    except Exception:
        return False


# 模块级标志：首次检查结果缓存，import 时不触发任何 CTP 加载
_HAS_CTP: Optional[bool] = None


class ConnectionStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTH_OK = "auth_ok"
    LOGINED = "logined"
    ERROR = "error"


@dataclass
class CtpConfig:
    md_server: str
    td_server: str
    broker_id: str
    user_id: str
    password: str
    auth_code: str = "0000000000000000"
    app_id: str = "simnow_client_test"
    product_info: str = "simnow_client"


# ---------------------------------------------------------------------------
# 懒加载辅助：在 CtpTdConnector/CtpMdConnector 实例化时调用，返回 SWIG 模块
# ---------------------------------------------------------------------------

def _require_ctp():
    """确保 CTP SWIG 可用，否则抛 RuntimeError。首次调用触发检查。"""
    global _HAS_CTP
    if _HAS_CTP is None:
        _HAS_CTP = _check_ctp()
    if not _HAS_CTP:
        raise RuntimeError(
            "CTP SWIG not available. "
            "CTP .pyd requires Python 3.13 on winclaw. "
            "Flask runs on Python 3.12. "
            "Use Python 3.13 interpreter to instantiate CtpTdConnector."
        )
    return True


# ---------------------------------------------------------------------------
# MdApi
# ---------------------------------------------------------------------------

class CtpMdConnector:
    """行情通道。subscribe() 订阅合约，add_tick_handler() 注册回调。"""

    def __init__(self, config: CtpConfig):
        _require_ctp()
        sys.path.insert(0, _CTP_SWG_PATH)
        from thostmduserapi import (
            CThostFtdcMdApi, CThostFtdcMdSpi,
            CThostFtdcReqUserLoginField as MdLoginField,
        )

        self.cfg = config
        self._status = ConnectionStatus.DISCONNECTED
        self._tick_handlers: list[Callable] = []
        self._instruments: set[str] = set()
        self._last_error = ""
        self._investor_id = ""
        self._trading_day = ""

        self._MdSpi_cls = CThostFtdcMdSpi
        self._MdLoginField_cls = MdLoginField

        self._api = CThostFtdcMdApi.CreateFtdcMdApi("")
        self._spi = _MdSpi(self, config)
        self._api.RegisterSpi(self._spi)
        self._api.Init()
        self._status = ConnectionStatus.CONNECTING

    def subscribe(self, symbols: list[str]):
        new = [s for s in symbols if s not in self._instruments]
        if new:
            self._instruments.update(new)
            if self._status == ConnectionStatus.LOGINED:
                self._api.SubscribeMarketData(new)

    def add_tick_handler(self, handler: Callable):
        self._tick_handlers.append(handler)

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def investor_id(self) -> str:
        return self._investor_id

    @property
    def trading_day(self) -> str:
        return self._trading_day


class _MdSpi(CThostFtdcMdSpi):
    """行情 SPI，继承 SWIG 基类。"""

    def __init__(self, conn: "CtpMdConnector", cfg: CtpConfig):
        super().__init__()
        self.conn = conn
        self.cfg = cfg

    def OnFrontConnected(self):
        req = self.conn._MdLoginField_cls()
        req.BrokerID = self.cfg.broker_id
        req.UserID = self.cfg.user_id
        req.Password = self.cfg.password
        self.conn._api.ReqUserLogin(req, 1)

    def OnRspUserLogin(self, pUserLogin, pRspInfo, nRequestID, bIsLast):
        if pRspInfo and pRspInfo.ErrorID != 0:
            self.conn._last_error = f"Md login failed: [{pRspInfo.ErrorID}] {pRspInfo.ErrorMsg}"
            self.conn._status = ConnectionStatus.ERROR
            return
        self.conn._investor_id = pUserLogin.InvestorID
        self.conn._trading_day = pUserLogin.TradingDay
        self.conn._status = ConnectionStatus.LOGINED
        if self.conn._instruments:
            self.conn._api.SubscribeMarketData(list(self.conn._instruments))

    def OnFrontDisConnected(self, reason: int):
        self.conn._last_error = f"Md disconnected: {reason}"
        self.conn._status = ConnectionStatus.DISCONNECTED

    def OnRtnDepthMarketData(self, pDepthMarketData):
        for h in self.conn._tick_handlers:
            try:
                h(pDepthMarketData)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# TdApi
# ---------------------------------------------------------------------------

class CtpTdConnector:
    """交易通道。place_order() 下单，cancel_order() 撤单。"""

    def __init__(self, config: CtpConfig):
        _require_ctp()
        sys.path.insert(0, _CTP_SWG_PATH)
        from thosttraderapi import (
            CThostFtdcTraderApi, CThostFtdcTraderSpi,
            CThostFtdcReqAuthenticateField, CThostFtdcReqUserLoginField,
            CThostFtdcReqSettlementInfoConfirmField,
            CThostFtdcInputOrderField, CThostFtdcInputOrderActionField,
            THOST_FTDC_D_Buy, THOST_FTDC_D_Sell,
            THOST_FTDC_OPT_LimitPrice, THOST_FTDC_OPT_AnyPrice,
            THOST_FTDC_TC_GFD, THOST_FTDC_VC_AV,
            THOST_FTDC_TP_Not, THOST_FTDC_FC_NotForceClose,
        )
        self._const = dict(
            D_Buy=THOST_FTDC_D_Buy, D_Sell=THOST_FTDC_D_Sell,
            OPT_LimitPrice=THOST_FTDC_OPT_LimitPrice,
            OPT_AnyPrice=THOST_FTDC_OPT_AnyPrice,
            TC_GFD=THOST_FTDC_TC_GFD, VC_AV=THOST_FTDC_VC_AV,
            TP_Not=THOST_FTDC_TP_Not, FC_NotForceClose=THOST_FTDC_FC_NotForceClose,
        )
        self._field = dict(
            ReqAuth=CThostFtdcReqAuthenticateField,
            ReqLogin=CThostFtdcReqUserLoginField,
            SettlementConfirm=CThostFtdcReqSettlementInfoConfirmField,
            InputOrder=CThostFtdcInputOrderField,
            InputOrderAction=CThostFtdcInputOrderActionField,
        )

        self.cfg = config
        self._status = ConnectionStatus.DISCONNECTED
        self._investor_id = ""
        self._trading_day = ""
        self._account_id = ""
        self._last_error = ""
        self._orders: dict[str, dict] = {}

        self._api = CThostFtdcTraderApi.CreateFtdcTraderApi("")
        self._spi = _TdSpi(self, config)
        self._api.RegisterSpi(self._spi)
        self._api.SubscribePrivateTopic(2)
        self._api.SubscribePublicTopic(2)
        self._api.RegisterFront(self.cfg.td_server)
        self._api.Init()
        self._status = ConnectionStatus.CONNECTING

    def place_order(self, symbol: str, direction: str, volume: int,
                     price: float = 0.0, price_type: str = "limit") -> str:
        req = self._field["InputOrder"]()
        req.InvestorID = self._investor_id
        req.BrokerID = self.cfg.broker_id
        req.ExchangeID = self._symbol_exchange(symbol)
        req.InstrumentID = symbol
        req.Direction = self._const["D_Buy"] if direction == "long" else self._const["D_Sell"]
        req.VolumeTotalOriginal = volume
        req.OrderPriceType = (self._const["OPT_LimitPrice"]
                              if price_type == "limit" else self._const["OPT_AnyPrice"])
        req.LimitPrice = price
        req.TimeCondition = self._const["TC_GFD"]
        req.VolumeCondition = self._const["VC_AV"]
        req.ContingentCondition = self._const["TP_Not"]
        req.ForceCloseReason = self._const["FC_NotForceClose"]
        ref = str(int(time.time()) % 100000)
        req.OrderRef = ref
        self._api.ReqOrderInsert(req, int(time.time()) % 100000)
        return ref

    def cancel_order(self, exchange: str, order_sys_id: str) -> bool:
        req = self._field["InputOrderAction"]()
        req.ExchangeID = exchange
        req.OrderSysID = order_sys_id
        req.ActionFlag = "0"
        ret = self._api.ReqOrderAction(req, int(time.time()) % 100000)
        return ret == 0

    @staticmethod
    def _symbol_exchange(symbol: str) -> str:
        prefix = symbol[:2].upper()
        return {
            "IF": "CFFEX", "IH": "CFFEX", "IC": "CFFEX", "IM": "CFFEX",
            "RU": "SHFE", "AU": "SHFE", "AG": "SHFE", "CU": "SHFE",
            "AL": "SHFE", "ZN": "SHFE", "PB": "SHFE", "NI": "SHFE",
            "SN": "SHFE", "RB": "SHFE", "HC": "SHFE", "SS": "SHFE",
            "BU": "SHFE", "SA": "SHFE",
            "M": "DCE", "Y": "DCE", "P": "DCE", "A": "DCE",
            "B": "DCE", "C": "DCE", "CS": "DCE", "JD": "DCE",
            "L": "DCE", "PP": "DCE", "V": "DCE", "EB": "DCE",
            "EG": "DCE", "RR": "DCE",
            "CF": "CZCE", "SR": "CZCE", "TA": "CZCE", "MA": "CZCE",
            "RM": "CZCE", "OI": "CZCE", "CY": "CZCE", "AP": "CZCE",
            "CJ": "CZCE", "UR": "CZCE",
            "SC": "INE", "BC": "INE", "NR": "INE", "EC": "INE",
            "T": "CFFEX", "TF": "CFFEX", "TS": "CFFEX",
        }.get(prefix, "SSE")

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def investor_id(self) -> str:
        return self._investor_id

    @property
    def trading_day(self) -> str:
        return self._trading_day


class _TdSpi(CThostFtdcTraderSpi):
    """交易 SPI，继承 SWIG 基类。"""

    def __init__(self, conn: "CtpTdConnector", cfg: CtpConfig):
        super().__init__()
        self.conn = conn
        self.cfg = cfg

    def OnFrontConnected(self):
        req = self.conn._field["ReqAuth"]()
        req.BrokerID = self.cfg.broker_id
        req.UserID = self.cfg.user_id
        req.AppID = self.cfg.app_id
        req.AuthCode = self.cfg.auth_code
        self.conn._api.ReqAuthenticate(req, 1)

    def OnFrontDisConnected(self, reason: int):
        self.conn._last_error = f"Td disconnected: {reason}"
        self.conn._status = ConnectionStatus.DISCONNECTED

    def OnRspAuthenticate(self, p, info, n, b):
        if info and info.ErrorID != 0:
            self.conn._last_error = f"Auth failed: [{info.ErrorID}] {info.ErrorMsg}"
            self.conn._status = ConnectionStatus.ERROR
            return
        req = self.conn._field["ReqLogin"]()
        req.BrokerID = self.cfg.broker_id
        req.UserID = self.cfg.user_id
        req.Password = self.cfg.password
        self.conn._api.ReqUserLogin(req, 2)

    def OnRspUserLogin(self, p, info, n, b):
        if info and info.ErrorID != 0:
            self.conn._last_error = f"Login failed: [{info.ErrorID}] {info.ErrorMsg}"
            self.conn._status = ConnectionStatus.ERROR
            return
        self.conn._investor_id = p.InvestorID
        self.conn._trading_day = p.TradingDay
        self.conn._account_id = p.AccountID
        req = self.conn._field["SettlementConfirm"]()
        req.BrokerID = self.cfg.broker_id
        req.InvestorID = p.InvestorID
        self.conn._api.ReqSettlementInfoConfirm(req, 3)
        self.conn._status = ConnectionStatus.LOGINED

    def OnRspSettlementInfoConfirm(self, p, info, n, b):
        pass
