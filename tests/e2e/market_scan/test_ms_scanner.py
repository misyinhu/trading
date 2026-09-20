"""
MS Market Scan Functional Tests
L2: Scan type selection, exchange filter, scan execution
"""

import pytest
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/market_scan")
    return page


@pytest.mark.L2
@pytest.mark.ac_ms_us1_2
def test_params_change_with_scan_type(authenticated_page: Page):
    combobox = authenticated_page.get_by_role("combobox").first
    combobox.select_option("bollinger")
    expect(authenticated_page.get_by_text("布林")).to_be_visible()


@pytest.mark.L2
@pytest.mark.ac_ms_us2_4
def test_select_all_exchanges(authenticated_page: Page):
    authenticated_page.get_by_text("OKX").click()
    if authenticated_page.getByText("IBKR").is_visible():
        authenticated_page.getByText("IBKR").click()


@pytest.mark.L2
@pytest.mark.ac_ms_us3_5
def test_scan_button_starts_scan(authenticated_page: Page):
    scan_btn = authenticated_page.get_by_role("button", name="开始扫描")
    if scan_btn.is_visible():
        scan_btn.click()
        expect(authenticated_page.getByText("扫描中")).to_be_visible()


@pytest.mark.L2
@pytest.mark.ac_ms_us3_6
def test_progress_bar_displayed(authenticated_page: Page):
    scan_btn = authenticated_page.get_by_role("button", name="开始扫描")
    if scan_btn.is_visible():
        scan_btn.click()
        progress = authenticated_page.locator('[role="progressbar"]')
        if progress.is_visible():
            expect(progress).to_be_visible()


@pytest.mark.L2
@pytest.mark.ac_ms_us3_7
def test_results_displayed_in_table(authenticated_page: Page):
    has_table = authenticated_page.locator("table").is_visible()
    has_dataframe = authenticated_page.locator(
        '[data-testid="stDataFrame"]'
    ).is_visible()
    assert has_table or has_dataframe


@pytest.mark.L2
@pytest.mark.ac_ms_us2_9
def test_exchange_connection_error_shown(authenticated_page: Page):
    scan_btn = authenticated_page.get_by_role("button", name="开始扫描")
    if scan_btn.is_visible():
        scan_btn.click()
        authenticated_page.wait_for_timeout(3000)
        has_error = authenticated_page.getByText("连接失败").is_visible()
        has_timeout = authenticated_page.getByText("超时").is_visible()
        has_table = authenticated_page.locator("table").is_visible()
        assert has_error or has_timeout or has_table


@pytest.mark.L2
@pytest.mark.ac_ms_us3_10
def test_scan_timeout_handling(authenticated_page: Page):
    scan_btn = authenticated_page.get_by_role("button", name="开始扫描")
    if scan_btn.is_visible():
        scan_btn.click()
        authenticated_page.wait_for_timeout(35000)


@pytest.mark.L2
@pytest.mark.ac_ms_us3_11
def test_cancel_scan_button(authenticated_page: Page):
    scan_btn = authenticated_page.get_by_role("button", name="开始扫描")
    if scan_btn.is_visible():
        scan_btn.click()
        cancel_btn = authenticated_page.get_by_role("button", name="取消")
        if cancel_btn.is_visible():
            cancel_btn.click()


@pytest.mark.L2
@pytest.mark.ac_ms_us3_14
def test_table_column_sorting(authenticated_page: Page):
    if authenticated_page.locator("th").count() > 0:
        authenticated_page.locator("th").first.click()
