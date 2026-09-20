# @spec: ../SPEC.md#al-us1-4
# @CI: https://github.com/trading/workflows/tc-linkage.yml
# @last-updated: 2025-05-11
@US-AL-US1 @AL
Feature: 警报周期设置

  作为用户，我需要设置警报检测周期，以便在不同时间粒度上监控市场状态。

  Background:
    Given 用户已登录 Kanban 系统
    And 在警报中心页面
    And TradingView CDP 连接正常

  @ac-al-us1-1 @TC-AL-001 @happy-path
  Scenario Outline: 警报周期选择
    When 用户从下拉框选择周期 "<timeframe>"
    Then 调用 get_all_tv_indicators(timeframe="<timeframe>")
    And 页面数据更新为对应周期

    Examples:
      | timeframe |
      | M30       |
      | M15       |
      | M5        |
      | M1        |

  @ac-al-us1-2 @TC-AL-002 @edge
  Scenario: 切换周期后检测逻辑更新
    Given 当前选择周期为 "M15"
    When 用户切换周期为 "M1"
    Then 使用 M1 周期重新获取指标数据
    And 警报列表清空并重新加载

  @ac-al-us1-1 @TC-AL-001 @edge
  Scenario: 不支持的周期显示错误
    When 用户尝试选择不支持的周期 "1D"
    Then 显示错误提示 "该周期暂不支持"
    And 保持当前周期不变

---

@US-AL-US2 @AL
Feature: 警报触发检测

  作为用户，我需要在指标触发时收到警报，以便及时响应市场变化。

  Background:
    Given 用户已登录 Kanban 系统
    And 在警报中心页面
    And TradingView CDP 连接正常

  @ac-al-us1-3 @TC-AL-201 @happy-path
  Scenario: RSI 超买时触发警报
    Given RSI 指标值 > 70
    When 指标数据更新
    Then 创建警报条目
    And 警报类型标记为 "RSI_OVERSOLD"
    And 显示红色上箭头图标

  @ac-al-us1-3 @TC-AL-201 @happy-path
  Scenario: RSI 超卖时触发警报
    Given RSI 指标值 < 30
    When 指标数据更新
    Then 创建警报条目
    And 警报类型标记为 "RSI_OVERBROUGHT"
    And 显示绿色下箭头图标

  @ac-al-us1-4 @TC-AL-201 @edge
  Scenario: 价格异动触发警报
    Given 价格变化 > 2% 在设置的时间窗口内
    When 指标数据更新
    Then 创建警报条目
    And 警报类型标记为 "PRICE_MOVE"

  @ac-al-us1-5 @TC-AL-202 @happy-path
  Scenario: 警报列表实时更新
    Given 警报列表已显示
    When 新警报触发
    Then 列表顶部显示新警报
    And 显示新警报数量角标

---

@US-AL-US3 @AL
Feature: 警报详情展开

  作为用户，我需要查看警报详细信息，以便分析触发原因。

  Background:
    Given 用户已登录 Kanban 系统
    And 在警报中心页面
    And 警报列表有至少一条警报

  @ac-al-us1-6 @TC-AL-301 @happy-path
  Scenario: 点击警报展开详情
    When 用户点击警报条目
    Then 展开详情区域
    And 显示触发时间、指标类型、当前值

  @ac-al-us1-7 @TC-AL-302 @happy-path
  Scenario: 警报详情显示触发时间和阈值
    Given 警报已展开
    Then 显示:
      | 字段 | 格式 |
      | 触发时间 | YYYY-MM-DD HH:mm:ss |
      | 指标名称 | RSI / Price |
      | 阈值 | 如 70 |
      | 当前值 | 如 75 |
      | 变化幅度 | 如 +5% |

  @ac-al-us1-1 @TC-AL-301 @edge
  Scenario: 收起已展开的警报
    Given 警报详情已展开
    When 用户再次点击
    Then 收起详情区域

---

@US-AL-US4 @AL
Feature: 相关性警报检测

  作为用户，我需要在相关性异常时收到警报，以便发现跨市场关联。

  Background:
    Given 用户已登录 Kanban 系统
    And 在警报中心页面
    And 已订阅多个标的的相关性监控

  @ac-al-us1-8 @TC-AL-401 @happy-path
  Scenario: 短期相关性低于阈值触发警报
    Given 短期相关性（默认 5 分钟）< 0.3
    When 定时检测执行
    Then 创建警报条目
    And 警报类型标记为 "CORR_LOW"

  @ac-al-us1-9 @TC-AL-401 @edge
  Scenario: 长期相关性变化检测
    Given 长期相关性（默认 1 小时）变化 > 20%
    When 定时检测执行
    Then 创建警报条目
    And 显示相关性变化幅度

  @ac-al-us1-10 @TC-AL-402 @happy-path
  Scenario: 多 Tab 相关性汇总显示
    Given 用户在相关性 Tab 页面
    Then 显示所有监控标的的相关性矩阵
    And 低相关性标的对高亮显示

---

@US-AL-US5 @AL
Feature: 警报自定义设置

  作为用户，我需要自定义警报参数，以便根据个人交易策略调整警报行为。

  Background:
    Given 用户已登录 Kanban 系统
    And 在警报中心页面

  @ac-al-us1-11 @TC-AL-403 @happy-path
  Scenario: 相关性矩阵热力图可视化显示
    Given 用户在相关性 Tab 页面
    When 页面加载相关性数据
    Then 显示热力图矩阵
    And 颜色渐变从蓝色（低）到红色（高）
    And 单元格显示相关系数值

  @ac-al-us1-12 @TC-AL-501 @happy-path
  Scenario: 用户自定义警报阈值
    Given 用户点击警报设置图标
    When 用户设置 RSI 超买阈值 = 80
    And 用户设置 RSI 超卖阈值 = 20
    And 用户设置价格变化阈值 = 3%
    And 用户设置相关性阈值 = 0.5
    And 保存设置
    Then 警报按新阈值触发
    And 设置持久化到本地存储

  @ac-al-us1-13 @TC-AL-502 @happy-path
  Scenario: 警报声音开关独立控制
    Given 警报列表有多种类型警报
    When 用户关闭 RSI 警报的声音
    Then RSI 警报触发时无声音
    And 其他类型警报声音保持不变
    When 用户开启价格警报的声音
    Then 价格警报触发时有声音
