#!/usr/bin/env python3
"""简单规则匹配的自然语言交易指令解析"""

import re
from typing import Dict, Any

# 外汇品种列表（真正的外汇对，使用 CASH 类型，交易所 IDEALPRO）
FOREX_SYMBOLS = {
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "AUDUSD",
    "NZDUSD",
    "USDCAD",
    "EURJPY",
    "GBPJPY",
    "EURGBP",
    "EURAUD",
    "GBPAUD",
}

# 商品品种列表（贵金属等，使用 CMDTY 类型）
CMDTY_SYMBOLS = {
    "XAUUSD",  # 黄金 vs USD
    "XAGUSD",  # 白银 vs USD
}

TRADING_PATTERNS = [
    # ===== 定时平仓 SCHEDULED_CLOSE =====（时间修饰语优先，阻止被 "平仓" 误匹配）
    (r"^(\d{1,2})点(\d{1,2})平仓(\S+)?$", "SCHEDULED_CLOSE"),  # 9点30平仓GC
    (r"^(\d{1,2})点平仓(\S+)?$", "SCHEDULED_CLOSE"),          # 9点平仓GC
    (r"^(\d{1,2}):(\d{2})平仓(\S+)?$", "SCHEDULED_CLOSE"),   # 09:30平仓GC
    (r"^(\d+)分钟(?:后)?平仓(\S+)?$", "SCHEDULED_CLOSE"),      # 30分钟后平仓GC
    # ===== 平仓 CLOSE ===== (具体 pattern 在前，通用在后)
    (r"平掉(\S+?)(?:仓|位)$", "CLOSE"),
    (r"平仓(\d+)(?:手|股)(\S+)$", "CLOSE"),  # 平仓2手GC
    (r"平仓([一二三四五六七八九十]+)(?:手|股)(\S+)$", "CLOSE"),  # 平仓一手GC
    (r"平(\d+)(?:手|股)(\S+)$", "CLOSE"),  # 平2手GC
    (r"平([一二三四五六七八九十]+)(?:手|股)(\S+)$", "CLOSE"),  # 平一手GC
    (r"平仓(\d+)单元(\S+)$", "CLOSE"),
    (r"平仓(\d+)手(\S+)$", "CLOSE"),
    (r"平仓(\S+)(\d+)单元$", "CLOSE"),
    (r"平仓(\S+)(\d+)手$", "CLOSE"),
    (r"清仓$", "CLOSE"),
    (r"平仓(\S+)$", "CLOSE"),  # 平仓GC (全平)
    (r"平(\S+)$", "CLOSE"),
    # ===== 卖出 SELL =====
    (r"卖空(\d+)(?:手|股)(\S+)$", "SELL"),
    (r"做空(\d+)(?:手|股)(\S+)$", "SELL"),
    (r"卖出(\d+)(?:手|股)(\S+)$", "SELL"),
    (r"卖出(\S+)$", "SELL"),
    (r"做空(\S+)$", "SELL"),
    (r"卖(\d+)$", "SELL"),
    # ===== 买入 BUY ===== (具体在前，通用在后)
    (r"买入(\d+)(?:手|股)(\S+)$", "BUY"),  # 买入1手GC
    (r"买入([一二三四五六七八九十]+)(?:手|股)(\S+)$", "BUY"),  # 买入一手GC
    (r"做多(\d+)(?:手|股)(\S+)$", "BUY"),
    (r"做多([一二三四五六七八九十]+)(?:手|股)(\S+)$", "BUY"),
    (r"买(\d+)(?:手|股)(\S+)$", "BUY"),
    (r"买([一二三四五六七八九十]+)(?:手|股)(\S+)$", "BUY"),  # 买一手GC
    (r"买入(\d+)单元(\S+)$", "BUY"),
    (r"做多(\d+)单元(\S+)$", "BUY"),
    (r"买入(\S+)(\d+)单元$", "BUY"),
    (r"做多(\S+)(\d+)单元$", "BUY"),
    (r"买入(\S+)(\d+)手$", "BUY"),
    (r"做多(\S+)(\d+)手$", "BUY"),
    (r"买入(\d+)$", "BUY"),
    (r"买入(\S+)$", "BUY"),
    (r"做多(\S+)$", "BUY"),
    (r"购买(\d+)(?:手|股)(\S+)$", "BUY"),
    (r"购买(\S+)$", "BUY"),
]

QUERY_PATTERNS = [
    r"^查看持仓$",
    r"^查看账户$",
    r"^查看订单$",
    r"^查看成交$",
    r"^账户余额$",
    r"^当前持仓$",
]


