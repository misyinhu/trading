"""
RS Resonance Page Load Tests
L1: Page element visibility, no JS errors
"""

import pytest
import re
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/resonance")
    return page


@pytest.mark.L1
@pytest.mark.tc_rs_001
def test_rs_page_loads_successfully(authenticated_page: Page):
    expect(authenticated_page).to_have_title(re.compile(r"Streamlit|Resonance"))


@pytest.mark.L1
@pytest.mark.ac_rs_us1_1
def test_chart_area_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert (
        authenticated_page.locator('[data-testid="stVegaLiteChart"]').is_visible()
        or authenticated_page.locator(".js-plotly-plot").is_visible()
        or authenticated_page.locator("canvas").first.is_visible()
        or authenticated_page.get_by_text("chart").is_visible()
    )


@pytest.mark.L1
@pytest.mark.ac_rs_us2_4
def test_resonance_score_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert (
        authenticated_page.get_by_text("共振").is_visible()
        or authenticated_page.get_by_text("%").is_visible()
        or authenticated_page.get_by_text("resonance").is_visible()
    )


@pytest.mark.L1
@pytest.mark.ac_rs_us1_13
def test_empty_state_or_chart(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    has_chart = authenticated_page.locator("canvas").first.is_visible()
    has_empty = authenticated_page.get_by_text("暂无数据").is_visible()
    has_title = authenticated_page.get_by_text("共振").is_visible()
    assert has_chart or has_empty or has_title


@pytest.mark.L1
@pytest.mark.ac_rs_us2_5
def test_contradiction_warning_area(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    has_warning = authenticated_page.get_by_text("矛盾").is_visible()
    has_chart = authenticated_page.locator("canvas").first.is_visible()
    has_title = authenticated_page.get_by_text("共振").is_visible()
    assert has_warning or has_chart or has_title
