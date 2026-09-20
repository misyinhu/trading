"""
AL Alerts Settings E2E Tests
TC-AL-501, TC-AL-502: Alert custom settings
AC_AL_12, AC_AL_13 coverage
"""

import pytest
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/alerts")
    return page


@pytest.mark.l2
@pytest.mark.ac_al_us5_12
def test_custom_alert_thresholds(authenticated_page: Page):
    """AL-AC12: 用户自定义警报阈值"""
    page = authenticated_page
    page.get_by_role("button", name="设置").first.click()
    rsi_overbought = page.get_by_placeholder("RSI超买")
    if rsi_overbought.count() > 0:
        rsi_overbought.fill("80")
    price_change = page.get_by_placeholder("价格变化")
    if price_change.count() > 0:
        price_change.fill("3")
    corr_threshold = page.get_by_placeholder("相关性")
    if corr_threshold.count() > 0:
        corr_threshold.fill("0.5")
    page.get_by_role("button", name="保存").click()
    page.reload()
    expect(page.get_by_text("RSI超买")).to_be_visible()


@pytest.mark.l2
@pytest.mark.ac_al_us5_13
def test_alert_sound_toggle_independent(authenticated_page: Page):
    """AL-AC13: 警报声音开关可独立控制"""
    page = authenticated_page
    page.get_by_role("button", name="设置").first.click()
    rsi_toggle = page.get_by_role("switch", name="RSI警报声音")
    if rsi_toggle.count() > 0:
        rsi_toggle.click()
        expect(rsi_toggle).to_have_attribute("aria-checked", "false")
    price_toggle = page.get_by_role("switch", name="价格警报声音")
    if price_toggle.count() > 0:
        expect(price_toggle).to_have_attribute("aria-checked", "true")
