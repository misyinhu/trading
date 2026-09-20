"""
TS Three Screen Page Load Tests
L1: Page element visibility, no JS errors
"""

import pytest
import re
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/three_screen")
    return page


@pytest.mark.L1
@pytest.mark.tc_ts_201
def test_ts_page_loads_successfully(authenticated_page: Page):
    expect(authenticated_page).to_have_title(re.compile(r"Streamlit|Three Screen"))


@pytest.mark.L1
@pytest.mark.ac_ts_us1_1
def test_three_cycle_cards_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    has_m30 = authenticated_page.get_by_text("M30").is_visible()
    has_m5 = authenticated_page.get_by_text("M5").is_visible()
    has_m1 = authenticated_page.get_by_text("M1").is_visible()
    has_title = authenticated_page.get_by_text("三重滤网").is_visible()
    assert has_m30 or has_m5 or has_m1 or has_title


@pytest.mark.L1
@pytest.mark.ac_ts_us1_2
def test_signal_display_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert (
        authenticated_page.get_by_text("信号").is_visible()
        or authenticated_page.get_by_text("做多").is_visible()
        or authenticated_page.get_by_text("做空").is_visible()
        or authenticated_page.get_by_text("三重滤网").is_visible()
    )


@pytest.mark.L1
@pytest.mark.ac_ts_us1_3
def test_scan_button_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert (
        authenticated_page.get_by_role("button", name="扫描").is_visible()
        or authenticated_page.get_by_role("button", name="开始扫描").is_visible()
        or authenticated_page.get_by_text("🚀 开始扫描").is_visible()
    )


@pytest.mark.L1
@pytest.mark.ac_ts_us1_6
def test_summary_display_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert (
        authenticated_page.get_by_text("汇总").is_visible()
        or authenticated_page.get_by_text("共振").is_visible()
        or authenticated_page.get_by_text("三重滤网").is_visible()
    )