def parse_trading_command(message: str) -> Dict[str, Any]:
    import datetime as _dt

    msg = message.strip()
    msg_lower = msg.lower()

    for pattern in QUERY_PATTERNS:
        if re.search(pattern, msg_lower):
            return {"action": "QUERY", "raw": msg}

    # ---- 定时平仓 SCHEDULED_CLOSE ----
    _SCHEDULED_PATTERNS = [
        (r"^(\d{1,2})点(\d{1,2})平仓(\S+)?$", "HM"),   # 9点30平仓GC
        (r"^(\d{1,2})点平仓(\S+)?$", "H"),            # 9点平仓GC
        (r"^(\d{1,2}):(\d{2})平仓(\S+)?$", "HM"),     # 09:30平仓GC
        (r"^(\d+)分钟(?:后)?平仓(\S+)?$", "DELTA"),    # 30分钟后平仓GC
    ]
    for _spat, _stype in _SCHEDULED_PATTERNS:
        _sm = re.match(_spat, msg_lower)
        if _sm:
            _sgroups = _sm.groups()
            _result = {"action": "SCHEDULED_CLOSE", "raw": msg}
            _now = _dt.datetime.now().replace(second=0, microsecond=0)
            _sym = None
            if _stype == "HM":
                _hour, _minute = int(_sgroups[0]), int(_sgroups[1])
                _sym = _sgroups[2]
                _result["schedule_time"] = _now.replace(hour=_hour, minute=_minute).isoformat()
            elif _stype == "H":
                _hour = int(_sgroups[0])
                _sym = _sgroups[1]
                _result["schedule_time"] = _now.replace(hour=_hour, minute=0).isoformat()
            elif _stype == "DELTA":
                _mins = int(_sgroups[0])
                _sym = _sgroups[1]
                _result["schedule_time"] = (_now + _dt.timedelta(minutes=_mins)).isoformat()
            # 清理 symbol
            if _sym:
                _sym = _sym.upper().strip()
                _sym = re.sub(r"(单元|手|股|仓|位)$", "", _sym).strip()
                # 过滤无意义单字
                _MEANINGLESS = {"仓", "位", "手", "股", "多", "空", "平", "买", "卖", "平"}
                if _sym and _sym not in _MEANINGLESS and len(_sym) > 1:
                    _result["symbol"] = _sym
            return _result
    # ---------------------------------

    for pattern, action in TRADING_PATTERNS:
        match = re.search(pattern, msg_lower)
        if match:
            result = {"action": action, "raw": msg}
            groups = match.groups()
            quantity = None
            symbol = None
            usd_amount = None

            if "美元" in pattern:
                for g in groups:
                    if g and g.isdigit():
                        usd_amount = int(g)
                    elif g and g.strip() and not g.strip().isdigit():
                        symbol = g.strip()
                if usd_amount:
                    result["usd_amount"] = usd_amount
            else:
                cn_num_map = {
                    "一": 1,
                    "二": 2,
                    "三": 3,
                    "四": 4,
                    "五": 5,
                    "六": 6,
                    "七": 7,
                    "八": 8,
                    "九": 9,
                    "十": 10,
                    "零": 0,
                    "百": 100,
                }
                for g in groups:
                    if g:
                        g_stripped = g.strip()
                        # 数字字符串 (Arabic)
                        if g_stripped.isdigit():
                            quantity = int(g_stripped)
                        # 中文数字字符串
                        elif any(cn in g_stripped for cn in cn_num_map):
                            # 取第一个匹配的中文数字 (只支持个位+十)
                            for cn, num in cn_num_map.items():
                                if cn in g_stripped:
                                    quantity = num
                                    break
                        # 普通字符串（不是数字）-> symbol
                        elif (
                            g_stripped
                            and not any(c.isdigit() for c in g_stripped)
                            and len(g_stripped) > 1
                        ):
                            symbol = g_stripped
                        elif g_stripped and not any(
                            cn in g_stripped for cn in cn_num_map
                        ):
                            # single char like "一" or "G" - only assign to symbol if it's clearly not a number
                            if g_stripped not in cn_num_map:
                                symbol = g_stripped
                if quantity is not None:
                    result["quantity"] = quantity

            if symbol:
                symbol = symbol.upper().strip()
                symbol = re.sub(r"(单元|手|股)$", "", symbol)
                symbol = symbol.strip()

                if "-SWAP" not in symbol and any(
                    k in symbol for k in ["DOGE", "ETH", "BTC"]
                ):
                    symbol = symbol + "-USDT-SWAP"
                    result["exchange"] = "OKX"
                    result["sec_type"] = "SWAP"
                else:
                    symbol_map = {
                        "BTC": "BTC",
                        "比特币": "BTC",
                        "黄金": "GC",
                        "小纳指": "MNQ",
                        "纳指": "NQ",
                        "标普": "ES",
                        "道指": "YM",
                    }
                    for k, v in symbol_map.items():
                        if k in symbol:
                            symbol = v
                            break
                    if symbol in CMDTY_SYMBOLS:
                        result["sec_type"] = "CMDTY"
                        result["exchange"] = "SMART"
                    elif symbol in FOREX_SYMBOLS:
                        result["sec_type"] = "CASH"
                        result["exchange"] = "IDEALPRO"

                result["symbol"] = symbol

            return result

    return {"action": "UNKNOWN", "raw": msg}


if __name__ == "__main__":
    test_cases = [
        "平掉BTC仓位",
        "平仓GC",
        "买入1手GC",
        "卖空2手NQ",
        "查看持仓",
        "今天天气怎么样",
    ]

    for msg in test_cases:
        result = parse_trading_command(msg)
        print(f"{msg} -> {result}")
