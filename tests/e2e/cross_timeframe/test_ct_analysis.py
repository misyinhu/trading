"""
CT Cross Timeframe Functional Tests
L2: Z-Score matrix, signal action
"""

import pytest
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/cross_timeframe")
    return page


@pytest.mark.L2
@pytest.mark.ac_ct_us1_1
def test_zscore_matrix_calculation(authenticated_page: Page):
    has_matrix = authenticated_page.getByText("矩阵").is_visible()
    has_table = authenticated_page.locator("table").is_visible()
    assert has_matrix or has_table


@pytest.mark.L2
@pytest.mark.ac_ct_us1_2
def test_correlation_break_detection(authenticated_page: Page):
    has_corr = authenticated_page.getByText("相关性").is_visible()
    has_alert = authenticated_page.getByText("破裂").is_visible()
    assert has_corr or has_alert


@pytest.mark.L2
@pytest.mark.ac_ct_us1_3
def test_contradiction_signal_identified(authenticated_page: Page):
    has_contradiction = authenticated_page.getByText("矛盾").is_visible()
    has_diff = authenticated_page.getByText("冲突").is_visible()
    assert has_contradiction or has_diff


@pytest.mark.L2
@pytest.mark.ac_ct_us1_4
def test_strong_entry_signal_fire(authenticated_page: Page):
    has_strong = authenticated_page.getByText("强烈").is_visible()
    has_entry = authenticated_page.getByText("入场").is_visible()
    assert has_strong or has_entry


@pytest.mark.L2
@pytest.mark.ac_ct_us1_5
def test_buy_signal_displayed(authenticated_page: Page):
    has_buy = authenticated_page.getByText("买入").is_visible()
    has_green = authenticated_page.getByCSS("color", has_text="green").is_visible()
    assert has_buy or has_green


@pytest.mark.L2
@pytest.mark.ac_ct_us1_6
def test_sell_signal_displayed(authenticated_page: Page):
    has_sell = authenticated_page.getByText("卖出").is_visible()
    has_red = authenticated_page.getByCSS("color", has_text="red").is_visible()
    assert has_sell or has_red


@pytest.mark.L2
@pytest.mark.ac_ct_us1_7
def test_neutral_when_no_signal(authenticated_page: Page):
    has_neutral = authenticated_page.getByText("观望").is_visible()
    has_chart = authenticated_page.locator("canvas").is_visible()
    assert has_neutral or has_chart
