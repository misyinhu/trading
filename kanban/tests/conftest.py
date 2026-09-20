"""
Kanban 测试套件 - pytest 配置和共享 fixtures

这个文件会在每个测试模块执行前自动被 pytest 加载。
定义此文件的目的是提供可复用的 fixtures 和配置。
"""

import sys
import os
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import numpy as np

# ============ 路径配置 ============
# 确保 kanban 目录在 Python 路径中
KANBAN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(KANBAN_ROOT))
sys.path.insert(0, str(KANBAN_ROOT.parent))  # 便于导入 config 等共享模块

# ============ 测试数据 Fixtures ============

@pytest.fixture
def sample_ohlcv_bars() -> List[Dict[str, Any]]:
    """标准 OHLCV K线数据 - 可重现测试数据"""
    np.random.seed(42)
    base_price = 100.0
    bars = []
    
    for i in range(50):
        close = base_price + np.random.randn() * 2
        open_price = close + np.random.uniform(-0.5, 0.5)
        high = max(open_price, close) + abs(np.random.uniform(0, 1))
        low = min(open_price, close) - abs(np.random.uniform(0, 1))
        volume = int(np.random.uniform(1000000, 5000000))
        
        bars.append({
            "timestamp": datetime.now() - timedelta(days=50-i),
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": volume,
        })
    
    return bars


@pytest.fixture
def sample_directions_up() -> List[str]:
    """全上涨方向列表"""
    return ["up", "up", "up", "up", "up"]


@pytest.fixture
def sample_directions_down() -> List[str]:
    """全下跌方向列表"""
    return ["down", "down", "down", "down", "down"]


@pytest.fixture
def sample_directions_mixed() -> List[str]:
    """混合方向列表"""
    return ["up", "up", "neutral", "neutral", "neutral"]


@pytest.fixture
def sample_directions_conflict() -> List[str]:
    """矛盾方向列表"""
    return ["up", "down", "up", "down", "neutral"]


@pytest.fixture
def sample_timeframe_data() -> Dict[str, Any]:
    """多周期时间框架数据"""
    return {
        "1m": {
            "trend": "up",
            "rsi": 58,
            "ma20": 100.5,
            "bars": [{"close": 101}, {"close": 102}] * 10,
        },
        "5m": {
            "trend": "up",
            "rsi": 55,
            "ma20": 100.2,
            "bars": [{"close": 100}, {"close": 101}] * 15,
        },
        "30m": {
            "trend": "up",
            "rsi": 52,
            "ma20": 99.8,
            "bars": [{"close": 99}, {"close": 100}] * 30,
        },
        "4h": {
            "trend": "down",
            "rsi": 45,
            "ma20": 101.0,
            "bars": [{"close": 102}, {"close": 101}] * 20,
        },
        "1D": {
            "trend": "neutral",
            "rsi": 50,
            "ma20": 100.0,
            "bars": [{"close": 100}, {"close": 100}] * 10,
        },
    }


@pytest.fixture
def sample_spread_data() -> tuple:
    """套利数据 - 两组相关品种的价差数据"""
    bars1 = [{"close": 100 + i * 0.5} for i in range(20)]
    bars2 = [{"close": 50 + i * 0.3} for i in range(20)]
    return bars1, bars2


@pytest.fixture
def sample_order_params() -> Dict[str, Any]:
    """标准订单参数"""
    return {
        "symbol": "AAPL",
        "action": "BUY",
        "quantity": 100,
        "order_type": "MKT",
        "exchange": "SMART",
        "sec_type": "STK",
    }


@pytest.fixture
def sample_trade_signal() -> Dict[str, Any]:
    """样本交易信号"""
    return {
        "symbol": "GC",
        "action": "BUY",
        "quantity": 1,
        "entry_price": 2350.0,
        "stop_loss": 2330.0,
        "take_profit": 2380.0,
        "confidence": 0.85,
        "strategy": "triple_screen",
        "indicators": {
            "zscore": 2.1,
            "rsi": 65,
            "ema_alignment": "BULLISH",
        },
    }


# ============ Mock Fixtures ============

@pytest.fixture
def mock_ib_connection():
    """Mock IBKR 连接"""
    mock = MagicMock()
    mock.isConnected = MagicMock(return_value=True)
    mock.accountSummary = MagicMock(return_value=[
        MagicMock(tag="NetLiquidation", value="1000000"),
        MagicMock(tag="BuyingPower", value="500000"),
    ])
    mock.positions = MagicMock(return_value=[])
    return mock


@pytest.fixture
def mock_tv_datafeed():
    """Mock TradingView 数据源"""
    mock = MagicMock()
    mock.getBars = MagicMock(return_value=[
        {"time": 1704067200, "close": 100, "volume": 1000},
        {"time": 1704153600, "close": 101, "volume": 1100},
    ])
    return mock


# ============ Streamlit 测试辅助 ============

@pytest.fixture(autouse=True)
def clear_streamlit_cache():
    """每个测试后清除 Streamlit 缓存"""
    yield
    try:
        import streamlit as st
        st.cache_data.clear()
        st.cache_resource.clear()
    except ImportError:
        pass


# ============ 测试标记配置 ============

def pytest_configure(config):
    """注册自定义标记"""
    config.addinivalue_line(
        "markers", "unit: Unit tests - fast, isolated tests (<1s)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests - component interaction (1-30s)"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests - full workflow testing"
    )
    config.addinivalue_line(
        "markers", "slow: Slow running tests - typically >30s"
    )
    config.addinivalue_line(
        "markers", "ibkr: Requires IBKR connection or mock"
    )
    config.addinivalue_line(
        "markers", "trading: Real trading logic tests"
    )
