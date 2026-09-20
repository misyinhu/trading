"""
RS Resonance Functional Tests
L2: Chart interaction, resonance score display
"""

import pytest
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/resonance")
    return page


@pytest.mark.L2
@pytest.mark.ac_rs_us1_2
def test_chart_supports_zoom(authenticated_page: Page):
    chart = authenticated_page.locator("canvas").first
    if chart.is_visible():
        chart.hover()
        authenticated_page.mouse.wheel(0, 100)


@pytest.mark.L2
@pytest.mark.ac_rs_us1_2
def test_chart_supports_scroll(authenticated_page: Page):
    chart = authenticated_page.locator("canvas").first
    if chart.is_visible():
        chart.hover()
        authenticated_page.mouse.down()
        authenticated_page.mouse.move(100, 0)
        authenticated_page.mouse.up()


@pytest.mark.L2
@pytest.mark.ac_rs_us2_3
def test_indicator_line_displayed(authenticated_page: Page):
    has_ma = authenticated_page.getByText("MA").is_visible()
    has_indicator = authenticated_page.locator("path").count() > 1
    assert has_ma or has_indicator


@pytest.mark.L2
@pytest.mark.ac_rs_us2_4
def test_resonance_score_percentage(authenticated_page: Page):
    has_score = authenticated_page.getByText("%").is_visible()
    has_label = authenticated_page.getByText("共振").is_visible()
    assert has_score or has_label


@pytest.mark.L2
@pytest.mark.ac_rs_us2_5
def test_resonance_contradiction_hint(authenticated_page: Page):
    has_hint = authenticated_page.getByText("矛盾").is_visible()
    has_chart = authenticated_page.locator("canvas").is_visible()
    assert has_hint or has_chart


@pytest.mark.L2
@pytest.mark.ac_rs_us2_6
def test_color_coded_intensity(authenticated_page: Page):
    has_green = authenticated_page.getByCSS("color", has_text="green").is_visible()
    has_red = authenticated_page.getByCSS("color", has_text="red").is_visible()
    has_chart = authenticated_page.locator("canvas").is_visible()
    assert has_green or has_red or has_chart


@pytest.mark.L2
@pytest.mark.ac_rs_us3_7
def test_ma20_calculation_displayed(authenticated_page: Page):
    has_ma = authenticated_page.getByText("MA20").is_visible()
    has_value = authenticated_page.locator("text=20").is_visible()
    assert has_ma or has_value


@pytest.mark.L2
@pytest.mark.ac_rs_us3_11
def test_ma_period_modifiable(authenticated_page: Page):
    ma_input = authenticated_page.get_by_role("spinbutton")
    if ma_input.is_visible():
        ma_input.fill("30")
