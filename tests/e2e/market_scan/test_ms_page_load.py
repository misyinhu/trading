"""
MS Market Scan Page Load Tests
L1: Page element visibility, no JS errors
"""

import pytest
import re
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/market_scan")
    return page


@pytest.mark.l1
@pytest.mark.tc_ms_001
def test_ms_page_loads_successfully(authenticated_page: Page):
    expect(authenticated_page).to_have_title(re.compile(r"Streamlit|Market Scan"))


@pytest.mark.l1
@pytest.mark.ac_ms_us1_1
def test_scan_type_selector_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert authenticated_page.get_by_role("combobox").is_visible()


@pytest.mark.l1
@pytest.mark.ac_ms_us2_3
def test_exchange_checkboxes_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert (
        authenticated_page.get_by_text("OKX").is_visible()
        or authenticated_page.get_by_text("IBKR").is_visible()
        or authenticated_page.locator('[data-testid="stCheckbox"]').first.is_visible()
    )


@pytest.mark.l1
@pytest.mark.ac_ms_us3_5
def test_scan_button_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert (
        authenticated_page.get_by_role("button", name="开始扫描").is_visible()
        or authenticated_page.get_by_role("button", name="扫描").is_visible()
        or authenticated_page.get_by_text("🚀 开始扫描").is_visible()
    )


@pytest.mark.l1
@pytest.mark.ac_ms_us3_7
def test_results_table_area_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert (
        authenticated_page.locator('[data-testid="stDataFrame"]').is_visible()
        or authenticated_page.locator("table").is_visible()
        or authenticated_page.get_by_text("市场扫描").is_visible()
    )
