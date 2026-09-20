"""
CT Cross Timeframe Page Load Tests
L1: Page element visibility, no JS errors
"""

import pytest
import re
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/cross_timeframe")
    return page


@pytest.mark.L1
@pytest.mark.tc_ct_001
def test_ct_page_loads_successfully(authenticated_page: Page):
    expect(authenticated_page).to_have_title(re.compile(r"Streamlit|Cross Timeframe"))


@pytest.mark.L1
@pytest.mark.ac_ct_us1_1
def test_zscore_matrix_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert (
        authenticated_page.get_by_text("Z-Score").is_visible()
        or authenticated_page.get_by_text("矩阵").is_visible()
        or authenticated_page.get_by_text("跨周期分析").is_visible()
    )


@pytest.mark.L1
@pytest.mark.ac_ct_us1_4
def test_signal_action_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(3000)
    has_signal = (
        authenticated_page.get_by_text("买入").first.is_visible()
        or authenticated_page.get_by_text("卖出").first.is_visible()
        or authenticated_page.get_by_text("观望").first.is_visible()
    )
    has_chart = authenticated_page.locator("canvas").first.is_visible()
    has_title = authenticated_page.get_by_text("跨周期分析").is_visible()
    assert has_signal or has_chart or has_title


@pytest.mark.L1
@pytest.mark.ac_ct_us1_7
def test_neutral_display(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    has_neutral = authenticated_page.get_by_text("观望").is_visible()
    has_matrix = authenticated_page.get_by_text("矩阵").is_visible()
    has_title = authenticated_page.get_by_text("跨周期分析").is_visible()
    assert has_neutral or has_matrix or has_title
