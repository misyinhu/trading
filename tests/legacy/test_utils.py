import pytest
from okx_client.utils import calculate_ema

def test_calculate_ema():
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    # Period 2 EMA calculation:
    # SMA1: (1.0+2.0)/2 = 1.5
    # EMA2: (3.0-1.5)*2/3 + 1.5 = 2.5
    # EMA3: (4.0-2.5)*2/3 + 2.5 = 3.5
    # EMA4: (5.0-3.5)*2/3 + 3.5 = 4.5
    ema = calculate_ema(data, 2)
    assert ema is not None
    assert abs(ema - 4.5) < 1e-9
