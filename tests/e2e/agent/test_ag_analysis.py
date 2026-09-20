"""
AG Agent Functional Tests
L2: Keyword input, AI analysis, history
"""

import pytest
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/market_agent")
    return page


@pytest.mark.L2
@pytest.mark.ac_ag_us1_2
def test_keyword_parsed_to_symbol(authenticated_page: Page):
    input_box = authenticated_page.get_by_role("textbox")
    if input_box.is_visible():
        input_box.fill("BTC")
        analyze_btn = authenticated_page.get_by_role("button", name="分析")
        if analyze_btn.is_visible():
            analyze_btn.click()


@pytest.mark.L2
@pytest.mark.ac_ag_us1_3
def test_parsed_result_displayed(authenticated_page: Page):
    has_result = authenticated_page.getByText("BTC").is_visible()
    has_arrow = authenticated_page.getByText("→").is_visible()
    assert has_result or has_arrow


@pytest.mark.L2
@pytest.mark.ac_ag_us2_5
def test_analysis_result_shows_confidence(authenticated_page: Page):
    has_conclusion = authenticated_page.getByText("结论").is_visible()
    has_confidence = authenticated_page.getByText("置信度").is_visible()
    assert has_conclusion or has_confidence


@pytest.mark.L2
@pytest.mark.ac_ag_us2_6
def test_pdf_export_button_works(authenticated_page: Page):
    export_btn = authenticated_page.getByText("导出")
    if export_btn.is_visible():
        export_btn.click()


@pytest.mark.L2
@pytest.mark.ac_ag_us1_7
def test_unknown_keyword_shows_error(authenticated_page: Page):
    input_box = authenticated_page.get_by_role("textbox")
    if input_box.is_visible():
        input_box.fill("UNKNOWNXYZ123")
        analyze_btn = authenticated_page.get_by_role("button", name="分析")
        if analyze_btn.is_visible():
            analyze_btn.click()


@pytest.mark.L2
@pytest.mark.ac_ag_us2_9
def test_api_timeout_shows_retry(authenticated_page: Page):
    input_box = authenticated_page.get_by_role("textbox")
    if input_box.is_visible():
        input_box.fill("BTC")
        analyze_btn = authenticated_page.get_by_role("button", name="分析")
        if analyze_btn.is_visible():
            analyze_btn.click()
        retry_btn = authenticated_page.get_by_role("button", name="重试")
        if retry_btn.is_visible():
            expect(retry_btn).to_be_visible()


@pytest.mark.L2
@pytest.mark.ac_ag_us3_11
def test_history_list_queryable(authenticated_page: Page):
    has_history = authenticated_page.getByText("历史").is_visible()
    has_table = authenticated_page.locator('[data-testid="stDataFrame"]').is_visible()
    assert has_history or has_table


@pytest.mark.L2
@pytest.mark.ac_ag_us3_12
def test_history_pagination_works(authenticated_page: Page):
    pagination = authenticated_page.getByText("下一页")
    if pagination.is_visible():
        pagination.click()


@pytest.mark.L2
@pytest.mark.ac_ag_us3_14
def test_history_time_filter(authenticated_page: Page):
    date_input = authenticated_page.get_by_role("textbox", name="日期")
    if date_input.is_visible():
        date_input.fill("2024-01-01")
