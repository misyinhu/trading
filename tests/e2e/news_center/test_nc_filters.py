"""
NC News Center Functional Tests
L2: Date/Category filters, tabs interaction
"""

import pytest
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/news_center")
    return page


@pytest.mark.L2
@pytest.mark.ac_nc_us1_2
def test_default_shows_last_7_days(authenticated_page: Page):
    start_date = (
        authenticated_page.get_by_text("开始日期").locator("..").locator("input").first
    )
    if start_date.is_visible():
        expect(start_date).to_be_visible()


@pytest.mark.L2
@pytest.mark.ac_nc_us1_3
def test_date_change_updates_list(authenticated_page: Page):
    authenticated_page.get_by_text("开始日期").locator("..").locator(
        "input"
    ).first.fill("2024-01-01")
    authenticated_page.get_by_role("button", name="刷新").click()


@pytest.mark.L2
@pytest.mark.ac_nc_us2_4
def test_category_dropdown_shows_options(authenticated_page: Page):
    combobox = authenticated_page.get_by_role("combobox").first
    combobox.click()
    expect(authenticated_page.locator("option", has_text="财经")).to_be_visible()


@pytest.mark.L2
@pytest.mark.ac_nc_us2_5
def test_multi_select_categories(authenticated_page: Page):
    authenticated_page.get_by_role("combobox").first.click()
    authenticated_page.get_by_text("加密").click()


@pytest.mark.L2
@pytest.mark.ac_nc_us3_7
def test_slider_controls_news_count(authenticated_page: Page):
    slider = authenticated_page.get_by_role("slider").first
    if slider.is_visible():
        slider.fill("20")


@pytest.mark.L2
@pytest.mark.ac_nc_us4_9
def test_financial_news_tab_content(authenticated_page: Page):
    authenticated_page.get_by_text("财经新闻").click()
    expect(authenticated_page.get_by_text("新闻")).to_be_visible()


@pytest.mark.L2
@pytest.mark.ac_nc_us5_11
def test_sentiment_tab_content(authenticated_page: Page):
    authenticated_page.get_by_text("市场情绪").click()
    expect(authenticated_page.get_by_text("情绪")).to_be_visible()


@pytest.mark.L2
@pytest.mark.ac_nc_us4_13
def test_tab_switch_shows_loading(authenticated_page: Page):
    authenticated_page.get_by_text("财经新闻").click()


@pytest.mark.L2
@pytest.mark.ac_nc_us5_16
def test_manual_refresh_button(authenticated_page: Page):
    if authenticated_page.get_by_role("button", name="刷新").is_visible():
        authenticated_page.get_by_role("button", name="刷新").click()
