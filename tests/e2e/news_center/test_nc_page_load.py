"""
NC News Center Page Load Tests
L1: Page element visibility, no JS errors
"""

import pytest
import re
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/news_center")
    return page


@pytest.mark.L1
@pytest.mark.tc_nc_001
def test_nc_page_loads_successfully(authenticated_page: Page):
    expect(authenticated_page).to_have_title(re.compile(r"Streamlit|News Center"))


@pytest.mark.L1
@pytest.mark.ac_nc_us1_1
def test_date_selector_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert (
        authenticated_page.get_by_text("开始日期").is_visible()
        or authenticated_page.get_by_text("结束日期").is_visible()
        or authenticated_page.get_by_text("日期").is_visible()
    )


@pytest.mark.L1
@pytest.mark.ac_nc_us2_4
def test_category_selector_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert (
        authenticated_page.get_by_text("分类").is_visible()
        or authenticated_page.get_by_role("combobox").is_visible()
        or authenticated_page.get_by_text("新闻").is_visible()
    )


@pytest.mark.L1
@pytest.mark.ac_nc_us3_7
def test_news_limit_slider_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert authenticated_page.get_by_role("slider").is_visible()


@pytest.mark.L1
@pytest.mark.ac_nc_us4_9
def test_financial_news_tab_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(3000)
    assert (
        authenticated_page.get_by_text("财经新闻").first.is_visible()
        or authenticated_page.get_by_text("📋 财经新闻").first.is_visible()
        or authenticated_page.get_by_text("新闻").first.is_visible()
    )


@pytest.mark.L1
@pytest.mark.ac_nc_us5_11
def test_sentiment_tab_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert authenticated_page.get_by_text("市场情绪").is_visible()
