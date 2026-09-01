#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SimNow trader -- high-level CTP wrapper (SWIG-based).

仅在 winclaw 上运行。从 settings.yaml + .streamlit/secrets.toml 读取配置。
"""

import sys
import threading
import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 仅在 winclaw 上导入 CTP connector（SWIG）
_CTP_SWG_PATH = r"C:\tmp\ctp_api\ctp_swig_build-6.7.11.1\ctp_api"
_WINCLOW = Path(_CTP_SWG_PATH).exists()

if _WINCLOW:
    sys.path.insert(0, _CTP_SWG_PATH)
    from thosttraderapi import CThostFtdcTraderApi, CThostFtdcTraderSpi
    from thostmduserapi import CThostFtdcMdApi, CThostFtdcMdSpi
    from simnow_client.ctp_connector import CtpMdConnector, CtpTdConnector, CtpConfig, ConnectionStatus
else:
    CtpMdConnector = CtpTdConnector = CtpConfig = ConnectionStatus = None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _load_config():
    """从 settings.yaml + secrets.toml 读取 SimNow 配置（纯 stdlib）。"""
    root = Path(__file__).resolve().parent.parent
    yaml_path = root / "config" / "settings.yaml"
    secrets_path = root / ".streamlit" / "secrets.toml"

    sn = {}
    if yaml_path.exists():
        in_simnow = False
        for line in open(yaml_path, encoding="utf-8"):
            stripped = line.strip()
            if stripped.startswith("simnow:"):
                in_simnow = True
                continue
            if in_simnow:
                if stripped and not stripped.startswith("#") and ":" in stripped:
                    key, _, val = stripped.partition(":")
                    sn[key.strip()] = val.strip().strip('"').strip("'")
                elif stripped and not stripped.startswith("#") and not any(
                    c in stripped for c in ":-'\""):
                    if stripped[0].isalpha():
                        break

    user = password = ""
    if secrets_path.exists():
        try:
            import tomllib
            secrets = tomllib.load(open(secrets_path, "rb"))
            user = secrets.get("SIMNOW_SIM_USER", "")
            password = secrets.get("SIMNOW_SIM_PASSWORD", "")
        except Exception:
            pass

    return {
        "flag": sn.get("flag", "sim"),
        "md_server": sn.get("md_server", "tcp://182.254.243.31:30011"),
        "td_server": sn.get("td_server", "tcp://182.254.243.31:30001"),
        "broker_id": sn.get("broker_id", "9999"),
        "auth_code": sn.get("auth_code", "0000000000000000"),
        "app_id": sn.get("app_id", "simnow_client_test"),
        "user": user,
        "password": password,
    }


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class SimNowStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    LOGINED = "logined"
    ERROR = "error"


@dataclass
class OrderResult:
    order_id: str = ""
    status: str = "unknown"
    message: str = ""
    timestamp: str = ""


@dataclass
class Position:
    symbol: str
    direction: str
    volume: int
    avg_price: float
    float_pnl: float = 0.0


@dataclass
class AccountInfo:
    account_id: str = ""
    balance: float = 0.0
    available: float = 0.0
    margin: float = 0.0


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------

class SimNowTrader:
    """
    SimNow / CTP 交易通道。

    用法：
        trader = SimNowTrader()
        ok = trader.connect()
        trader.place_order("IF2609", "long", 1, 4000.0)
        trader.disconnect()
    """

    def __init__(
        self,
        md_server: Optional[str] = None,
        td_server: Optional[str] = None,
        broker_id: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        auth_code: str = "0000000000000000",
        app_id: str = "simnow_client_test",
    ):
        cfg = _load_config()

        self._md_server = md_server or cfg.get("md_server", "tcp://182.254.243.31:30011")
        self._td_server = td_server or cfg.get("td_server", "tcp://182.254.243.31:30001")
        self._broker_id = broker_id or cfg.get("broker_id", "9999")
        self._user = user or cfg.get("user", "")
        self._password = password or cfg.get("password", "")
        self._auth_code = auth_code
        self._app_id = app_id

        self._md_conn: Optional[object] = None
        self._td_conn: Optional[object] = None
        self._status = SimNowStatus.DISCONNECTED
        self._login_error: str = ""
        self._order_ref_lock = threading.Lock()
        self._next_order_ref = 1
        self._positions: dict[str, Position] = {}
        self._account: Optional[AccountInfo] = None

    # -- Lifecycle --

    def connect(self, timeout: float = 15.0) -> bool:
        """连接 SimNow 并登录（阻塞直到超时）。"""
        if not _WINCLOW:
            self._login_error = (
                "CTP SWIG not available. "
                "This module must run on winclaw (100.99.204.126)."
            )
            self._status = SimNowStatus.ERROR
            return False

        ctp_cfg = CtpConfig(
            md_server=self._md_server,
            td_server=self._td_server,
            broker_id=self._broker_id,
            user_id=self._user,
            password=self._password,
            auth_code=self._auth_code,
            app_id=self._app_id,
        )

        self._status = SimNowStatus.CONNECTING

        self._td_conn = CtpTdConnector(ctp_cfg)

        deadline = time.time() + timeout
        last_err = ""
        while time.time() < deadline:
            st = self._td_conn.status
            if st == ConnectionStatus.LOGINED:
                self._status = SimNowStatus.LOGINED
                logger.info(f"SimNow login OK: investor={self._td_conn.investor_id}")
                return True
            if st == ConnectionStatus.ERROR:
                last_err = self._td_conn.last_error
            time.sleep(0.5)

        self._login_error = last_err or "login timeout"
        self._status = SimNowStatus.ERROR
        return False

    def disconnect(self):
        if self._td_conn:
            try:
                self._td_conn._api.Release()
            except Exception:
                pass
        self._status = SimNowStatus.DISCONNECTED

    def is_connected(self) -> bool:
        return self._status == SimNowStatus.LOGINED

    def last_error(self) -> str:
        return self._login_error

    # -- Trading --

    def place_order(
        self,
        symbol: str,
        direction: str,
        volume: int,
        price: float = 0.0,
        order_type: str = "limit",
    ) -> OrderResult:
        """下单。direction: 'long'/'short'，price_type: 'limit'/'market'。"""
        if not self.is_connected():
            return OrderResult(status="rejected", message="not connected")

        symbol = symbol.upper().strip()
        try:
            ref = self._td_conn.place_order(
                symbol=symbol,
                direction=direction,
                volume=volume,
                price=price,
                price_type=order_type,
            )
            return OrderResult(
                order_id=f"ctp_{ref}",
                status="submitted",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            )
        except Exception as e:
            return OrderResult(status="rejected", message=str(e))

    def cancel_order(self, order_id: str, exchange: str = "", order_sys_id: str = "") -> OrderResult:
        """撤单。"""
        if not self.is_connected():
            return OrderResult(status="rejected", message="not connected")
        try:
            ok = self._td_conn.cancel_order(
                exchange or order_sys_id.split("-")[0] if order_sys_id else "",
                order_sys_id or order_id,
            )
            return OrderResult(
                order_id=order_id,
                status="cancelling" if ok else "reject",
            )
        except Exception as e:
            return OrderResult(status="rejected", message=str(e))

    # -- Query --

    def query_positions(self) -> list[Position]:
        return list(self._positions.values())

    def query_account(self) -> Optional[AccountInfo]:
        return self._account

    # -- Properties --

    @property
    def status(self) -> SimNowStatus:
        return self._status

    @property
    def investor_id(self) -> str:
        if self._td_conn:
            return self._td_conn.investor_id
        return ""

    @property
    def trading_day(self) -> str:
        if self._td_conn:
            return self._td_conn.trading_day
        return ""
