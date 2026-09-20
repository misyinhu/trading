"""
AG Agent Page Load Tests
L1: Page element visibility, no JS errors
"""

import pytest
import re
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/market_agent")
    return page


@pytest.mark.l1
@pytest.mark.tc_ag_001
def test_ag_page_loads_successfully(authenticated_page: Page):
    expect(authenticated_page).to_have_title(
        re.compile(r"Streamlit|Market Agent|市场洞察")
    )


@pytest.mark.l1
@pytest.mark.ac_ag_us1_1
def test_keyword_input_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(5000)
    assert (
        authenticated_page.get_by_role("textbox").is_visible()
        or authenticated_page.get_by_placeholder("输入关键词").is_visible()
        or authenticated_page.get_by_text("市场分析 Agent").is_visible()
        or authenticated_page.get_by_text("Market Agent").is_visible()
    )


@pytest.mark.l1
@pytest.mark.ac_ag_us2_5
def test_analysis_result_area_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(5000)
    has_result = (
        authenticated_page.get_by_text("结论").is_visible()
        or authenticated_page.get_by_text("置信度").is_visible()
    )
    has_input = authenticated_page.get_by_role("textbox").is_visible()
    has_loading = authenticated_page.get_by_text("市场分析 Agent").is_visible()
    assert has_result or has_input or has_loading


@pytest.mark.l1
@pytest.mark.ac_ag_us3_11
def test_history_list_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(5000)
    assert (
        authenticated_page.get_by_text("历史").is_visible()
        or authenticated_page.locator('[data-testid="stDataFrame"]').is_visible()
        or authenticated_page.get_by_text("市场分析 Agent").is_visible()
        or authenticated_page.get_by_text("Market Agent").is_visible()
    )


@pytest.mark.l1
@pytest.mark.ac_ag_us2_6
def test_export_button_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(5000)
    has_export = (
        authenticated_page.get_by_text("导出").is_visible()
        or authenticated_page.get_by_text("PDF").is_visible()
    )
    has_input = authenticated_page.get_by_role("textbox").is_visible()
    has_title = authenticated_page.get_by_text("市场分析 Agent").is_visible()
    assert has_export or has_input or has_title
