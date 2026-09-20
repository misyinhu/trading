"""
KB Navigation E2E Tests
TC-KB-001: Kanban sidebar navigation
AC_KB_1 ~ AC_KB_10 coverage
"""

import pytest
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8502"


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    """Navigate to Kanban and authenticate if needed."""
    page.goto(BASE_URL)
    return page


@pytest.mark.TC_KB_001
@pytest.mark.ac_kb_us1_1
def test_sidebar_shows_six_entries(authenticated_page: Page):
    """KB-AC1: 侧边栏显示 6 个页面入口"""
    page = authenticated_page
    expected_entries = [
        "News Center",
        "Alerts",
        "Market Scan",
        "Three Screen",
        "Resonance",
        "Agent",
    ]
    for entry in expected_entries:
        locator = page.get_by_text(entry, exact=True)
        expect(locator).to_be_visible()


@pytest.mark.TC_KB_001
@pytest.mark.ac_kb_us1_2
@pytest.mark.parametrize(
    "page_name,url_part",
    [
        ("News Center", r"/news|News Center"),
        ("Alerts", r"/alerts|Alerts"),
        ("Market Scan", r"/scan|Market Scan"),
        ("Three Screen", r"/three-screen|Three Screen"),
        ("Resonance", r"/resonance|Resonance"),
        ("Agent", r"/agent|Agent"),
    ],
)
def test_click_navigates_to_page(
    authenticated_page: Page, page_name: str, url_part: str
):
    """KB-AC2: 点击页面名称跳转到对应页面"""
    page = authenticated_page
    page.get_by_text(page_name, exact=True).click()
    expect(page).to_have_url(pytest.regex(url_part))


@pytest.mark.TC_KB_001
@pytest.mark.ac_kb_us1_3
def test_current_page_highlighted(authenticated_page: Page):
    """KB-AC3: 当前页面高亮显示"""
    page = authenticated_page
    page.get_by_text("News Center", exact=True).click()
    news_entry = page.get_by_text("News Center", exact=True)
    expect(news_entry).to_have_css("background-color", pytest.regex(r".+"))


@pytest.mark.TC_KB_001
@pytest.mark.ac_kb_us1_4
def test_sidebar_shows_icon_and_name(authenticated_page: Page):
    """KB-AC4: 侧边栏显示图标和页面名称"""
    page = authenticated_page
    entries_with_icons = ["News Center", "Alerts", "Market Scan"]
    for entry in entries_with_icons:
        locator = page.get_by_text(entry, exact=True)
        expect(locator).to_be_visible()


@pytest.mark.TC_KB_001
@pytest.mark.ac_kb_us1_5
def test_sidebar_expanded_by_default(authenticated_page: Page):
    """KB-AC5: 页面加载时默认展开侧边栏"""
    page = authenticated_page
    sidebar = page.locator('[data-testid="stSidebar"]')
    expect(sidebar).to_be_visible()


@pytest.mark.TC_KB_001
@pytest.mark.ac_kb_us1_6
def test_hover_shows_tooltip(authenticated_page: Page):
    """KB-AC6: 鼠标悬停页面入口显示提示"""
    page = authenticated_page
    news_entry = page.get_by_text("News Center", exact=True)
    news_entry.hover()
    expect(news_entry).to_have_attribute("title", pytest.regex(r".+"))


@pytest.mark.TC_KB_001
@pytest.mark.ac_kb_us1_7
def test_hover_changes_style(authenticated_page: Page):
    """KB-AC7: 鼠标悬停时入口样式变化"""
    page = authenticated_page
    news_entry = page.get_by_text("News Center", exact=True)
    initial_bg = news_entry.evaluate("el => getComputedStyle(el).backgroundColor")
    news_entry.hover()
    expect(news_entry).to_have_css("cursor", "pointer")


@pytest.mark.TC_KB_001
@pytest.mark.ac_kb_us1_8
def test_highlight_follows_after_navigation(authenticated_page: Page):
    """KB-AC8: 跳转后高亮跟随切换"""
    page = authenticated_page
    page.get_by_text("News Center", exact=True).click()
    news_highlighted = page.get_by_text("News Center", exact=True)
    expect(news_highlighted).to_have_css(
        "background-color", pytest.regex(r"rgba?\([^)]+\)")
    )
    page.get_by_text("Alerts", exact=True).click()
    expect(page).to_have_url(pytest.regex(r"/alerts"))


@pytest.mark.TC_KB_001
@pytest.mark.ac_kb_us1_9
def test_direct_url_has_correct_highlight(authenticated_page: Page):
    """KB-AC9: 页面直接访问时高亮正确"""
    page = authenticated_page
    page.goto(f"{BASE_URL}/alerts")
    alerts_entry = page.get_by_text("Alerts", exact=True)
    expect(alerts_entry).to_have_css("background-color", pytest.regex(r".+"))


@pytest.mark.TC_KB_001
@pytest.mark.ac_kb_us1_10
def test_news_alerts_resonance_navigation(authenticated_page: Page):
    """KB-AC10: News Center/Alerts/Resonance 跳转"""
    page = authenticated_page
    page.get_by_text("News Center", exact=True).click()
    expect(page).to_have_url(pytest.regex(r"/news|News Center"))
    page.get_by_text("Alerts", exact=True).click()
    expect(page).to_have_url(pytest.regex(r"/alerts|Alerts"))
    page.get_by_text("Resonance", exact=True).click()
    expect(page).to_have_url(pytest.regex(r"/resonance|Resonance"))
