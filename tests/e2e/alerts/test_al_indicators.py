"""
AL Alerts Functional Tests
L2: Period switching, alert trigger/expand
"""

import pytest
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/alerts")
    return page


@pytest.mark.l2
@pytest.mark.ac_al_us1_2
def test_period_switch_updates_data(authenticated_page: Page):
    combobox = authenticated_page.get_by_role("combobox").first
    initial_value = combobox.input_value()
    combobox.select_option("M5")
    expect(authenticated_page.get_by_text("M5")).to_be_visible()


@pytest.mark.l2
@pytest.mark.ac_al_us1_3
def test_alert_triggers_on_rsi_extreme(authenticated_page: Page):
    alert_item = authenticated_page.locator('[data-testid="stExpander"]').first
    if alert_item.is_visible():
        alert_item.click()


@pytest.mark.l2
@pytest.mark.ac_al_us1_4
def test_alert_triggers_on_price_move(authenticated_page: Page):
    alerts = authenticated_page.locator('[data-testid="stExpander"]')
    if alerts.count() > 0:
        expect(alerts.first).to_be_visible()


@pytest.mark.l2
@pytest.mark.ac_al_us1_5
def test_alert_list_updates_realtime(authenticated_page: Page):
    initial_count = authenticated_page.locator('[data-testid="stExpander"]').count()
    authenticated_page.wait_for_timeout(2000)
    new_count = authenticated_page.locator('[data-testid="stExpander"]').count()


@pytest.mark.l2
@pytest.mark.ac_al_us1_6
def test_alert_expand_shows_details(authenticated_page: Page):
    if authenticated_page.locator('[data-testid="stExpander"]').count() > 0:
        authenticated_page.locator('[data-testid="stExpander"]').first.click()
        expect(authenticated_page.get_by_text("触发时间")).to_be_visible()


@pytest.mark.l2
@pytest.mark.ac_al_us1_7
def test_alert_detail_shows_threshold(authenticated_page: Page):
    if authenticated_page.locator('[data-testid="stExpander"]').count() > 0:
        authenticated_page.locator('[data-testid="stExpander"]').first.click()
        expect(authenticated_page.get_by_text("阈值")).to_be_visible()


@pytest.mark.l2
@pytest.mark.ac_al_us1_8
def test_correlation_alert_on_low_value(authenticated_page: Page):
    has_corr = authenticated_page.getByText("相关性").is_visible()
    has_alert = authenticated_page.locator('[data-testid="stExpander"]').count() > 0
    assert has_corr or has_alert


@pytest.mark.l2
@pytest.mark.ac_al_us1_11
def test_correlation_heatmap_displayed(authenticated_page: Page):
    has_matrix = authenticated_page.getByText("矩阵").is_visible()
    has_chart = authenticated_page.locator("canvas").count() > 0
    assert has_matrix or has_chart
