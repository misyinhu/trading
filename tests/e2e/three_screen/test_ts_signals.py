"""
TS Three Screen Functional Tests
L2: Signal display, cycle cards
"""

import pytest
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    page.goto(f"{BASE_URL}/three_screen")
    return page


@pytest.mark.L2
@pytest.mark.ac_ts_us1_1
def test_three_period_cards_display(authenticated_page: Page):
    expect(authenticated_page.getByText("M30")).to_be_visible()
    expect(authenticated_page.getByText("M5")).to_be_visible()
    expect(authenticated_page.getByText("M1")).to_be_visible()


@pytest.mark.L2
@pytest.mark.ac_ts_us1_2
def test_signal_shows_entry_price(authenticated_page: Page):
    has_signal = (
        authenticated_page.getByText("做多").is_visible()
        or authenticated_page.getByText("做空").is_visible()
    )
    has_entry = authenticated_page.getByText("入场").is_visible()
    assert has_signal or has_entry


@pytest.mark.L2
@pytest.mark.ac_ts_us1_3
def test_aligned_signals_highlighted(authenticated_page: Page):
    has_highlight = authenticated_page.locator(
        '[data-testid="stHighlighter"]'
    ).is_visible()
    has_color = authenticated_page.getByCSS(
        "background-color", has_text="green"
    ).is_visible()
    assert has_highlight or has_color


@pytest.mark.L2
@pytest.mark.ac_ts_us1_4
def test_no_signal_shows_pending(authenticated_page: Page):
    has_pending = authenticated_page.getByText("待确认").is_visible()
    has_neutral = authenticated_page.getByText("观望").is_visible()
    assert has_pending or has_neutral


@pytest.mark.L2
@pytest.mark.ac_ts_us1_5
def test_conflict_warning_displayed(authenticated_page: Page):
    has_conflict = authenticated_page.getByText("矛盾").is_visible()
    has_mixed = authenticated_page.getByText("不一致").is_visible()
    assert has_conflict or has_mixed


@pytest.mark.L2
@pytest.mark.ac_ts_us1_6
def test_summary_shows_all_status(authenticated_page: Page):
    expect(authenticated_page.getByText("汇总")).to_be_visible()
    expect(authenticated_page.getByText("共振")).to_be_visible()


@pytest.mark.L2
@pytest.mark.ac_ts_us1_7
def test_last_update_time_shown(authenticated_page: Page):
    has_time = authenticated_page.getByText("更新时间").is_visible()
    has_refresh = authenticated_page.getByText("刷新").is_visible()
    assert has_time or has_refresh
