"""tick 统一 schema —— 规格 §3.2。

交易所原始时间戳原样保留（ActionDay + UpdateTime + UpdateMillisec），
夜盘 ActionDay 归属由交易所字段决定，本层不自行切日。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Any

CST = timezone(timedelta(hours=8))

# CTP DepthMarketData 字段 -> 统一字段
# 缺失字段（部分柜台/回放数据）一律按 0.0/0 补齐，不伪造时间。
_FLOAT_FIELDS = {
    "last_price": "LastPrice",
    "turnover": "Turnover",
    "open_interest": "OpenInterest",
    "bid1": "BidPrice1",
    "ask1": "AskPrice1",
    "upper_limit": "UpperLimitPrice",
    "lower_limit": "LowerLimitPrice",
    "average_price": "AveragePrice",
}
_INT_FIELDS = {
    "volume": "Volume",
    "bid_vol1": "BidVolume1",
    "ask_vol1": "AskVolume1",
}


def _f(v: Any) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    # CTP 无效值统一用 DBL_MAX（1.7976931348623157e+308）
    return 0.0 if x > 1e300 else x


def _i(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


@dataclass
class Tick:
    profile: str
    instrument_id: str
    exchange_id: str
    ts_exchange: str          # ActionDay + UpdateTime + Millisec，北京时间字符串
    ts_recv: str              # 本机接收时间 ISO8601 +08:00
    last_price: float
    volume: int               # 当日累计成交量（差分算每根量）
    turnover: float
    open_interest: float
    bid1: float
    ask1: float
    bid_vol1: int
    ask_vol1: int
    upper_limit: float
    lower_limit: float
    average_price: float

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def key(self) -> tuple[str, str]:
        return (self.profile, self.instrument_id)


def make_exchange_ts(action_day: str, update_time: str, millisec: int | str) -> str:
    """拼成 ActionDay HH:MM:SS.mmm；字段缺失时返回空串（调用方决定补齐策略）。"""
    action_day = (action_day or "").strip()
    update_time = (update_time or "").strip()
    if not action_day or not update_time:
        return ""
    try:
        ms = int(_i(millisec))
    except (TypeError, ValueError):
        ms = 0
    return f"{action_day} {update_time}.{ms:03d}"


def tick_from_ctp(data: Any, profile: str, exchange_id: str = "",
                  recv_dt: datetime | None = None,
                  last_snapshot: Tick | None = None) -> Tick:
    """把 CTP DepthMarketData（对象或 dict）映射为统一 Tick。

    只推变化字段时用 last_snapshot 补齐（规格 §3.2）。
    """
    def g(name: str):
        if isinstance(data, dict):
            return data.get(name)
        return getattr(data, name, None)

    iid = str(g("InstrumentID") or (last_snapshot.instrument_id if last_snapshot else "")).strip()
    exid = str(g("ExchangeID") or exchange_id or (last_snapshot.exchange_id if last_snapshot else "")).strip()
    ts = make_exchange_ts(str(g("ActionDay") or ""), str(g("UpdateTime") or ""), g("UpdateMillisec") or 0)
    if not ts and last_snapshot is not None:
        ts = last_snapshot.ts_exchange

    recv = recv_dt or datetime.now(CST)
    out = Tick(
        profile=profile,
        instrument_id=iid,
        exchange_id=exid,
        ts_exchange=ts,
        ts_recv=recv.isoformat(timespec="milliseconds"),
        last_price=_f(g("LastPrice")),
        volume=_i(g("Volume")),
        turnover=_f(g("Turnover")),
        open_interest=_f(g("OpenInterest")),
        bid1=_f(g("BidPrice1")),
        ask1=_f(g("AskPrice1")),
        bid_vol1=_i(g("BidVolume1")),
        ask_vol1=_i(g("AskVolume1")),
        upper_limit=_f(g("UpperLimitPrice")),
        lower_limit=_f(g("LowerLimitPrice")),
        average_price=_f(g("AveragePrice")),
    )
    # 变化字段补齐：0 值字段用最近快照（累计量/盘口/涨跌停经常被柜台省略）
    if last_snapshot is not None:
        for fld in ("turnover", "open_interest", "bid1", "ask1", "bid_vol1",
                    "ask_vol1", "upper_limit", "lower_limit", "average_price"):
            if getattr(out, fld) in (0, 0.0):
                setattr(out, fld, getattr(last_snapshot, fld))
    return out
