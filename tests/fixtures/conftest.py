import pytest
import sys
import os
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def mock_ib_connection():
    mock_ib = Mock()
    mock_ib.positions.return_value = []
    mock_ib.placeOrder.return_value = create_mock_order()
    return mock_ib


def create_mock_order():
    mock_order = Mock()
    mock_order.orderStatus.status = "Filled"
    mock_order.orderStatus.filled = 1
    mock_order.orderStatus.remaining = 0
    mock_order.order.orderId = 123
    mock_order.order.action = "BUY"
    return mock_order


def mock_feishu():
    return (True, "OK")


@pytest.fixture
def mock_tv_indicators():
    return {
        "RSI": 65.5,
        "MA20": 15000.0,
        "price": 15100.0,
    }


@pytest.fixture
def mock_news_data():
    return [
        {
            "title": "Test News Title",
            "summary": "Test summary",
            "published": "2025-05-10T14:30:00Z",
            "source": "TestSource",
            "url": "https://example.com/news/1",
        }
    ]


@pytest.fixture
def mock_sentiment_data():
    return {
        "sentiment_label": "Bullish",
        "sentiment_score": 0.75,
        "posts_analyzed": 150,
        "top_posts": [
            {
                "title": "Bullish post",
                "author": "user1",
                "upvotes": 100,
                "subreddit": "Bitcoin",
                "sentiment": "bullish",
            }
        ],
    }


@pytest.fixture(autouse=True)
def setup_mocks():
    with patch(
        "client.ib_connection.get_ib_connection", return_value=mock_ib_connection()
    ):
        with patch("notify.webhook_bridge.send_feishu", return_value=mock_feishu()):
            with patch(
                "notify.webhook_bridge.get_tenant_token", return_value="mock_token"
            ):
                yield
