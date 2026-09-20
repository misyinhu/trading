# SimNow CTP 客户端
# 支持内盘期货模拟盘 / 实盘下单

import os

# md-only 行情 worker（CTP_MD_ONLY=1）禁止 import trader 链：包初始化若加载
# thosttraderapi，会与 thostmduserapi 同驻，开盘后原生 abort。
if os.environ.get("CTP_MD_ONLY") != "1":
    from .trader import SimNowTrader, SimNowStatus

    __all__ = ["SimNowTrader", "SimNowStatus"]
else:
    __all__ = []
