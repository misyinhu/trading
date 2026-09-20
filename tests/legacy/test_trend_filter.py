from typing import List
from okx_client.utils import calculate_ema

def check_trend_filter(price: float, ohlc_closes: List[float], period: int = 200) -> str:
    """趋势过滤器: 返回 'long', 'short', 'hold'"""
    ema200 = calculate_ema(ohlc_closes, period)
    if ema200 is None:
        return 'hold'
    
    if price > ema200:
        return 'long'
    elif price < ema200:
        return 'short'
    return 'hold'

def test_trend_filter():
    # 构造数据：前200个是100，第201个是101（Price > EMA200）
    data = [100.0] * 200 + [101.0]
    # EMA200 的 SMA 是 100.0，第201个点 EMA 约为 100.0099
    # 所以 101 > 100.0099
    assert check_trend_filter(101.0, data) == 'long'
    
    # 构造数据：前200个是100，第201个是99（Price < EMA200）
    data2 = [100.0] * 200 + [99.0]
    # EMA200 的 SMA 是 100.0，第201个点 EMA 约为 99.99
    # 所以 99 < 99.99
    assert check_trend_filter(99.0, data2) == 'short'
