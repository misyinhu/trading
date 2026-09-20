# @spec: ../SPEC.md#kb-us1
# @CI: https://github.com/trading/workflows/tc-linkage.yml
# @last-updated: 2026-05-12
@US-KB-US1 @KB
Feature: Kanban 导航侧边栏

  作为用户，我需要通过侧边栏导航到各个功能页面，以便高效切换不同模块。

  Background:
    Given 用户已登录 Kanban 系统
    And 侧边栏可见

  @ac-kb-us1-1 @TC-KB-001 @happy-path
  Scenario: 侧边栏显示 6 个页面入口
    Then 侧边栏显示以下页面入口:
      | 入口名称 | 图标 |
      | News Center | 📰 |
      | Alerts | 🔔 |
      | Market Scan | 🔍 |
      | Three Screen | 📊 |
      | Resonance | 🔗 |
      | Agent | 🤖 |

  @ac-kb-us1-4 @TC-KB-001 @happy-path
  Scenario: 侧边栏显示图标和页面名称
    Then 每个入口显示图标和文字名称
    And 图标与页面名称匹配

  @ac-kb-us1-2 @TC-KB-001 @happy-path
  Scenario: 点击 News Center 跳转
    When 用户点击 "News Center" 入口
    Then 页面跳转到新闻事件中心
    And URL 包含 "/news" 或页面标题为 "News Center"

  @ac-kb-us1-2 @TC-KB-001 @happy-path
  Scenario: 点击 Alerts 跳转
    When 用户点击 "Alerts" 入口
    Then 页面跳转到警报中心
    And URL 包含 "/alerts" 或页面标题为 "Alerts"

  @ac-kb-us1-2 @TC-KB-001 @happy-path
  Scenario: 点击 Market Scan 跳转
    When 用户点击 "Market Scan" 入口
    Then 页面跳转到市场扫描页面
    And URL 包含 "/scan" 或页面标题为 "Market Scan"

  @ac-kb-us1-2 @TC-KB-001 @happy-path
  Scenario: 点击 Three Screen 跳转
    When 用户点击 "Three Screen" 入口
    Then 页面跳转到三重滤网页面
    And URL 包含 "/three-screen" 或页面标题为 "Three Screen"

  @ac-kb-us1-2 @TC-KB-001 @happy-path
  Scenario: 点击 Resonance 跳转
    When 用户点击 "Resonance" 入口
    Then 页面跳转到多周期共振页面
    And URL 包含 "/resonance" 或页面标题为 "Resonance"

  @ac-kb-us1-2 @TC-KB-001 @happy-path
  Scenario: 点击 Agent 跳转
    When 用户点击 "Agent" 入口
    Then 页面跳转到智能体页面
    And URL 包含 "/agent" 或页面标题为 "Agent"

  @ac-kb-us1-3 @TC-KB-001 @happy-path
  Scenario: 当前页面高亮显示
    Given 用户在 News Center 页面
    Then 侧边栏中 "News Center" 高亮显示
    And 高亮样式为背景色变化或下划线

  @ac-kb-us1-8 @TC-KB-001 @happy-path
  Scenario: 跳转后高亮跟随
    Given 用户在 Market Scan 页面
    When 用户点击 "Alerts"
    Then "Alerts" 高亮显示
    And "Market Scan" 不再高亮

  @ac-kb-us1-10 @TC-KB-001 @edge
  Scenario: 页面加载时高亮正确
    Given 用户直接访问 News Center URL
    When 页面加载完成
    Then 侧边栏中 "News Center" 自动高亮

  @ac-kb-us1-6 @TC-KB-001 @happy-path
  Scenario: 悬停时显示页面提示
    When 用户悬停在 "Three Screen" 入口
    Then 显示 tooltip "三重滤网分析"
    And tooltip 在鼠标移开后消失

  @ac-kb-us1-7 @TC-KB-001 @edge
  Scenario: 悬停时入口样式变化
    When 用户悬停在任意入口
    Then 入口背景色或透明度发生变化
    And 不触发页面跳转

  @ac-kb-us1-5 @TC-KB-001 @happy-path
  Scenario: 页面加载时默认展开侧边栏
    Given 用户已登录系统
    When 页面加载完成
    Then 侧边栏默认处于展开状态

  @ac-kb-us1-9 @TC-KB-001 @edge
  Scenario: 直接访问URL时高亮正确
    Given 用户直接访问 News Center URL
    When 页面加载完成
    Then 侧边栏中 "News Center" 自动高亮
    And 其他入口不高亮