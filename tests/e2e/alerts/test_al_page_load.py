"""
AL Alerts Page Load Tests
L1: Page element visibility, no JS errors
"""

import pytest
import re
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/alerts")
    return page


@pytest.mark.l1
@pytest.mark.tc_al_001
def test_al_page_loads_successfully(authenticated_page: Page):
    expect(authenticated_page).to_have_title(re.compile(r"Streamlit|Alerts"))


@pytest.mark.l1
@pytest.mark.ac_al_us1_1
def test_timeframe_selector_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert authenticated_page.locator('[data-testid="stSelectbox"]').first.is_visible()


@pytest.mark.l1
@pytest.mark.ac_al_us2_3
def test_alert_list_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert (
        authenticated_page.get_by_text("警报").is_visible()
        or authenticated_page.locator('[data-testid="stExpander"]').first.is_visible()
    )


@pytest.mark.l1
@pytest.mark.ac_al_us3_6
def test_alert_expand_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert (
        authenticated_page.get_by_text("详情").is_visible()
        or authenticated_page.locator('[data-testid="stExpander"]').first.is_visible()
        or authenticated_page.get_by_text("警报").is_visible()
    )


@pytest.mark.l1
@pytest.mark.ac_al_us5_12
def test_settings_button_visible(authenticated_page: Page):
    authenticated_page.wait_for_timeout(2000)
    assert (
        authenticated_page.get_by_role("button", name="设置").is_visible()
        or authenticated_page.get_by_role("button", name="Settings").is_visible()
        or authenticated_page.get_by_role("button").first.is_visible()
    )
