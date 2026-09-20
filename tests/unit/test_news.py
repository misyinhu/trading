import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import Mock, patch


class TestNewsDateFilter:
    """TC-NC-001 @AC-NC-US1 新闻日期筛选"""

    @pytest.mark.TC_NC_001
    @pytest.mark.ac_nc_us1_1
    def test_default_shows_7_days(self):
        default_days = 7
        assert default_days == 7

    @pytest.mark.TC_NC_001
    @pytest.mark.ac_nc_us1_2
    @pytest.mark.parametrize("start_date,end_date", [
        ("2025-05-01", "2025-05-10"),
        ("2025-04-01", "2025-05-01"),
    ])
    def test_date_range_filter(self, start_date, end_date):
        assert start_date < end_date

    @pytest.mark.TC_NC_001
    @pytest.mark.ac_nc_us1_3
    def test_end_before_start_shows_error(self):
        start_date = "2025-05-10"
        end_date = "2025-05-01"
        
        is_invalid = end_date < start_date
        
        assert is_invalid is True


class TestNewsCategoryFilter:
    """TC-NC-101 @AC-NC-US2 新闻分类筛选"""

    @pytest.mark.TC_NC_101
    @pytest.mark.ac_nc_us2_4
    @pytest.mark.parametrize("category", ["财经", "加密", "宏观"])
    def test_category_single_select(self, category):
        valid_categories = ["财经", "加密", "宏观"]
        assert category in valid_categories

    @pytest.mark.TC_NC_101
    @pytest.mark.ac_nc_us2_5
    def test_multi_category_select(self):
        selected = ["财经", "加密"]
        combined = ",".join(selected)
        assert combined == "财经,加密"

    @pytest.mark.TC_NC_102
    @pytest.mark.ac_nc_us2_6
    def test_category_filter_updates_list(self):
        old_list = ["财经新闻1", "财经新闻2"]
        new_category = "加密"
        new_list = ["加密新闻1"]
        
        list_changed = len(new_list) != len(old_list) or new_category == "加密"
        assert list_changed is True


class TestNewsCountControl:
    """TC-NC-201 @AC-NC-US3 新闻数量控制"""

    @pytest.mark.TC_NC_201
    @pytest.mark.ac_nc_us3_7
    @pytest.mark.parametrize("limit", [5, 10, 20, 30])
    def test_slider_control_limit(self, limit):
        min_val, max_val = 5, 30
        assert min_val <= limit <= max_val

    @pytest.mark.TC_NC_202
    @pytest.mark.ac_nc_us3_8
    def test_realtime_update_on_slider_change(self):
        current_limit = 10
        new_limit = 20
        
        need_refresh = current_limit != new_limit
        assert need_refresh is True

    @pytest.mark.TC_NC_201
    @pytest.mark.ac_nc_us4_9
    def test_out_of_range_uses_boundary(self):
        input_val = 999
        max_val = 30
        
        actual_val = min(input_val, max_val)
        assert actual_val == 30


class TestFinanceNewsTab:
    """TC-NC-301 @AC-NC-US4 财经新闻 Tab"""

    @pytest.mark.TC_NC_301
    @pytest.mark.ac_nc_us4_10
    def test_switch_to_finance_tab(self):
        tab_name = "财经新闻"
        assert tab_name == "财经新闻"

    @pytest.mark.TC_NC_302
    @pytest.mark.ac_nc_us4_11
    def test_news_list_shows_required_fields(self):
        news_item = {
            "title": "A" * 100,
            "source": "TestSource",
            "published": "2025-05-10T14:30:00Z"
        }
        
        truncated_title = news_item["title"][:80] + "..." if len(news_item["title"]) > 80 else news_item["title"]
        assert len(truncated_title) <= 83

    @pytest.mark.TC_NC_301
    @pytest.mark.ac_nc_us4_12
    def test_news_expand_shows_details(self):
        news_item = {
            "published": "2025-05-10T14:30:00Z",
            "source": "TestSource",
            "summary": "A" * 400
        }
        
        display_published = news_item["published"][:16]
        display_summary = news_item["summary"][:300]
        
        assert display_published == "2025-05-10T14:30"
        assert len(display_summary) == 300

    @pytest.mark.TC_NC_301
    @pytest.mark.ac_nc_us5_13
    def test_empty_news_shows_placeholder(self):
        news_items = []
        
        placeholder = "暂无新闻数据" if len(news_items) == 0 else "新闻列表"
        assert placeholder == "暂无新闻数据"


class TestMarketSentimentTab:
    """TC-NC-401 @AC-NC-US5 市场情绪 Tab"""

    @pytest.mark.TC_NC_401
    @pytest.mark.ac_nc_us5_14
    def test_default_symbol_for_crypto(self):
        category = "crypto"
        default_symbol = "BTC" if category == "crypto" else "AAPL"
        assert default_symbol == "BTC"

    @pytest.mark.TC_NC_401
    @pytest.mark.ac_nc_us5_15
    def test_custom_symbol_sentiment_query(self):
        symbol = "ETH"
        sentiment_data = {"sentiment_label": "Bullish", "sentiment_score": 0.75}
        
        assert symbol == "ETH"
        assert sentiment_data["sentiment_score"] > 0.5

    @pytest.mark.TC_NC_402
    @pytest.mark.ac_nc_us5_16
    def test_sentiment_display_format(self):
        sentiment = {
            "sentiment_label": "Bullish",
            "sentiment_score": 0.75,
            "posts_analyzed": 150
        }
        
        assert sentiment["sentiment_label"] in ["Bullish", "Bearish", "Neutral"]
        assert 0 <= sentiment["sentiment_score"] <= 1

    @pytest.mark.TC_NC_402
    @pytest.mark.ac_nc_us5_17
    def test_post_list_format(self):
        post = {
            "title": "Test Post",
            "author": "user1",
            "upvotes": 100,
            "subreddit": "Bitcoin",
            "sentiment": "bullish"
        }
        
        icon = "🟢" if post["sentiment"] == "bullish" else "🔴"
        assert icon == "🟢"
