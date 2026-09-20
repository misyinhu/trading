# 测试用例（自动化友好格式）

> 本文件采用 Gherkin 格式，支持 QA 手工执行或 DEV 转换为自动化测试。
> **格式**：Given-When-Then，明确 Pre-conditions 和 Schema 断言
> **来源**：proposal.md + design.md + tasks.md

---

## 全局 Schema 字典（Contract Repository）

所有 TC 引用的标准对象定义于此。重复字段不再在各 TC 中定义。

### 1. OrderObject（OKX 下单响应）

```json
{
  "code": "string (0=成功, 非0=失败)",
  "msg": "string (错误描述，成功时为空)",
  "data": [
    {
      "ordId": "string (订单唯一ID，正整数)",
      "clOrdId": "string (客户端自定义ID，可选)"
    }
  ]
}
```

**Schema 引用**: `$OrderObject`  
**验证规则**:
- `$.code == "0"` 表示成功
- `$.data[0].ordId` 正则匹配 `^[0-9]+$`

---

### 2. SignalPayload（Webhook 输入）

```json
{
  "action": "enum['buy', 'sell', 'close']",
  "symbol": "string (如 'BTC-USDT', 'GC')",
  "qty": "number (>0)",
  "order_type": "string (default: 'market')"
}
```

**Schema 引用**: `$SignalPayload`  
**验证规则**:
- `$.action` 枚举值: buy/sell/close
- `$.symbol` 非空字符串
- `$.qty` > 0

---

### 3. WebhookResponse（/tv-webhook 标准响应）

```json
{
  "status": "string (ok/error)",
  "order": "$OrderObject | {error: string}",
  "config": {
    "app_id": "boolean",
    "conversation_id": "boolean",
    "query_only": "boolean"
  }
}
```

**Schema 引用**: `$WebhookResponse`  
**验证规则**:
- `$.status` == "ok" 或 "error"
- 如果 `$.status == "ok"`，则 `$.order` 符合 `$OrderObject`
- 如果 `$.status == "error"`，则 `$.order.error` 为非空字符串

---

### 4. FinancialNewsItem（新闻条目）

```json
{
  "title": "string",
  "summary": "string (可选)",
  "published": "string (ISO8601 日期)",
  "source": "string",
  "url": "string (可选)"
}
```

**Schema 引用**: `$FinancialNewsItem`

---

### 5. SentimentPost（情绪帖子）

```json
{
  "title": "string",
  "author": "string",
  "upvotes": "number",
  "subreddit": "string",
  "sentiment": "enum['bullish', 'bearish', 'neutral']",
  "sentiment_score": "number (0.0-1.0)"
}
```

**Schema 引用**: `$SentimentPost`

---

### 6. MarketAnalysisReport（市场分析报告）

```json
{
  "conclusion": "string (原因推断)",
  "confidence": "number (0.0-1.0)",
  "evidence": {
    "news": ["string (新闻标题)"],
    "sentiment": "string (情绪摘要)",
    "technical": "string (技术面摘要)"
  },
  "related_links": ["string (URL)"]
}
```

**Schema 引用**: `$MarketAnalysisReport`

---

## 一、Webhook 服务

### WH-001: 健康检查端点

**Epic**: Webhook
**验证AC**: US-1 - 健康检查端点

```gherkin
Scenario: 健康检查返回正常状态
  Given 服务运行在 {host}:5002
  When 用户发送 GET 请求至 "/health"
  Then HTTP 状态码 = 200
  And Response Body 应符合 $WebhookResponse
  And $.status = "ok"
  And $.config.app_id = true
  And $.config.conversation_id = true
```

---

### WH-101: TradingView 买入信号处理

**Epic**: Webhook
**验证AC**: US-2 - TradingView 信号执行

**Pre-conditions**:
- OKX 模拟盘账户余额 ≥ 10 USDT
- OKX API Key 有效（未过期/未吊销）
- 网络代理已配置（127.0.0.1:7890）
- `config/okx.yaml` flag="sim"

```gherkin
Scenario: TV webhook 处理买入信号 (WH-101)
  Given OKX 模拟盘 API 已就绪
  And 账户持有 >= 10 USDT
  When 接收到 POST 请求至 "/tv-webhook"
  And Headers: Content-Type: application/json
  And Payload 应符合 $SignalPayload
  And Payload = {"action": "buy", "symbol": "DOGE-USDT", "exchange": "OKX", "qty": 1, "order_type": "market"}
  Then HTTP 状态码 = 200
  And Response Body 应符合 $WebhookResponse
  And $.status = "ok"
  And $.order.code = "0"
  And $.order.data[0].ordId 正则匹配 "^[0-9]+$"

Scenario: OKX 下单失败（余额不足）
  Given OKX 账户余额 < 1 USDT
  When POST "/tv-webhook" Payload = {"action": "buy", "symbol": "BTC-USDT", "qty": 1}
  Then HTTP 200
  And Response Body 应符合 $WebhookResponse
  And $.order.error 匹配 "余额|insufficient|balance"

Scenario: OKX API Key 无效
  Given config/okx.yaml 使用过期/吊销的 API Key
  When POST "/tv-webhook" Payload = {"action": "buy", "symbol": "BTC-USDT", "qty": 1}
  Then HTTP 200
  And $.order.error 匹配 "401|APIKey|invalid|environment"

Negative Testing:
  When POST "/tv-webhook" Payload 为非 JSON 格式
  Then HTTP 状态码 >= 400

  When POST "/tv-webhook" Payload 缺少 action 字段
  Then $.status = "error"

  When POST "/tv-webhook" Payload qty = 0
  Then $.status = "error"
```

---

### WH-102: TradingView 卖出信号处理

**Epic**: Webhook
**验证AC**: US-2 - TradingView 信号执行

```gherkin
Scenario: TV webhook 处理卖出信号
  Given 持有 DOGE-USDT >= 1
  When POST "/tv-webhook" Payload = {"action": "sell", "symbol": "DOGE-USDT", "qty": 1}
  Then HTTP 200
  And Response Body 应符合 $WebhookResponse
  And $.order.code = "0"

Scenario: 卖出但无持仓
  Given 账户不持有 DOGE-USDT
  When POST "/tv-webhook" Payload = {"action": "sell", "symbol": "DOGE-USDT", "qty": 1}
  Then HTTP 200
  And $.order.error 匹配 "余额不足|insufficient"

Scenario: 重复信号去重
  Given 系统已记录 signal_hash = SHA256(action+symbol+qty)
  When 在 30 秒内 POST 相同信号两次
  Then 第一次: $.order.code = "0"
  And 第二次: $.order.error 匹配 "duplicate|already|重复" 或 $.order.code = "0" 但实际未下单
```

---

### WH-201: 飞书命令解析

**Epic**: Webhook
**验证AC**: US-3 - 飞书自然语言下单

```gherkin
Scenario: 解析"买入1手GC"
  Given 飞书 Webhook 服务运行
  When POST "/feishu-webhook" Payload = {"message": {"content": "买入1手GC"}}
  Then NL 解析结果:
    - action = "buy"
    - symbol = "GC"
    - quantity = 1
    - sec_type = "FUT"

Scenario: 解析"卖空2手NQ"
  When POST "/feishu-webhook" Payload = {"message": {"content": "卖空2手NQ"}}
  Then 解析结果: action="sell", symbol="NQ", quantity=2

Scenario: 解析"平仓GC"
  When POST "/feishu-webhook" Payload = {"message": {"content": "平仓GC"}}
  Then 解析结果: action="close", symbol="GC"

Scenario: 解析"查看持仓"
  When POST "/feishu-webhook" Payload = {"message": {"content": "查看持仓"}}
  Then 解析结果: action="query"
```

---

### WH-301: 成交通知

**Epic**: Webhook
**验证AC**: US-4 - 成交通知推送

```gherkin
Scenario: 订单成交后发送飞书通知
  Given 订单已提交且配置了 execDetails 回调
  When 订单成交（fill event）
  Then 飞书收到 HTTP POST 请求
  And 请求体包含: symbol, direction(买入/卖出), quantity, price

Scenario: exec_id 去重
  Given 同一 exec_id 触发两次回调
  When 第二次回调到达
  Then 飞书收到通知 <= 1 次（去重生效）

Scenario: 通知格式验证
  Given 飞书收到成交通知
  Then 通知包含字段: contract(合约名), side(方向), size(数量), price(价格)
```

---

## 二、Kanban 导航

### KB-001 ~ KB-008: 页面切换

**Epic**: Kanban
**验证AC**: KB-US1 - 页面导航

```gherkin
Scenario: 侧边栏显示所有页面
  Given 用户已登录 Kanban APP
  When 页面加载完成
  Then 侧边栏显示页面链接:
    - 新闻事件中心 (0_news_center.py)
    - 警报中心 (1_alerts.py)
    - 市场扫描 (2_market_scan.py)
    - 三重滤网 (3_three_screen.py)
    - 多周期共振 (4_resonance.py)
    - 跨周期分析 (5_cross_timeframe.py)
    - 市场分析 (6_market_agent.py)
  And 每个链接可点击跳转

Scenario: 点击页面链接后 URL 正确
  Given 用户在 Kanban 主页面
  When 点击 "新闻事件中心"
  Then URL 包含 /0_news_center.py 或等效路由
  And 页面内容为新闻事件中心

# KB-003 到 KB-008 同理
```

---

## 三、新闻事件中心（0_news_center.py）

### NC-001: 日期筛选

**Epic**: Kanban - News Center
**验证AC**: NC-US1 - 新闻日期筛选

```gherkin
Scenario: 默认日期为今天
  When 用户打开新闻事件中心页面
  Then 开始日期 input 默认 = 今天 (date.today())
  And 结束日期 input 默认 = 今天

Scenario: 日期范围筛选
  Given 有 2024-01-01 至 2024-01-31 的新闻数据
  When 用户设置开始日期 = 2024-01-15，结束日期 = 2024-01-20
  Then 仅显示 2024-01-15 <= published <= 2024-01-20 的新闻

Negative Testing:
  When 开始日期 > 结束日期
  Then 显示错误提示 OR 自动交换日期

  When 日期格式无效
  Then 显示错误提示
```

---

### NC-101: 分类筛选

**Epic**: Kanban - News Center
**验证AC**: NC-US2 - 新闻分类筛选

```gherkin
Scenario: 选择"全部"分类
  When 用户选择分类 = "all"
  Then 调用 tv_financial_news(category="all")
  And 显示所有分类新闻

Scenario: 选择"加密货币"分类
  When 用户选择分类 = "crypto"
  Then 调用 tv_financial_news(category="crypto")
  And 仅显示加密货币新闻

Scenario: 选择"股票"分类
  When 用户选择分类 = "stocks"
  Then 调用 tv_financial_news(category="stocks")
```

---

### NC-102: 分类筛选后列表更新

**Epic**: Kanban - News Center
**验证AC**: NC-US2 - 新闻分类筛选

```gherkin
Scenario: 选择分类后列表立即更新
  When 用户选择分类 = "crypto"
  Then 调用 tv_financial_news(category="crypto")
  And 列表刷新显示新结果

Scenario: 多选分类时组合过滤
  When 用户同时选择 "crypto" 和 "stocks"
  Then 调用 tv_financial_news(category="crypto,stocks")
  And 列表显示两个分类的新闻
```

---

### NC-201: 新闻数量滑块

**Epic**: Kanban - News Center
**验证AC**: NC-US3 - 新闻数量控制

```gherkin
Scenario: 滑块范围 5-30
  Given 滑块配置 min=5, max=30, default=10
  When 用户设置滑块值 = 5
  Then 调用 tv_financial_news(limit=5)

  When 设置滑块值 = 30
  Then 调用 tv_financial_news(limit=30)

Negative Testing:
  When 输入值 < 5（如 0 或 -1）
  Then 使用最小值 5 或显示错误

  When 输入值 > 30（如 999）
  Then 使用最大值 30 或显示错误
```

---

### NC-202: 新闻数量实时更新

**Epic**: Kanban - News Center
**验证AC**: NC-US3 - 新闻数量控制

```gherkin
Scenario: 拖动滑块时实时更新新闻数量
  Given 财经新闻列表已显示（当前 limit=10）
  When 用户拖动滑块到 20
  Then 调用 tv_financial_news(limit=20)
  And 列表更新为 20 条新闻

Scenario: 点击确认或失焦后触发更新
  When 用户输入数字 25 并离开输入框
  Then 调用 tv_financial_news(limit=25)
  And 列表刷新显示 25 条
```

---

### NC-301: 财经新闻 Tab

**Epic**: Kanban - News Center
**验证AC**: NC-US4 - 财经新闻 Tab

```gherkin
Scenario: 新闻加载显示
  When 用户切换到"财经新闻" Tab
  Then 显示 spinner "加载财经新闻..."
  And spinner 消失后显示新闻列表
  And 每条新闻标题截断至 80 字符

Scenario: 点击新闻展开详情
  Given 新闻列表已显示
  When 用户点击某条新闻的 expander
  Then 展开内容包含:
    - published (ISO8601，前16字符显示)
    - source (来源)
    - summary (前300字符或 title)

Scenario: 无新闻数据
  Given tv_financial_news 返回空 items 或 error
  Then 显示 "暂无新闻数据"
```

---

### NC-302: 新闻列表字段显示

**Epic**: Kanban - News Center
**验证AC**: NC-US4 - 财经新闻 Tab

```gherkin
Scenario: 新闻列表显示标题/来源/时间
  When 新闻列表加载完成
  Then 每条新闻显示:
    - 标题（截断80字符，超出显示...）
    - 来源（source 字段）
    - 发布时间（published 前16字符，格式 YYYY-MM-DD HH:mm）

Scenario: 时间显示格式
  Given published = "2025-05-10T14:30:00Z"
  Then 显示 "2025-05-10 14:30"
```

---

### NC-401: 市场情绪 Tab

**Epic**: Kanban - News Center
**验证AC**: NC-US5 - 市场情绪 Tab

```gherkin
Scenario: 默认 Symbol 根据分类
  Given category = "crypto"
  When 切换到"市场情绪" Tab
  Then Symbol input 默认值 = "BTC"

  Given category = "stocks"
  Then 默认值 = "AAPL"

Scenario: 自定义 Symbol 查询
  When 用户输入 "ETH" 并提交
  Then 调用 tv_market_sentiment(symbol="ETH", category="all")
  And 显示 ETH 的情绪数据

Scenario: 情绪分数显示
  Given tv_market_sentiment 返回数据
  Then 显示:
    - sentiment_label: "Bullish" / "Bearish" / "Neutral"
    - sentiment_score: 0.00-1.00
    - posts_analyzed: 已分析帖子数

Scenario: 帖子列表格式
  Then 每个 top_post 包含字段:
    - title
    - author
    - upvotes (数值)
    - subreddit
    - sentiment (bullish 显示 🟢，bearish 显示 🔴)
```

---

### NC-402: Reddit/社交媒体情绪数据

**Epic**: Kanban - News Center
**验证AC**: NC-US5 - 市场情绪 Tab

```gherkin
Scenario: 显示 Reddit/社交媒体情绪
  Given 用户在"市场情绪" Tab
  Then 调用 tv_market_sentiment 获取情绪数据
  And 显示情绪分数和标签

Scenario: 情绪数据来源显示
  Given tv_market_sentiment 返回 posts
  Then 显示来源包括 Reddit/subreddit 数据
  And 每个 post 显示 upvote 和评论数

Scenario: 社交媒体情绪图标
  Given sentiment = "Bullish"
  Then 显示 🟢 图标
  Given sentiment = "Bearish"
  Then 显示 🔴 图标
```

---

## 四、警报中心（1_alerts.py）

### AL-001: 周期选择与连接检测

**Epic**: Kanban - Alert Center
**验证AC**: AL-US1 - 警报周期设置

```gherkin
Scenario: 默认周期为 15s
  When 页面加载
  Then 默认选择 "15s" 周期
  And 调用 get_all_tv_indicators(timeframe="15s")

Scenario: 切换周期
  When 用户选择 "1m"
  Then 调用 get_all_tv_indicators(timeframe="1m")
  And 页面数据更新为 1m 周期

Scenario: 所有周期选项可用
  Then 可选周期: 1m, 5m, 15s, 30m, 3h

Scenario: TV 连接失败
  Given TV CDP 不可达 (TV_HOST:TV_PORT)
  When 页面加载
  Then 显示警告: "无法连接到 TradingView CDP"
  And 不继续加载后续数据

Scenario: 无布局提示
  Given TradingView 未打开任何图表布局
  When 页面加载
  Then 显示警告: "⚠️ 未扫描到任何图表，请在 TradingView 中打开布局"
```

---

### AL-002: 切换周期后检测逻辑更新

**Epic**: Kanban - Alert Center
**验证AC**: AL-US1 - 警报周期设置

```gherkin
Scenario: 周期切换后重新获取指标
  When 用户切换周期从 "15s" 到 "1m"
  Then 调用 get_all_tv_indicators(timeframe="1m")
  And 警报列表根据新周期数据重新计算

Scenario: 周期切换保持选择状态
  Given 用户已选择特定 Tab
  When 切换周期
  Then 保持相同 Tab 不变
  And 数据刷新为新周期
```

---

### AL-201: 警报检测逻辑

**Epic**: Kanban - Alert Center
**验证AC**: AL-US2 - 警报触发检测

```gherkin
Scenario: Z-Score >= 2 触发警报
  Given 某指标的 Z-Score 值 = 2.5
  When 警报检测执行
  Then 添加到警报列表
  And 显示 🟡 图标

Scenario: Z-Score >= 3 高危标注
  Given Z-Score = 3.5
  Then 显示 🔴 图标

Scenario: 短期相关性 < 0.2
  Given 短期相关性 = 0.15
  Then 添加到警报列表

Scenario: 警报计数显示
  Given 有 N 条活跃警报
  Then 页面显示警报数量 N
```

---

### AL-202: 警报列表实时更新

**Epic**: Kanban - Alert Center
**验证AC**: AL-US2 - 警报触发检测

```gherkin
Scenario: 新警报自动添加到列表
  When Z-Score 触发阈值 (>=2)
  Then 新警报出现在列表顶部
  And 警报计数 +1

Scenario: 警报列表自动刷新
  Given 警报中心页面打开
  When 指标数据更新
  Then 警报列表自动刷新
  And 显示最新警报状态
```

---

### AL-301: 指标详情展开

**Epic**: Kanban - Alert Center
**验证AC**: AL-US3 - 警报详情展开

```gherkin
Scenario: Tab expander 显示价格数据
  Given Tab 有 quote 数据
  When 用户点击 Tab expander
  Then 显示 4 个 metric:
    - 最新价 (close, 2位小数)
    - 开盘 (open)
    - 最高 (high)
    - 最低 (low)

Scenario: 无 quote 数据
  Given Tab 的 quote = null 或空
  Then 不显示 metric 或显示 N/A
```

---

### AL-302: 警报详情显示触发时间和阈值

**Epic**: Kanban - Alert Center
**验证AC**: AL-US3 - 警报详情展开

```gherkin
Scenario: 警报详情显示完整信息
  When 用户展开某条警报
  Then 显示:
    - 触发时间 (timestamp)
    - 指标名称 (study_name)
    - 当前阈值 (Z-Score 或相关性值)

Scenario: Z-Score 警报详情
  Given Z-Score = 2.8
  When 展开警报
  Then 显示: Z-Score 达到 2.8

Scenario: 相关性警报详情
  Given 短期相关性 = 0.25
  When 展开警报
  Then 显示: 短期相关性 0.25
```

---

### AL-402: 多 Tab 相关性汇总

**Epic**: Kanban - Alert Center
**验证AC**: AL-US4 - 相关性警报检测

```gherkin
Scenario: 汇总所有 Tab 相关性
  Given 多个 Tab (N个)
  When 警报检测执行
  Then 汇总每个 Tab 的短期/长期相关性

Scenario: 显示相关性异常 Tab
  Given 某 Tab 短期相关性 < 0.3
  Then 该 Tab 标记为异常
  And 警报列表高亮显示

Scenario: 相关性趋势显示
  Given 某 Tab 相关性从 0.8 降至 0.2
  Then 显示下降趋势图标
  And 警报详情显示变化幅度
```

---

## 五、市场扫描（2_market_scan.py）

### MS-001: 扫描类型与参数

**Epic**: Kanban - Market Scan
**验证AC**: MS-US1 - 扫描类型选择

```gherkin
Scenario: 显示 5 种扫描类型
  Then 扫描类型选项:
    - volume_breakout: 交易量突破
    - bollinger: 布林带分析
    - trending: 趋势分析
    - consecutive: 连续K线
    - multi_changes: 多周期变化

Scenario: 选择类型显示对应参数
  When 选择 "交易量突破"
  Then 显示参数: timeframe(select), volume_multiplier(1.5-5.0), price_change_min(1.0-10.0), limit(5-50)

  When 选择 "布林带分析"
  Then 显示参数: timeframe, bb_period(10-30), bb_std(1.5-3.0), limit
```

---

### MS-002: 扫描参数动态表单

**Epic**: Kanban - Market Scan
**验证AC**: MS-US1 - 扫描类型选择

```gherkin
Scenario: 选择交易量突破时显示放量倍数参数
  When 选择 "交易量突破"
  Then 显示 volume_multiplier 输入框（范围 1.5-5.0，默认 2.0）

Scenario: 选择布林带时显示周期和标准差参数
  When 选择 "布林带分析"
  Then 显示 bb_period 输入框（范围 10-30，默认 20）
  And 显示 bb_std 输入框（范围 1.5-3.0，默认 2.0）

Scenario: 切换类型后清空其他类型的参数值
  When 选择 "交易量突破" 并设置 volume_multiplier=3.0
  And 切换为 "布林带分析"
  Then volume_multiplier 值已清除
  And 显示布林带参数
```

---

### MS-101: 市场选择

**Epic**: Kanban - Market Scan
**验证AC**: MS-US2 - 市场选择

```gherkin
Scenario: 常用品种开关
  When 用户勾选 "常用品种"
  Then 使用 get_common_symbols() 返回的品种列表

  When 取消勾选
  Then 不使用常用品种

Scenario: 交易所多选
  When 勾选 "OKX (加密)"
  Then 参数 exchanges 包含 "okx"

  When 同时勾选 "OKX" 和 "上交所 (A股)"
  Then exchanges = ["okx", "sse"]
```

---

### MS-102: 全选/取消全选

**Epic**: Kanban - Market Scan
**验证AC**: MS-US2 - 市场选择

```gherkin
Scenario: 点击全选按钮
  Given 交易所列表包含 OKX/IBKR/NASDAQ/SSE/SZSE
  When 点击 "全选"
  Then 所有交易所复选框均被勾选

Scenario: 点击取消全选按钮
  Given 所有交易所已被勾选
  When 点击 "取消全选"
  Then 所有交易所复选框均未被勾选

Scenario: 部分选择后点击全选
  Given 只勾选了 OKX
  When 点击 "全选"
  Then 全部 5 个交易所复选框均被勾选
```

---

### MS-301: 扫描执行

**Epic**: Kanban - Market Scan
**验证AC**: MS-US3 - 扫描执行

```gherkin
Scenario: 点击开始扫描
  Given 参数已配置（类型、交易所等）
  When 点击 "🚀 开始扫描"
  Then 显示 spinner "扫描中..."
  And 调用 POST /api/scan/{scanner_type}
  Then spinner 消失
  And 显示扫描结果（表格或卡片）

Scenario: 扫描无结果
  Given 没有满足条件的标的
  Then 显示 "暂无满足条件的结果"

Scenario: Quant Core 不可用
  Given QUANT_CORE_URL 不可达
  Then 显示连接错误信息
```

---

### MS-302: 扫描结果表格显示

**Epic**: Kanban - Market Scan
**验证AC**: MS-US3 - 扫描执行

```gherkin
Scenario: 扫描成功后显示结果表格
  When 扫描完成
  Then 显示结果表格包含列: 标的 | 当前价格 | 变化幅度 | 扫描时间

Scenario: 结果按变化幅度降序排列
  When 扫描结果显示
  Then 结果行按变化幅度从大到小排序

Scenario: 点击结果行打开详情
  Given 扫描结果显示
  When 点击某一行
  Then 打开该标的的详情页面或弹窗
```

---

## 六、三重滤网（3_three_screen.py）

### TS-201: 扫描与信号显示

**Epic**: Kanban - Three Screen
**验证AC**: TS-US1 - 三重滤网信号

```gherkin
Scenario: 点击开始扫描
  Given 参数已配置
  When 点击 "🚀 开始扫描"
  Then 调用 POST /api/scan/three-screen
  And 显示 spinner

Scenario: 三重向上买入信号
  Given M30 趋势向上 AND M5 向上 AND M1 确认向上
  Then 显示:
    - 信号文字包含 "做多"
    - 图标为 📈
    - color 变量已定义（非 undefined，P0 修复验证）

Scenario: 三重向下卖出信号
  Given M30 向下 AND M5 向下 AND M1 确认向下
  Then 显示:
    - 信号文字包含 "做空"
    - 图标为 📉

Scenario: 无共振信号
  Then 不显示做多/做空信号
  Or 显示中性状态
```

---

### TS-202: 信号一致时高亮

**Epic**: Kanban - Three Screen
**验证AC**: TS-US1 - 三重滤网信号

```gherkin
Scenario: 三周期信号一致（全部做多）
  Given M30=向上 AND M5=向上 AND M1=确认向上
  Then 高亮显示该信号行（背景色 #00FF00 或类似）
  And 信号图标为 📈

Scenario: 三周期信号一致（全部做空）
  Given M30=向下 AND M5=向下 AND M1=确认向下
  Then 高亮显示该信号行（背景色 #FF0000 或类似）
  And 信号图标为 📉

Scenario: 信号不一致时不高亮
  Given M30=向上 AND M5=向下
  Then 不高亮显示
  And 显示中性信号（🟡）
```

---

## 七、多周期共振（4_resonance.py）

### RS-001: 图表渲染

**Epic**: Kanban - Resonance
**验证AC**: RS-US1 - TradingView 图表

```gherkin
Scenario: 有数据时显示图表
  Given TradingView CDP 连接正常
  And 有历史数据
  Then 显示 lightweight-charts
  And 图表包含 MA20 线条

Scenario: 无数据不显示图表
  Given 无历史数据
  Then 不渲染图表区域
```

---

### RS-002: 显示技术指标

**Epic**: Kanban - Resonance
**验证AC**: RS-US1 - TradingView 图表

```gherkin
Scenario: 图表加载后显示 MA20 指标
  Given 图表已渲染
  Then 显示 MA20 指标线（颜色 #2196F3）

Scenario: 指标线位于 K 线上方
  Given 当前价格 > MA20
  Then MA20 线在价格下方

Scenario: 缩放时指标同步
  When 用户缩放图表
  Then MA20 指标同步更新
```

---

### RS-201: 共振度计算与显示

**Epic**: Kanban - Resonance
**验证AC**: RS-US2 - 共振度评分

```gherkin
Scenario: 高共振 >= 75%
  Given 共振度 = 0.8
  Then 显示 "高共振" 标签

Scenario: 中共振 50%-75%
  Given 共振度 = 0.6
  Then 显示 "中共振" 标签

Scenario: 低共振 < 50%
  Given 共振度 = 0.3
  Then 显示 "低共振" 标签

Scenario: 矛盾检测
  Given 多周期方向冲突
  Then 显示矛盾警告
  And 展开详情显示冲突周期
```

---

### RS-202: 颜色标识共振强度

**Epic**: Kanban - Resonance
**验证AC**: RS-US2 - 共振度评分

```gherkin
Scenario: 高共振（>=75%）显示绿色
  Given 共振度 >= 75%
  Then 该行背景显示浅绿色 (#00FF001A)
  And 标签文字为绿色

Scenario: 中共振（50%-75%）显示黄色
  Given 共振度 50%-75%
  Then 该行背景显示浅黄色 (#FFFF001A)
  And 标签文字为深黄色

Scenario: 低共振（<50%）显示红色
  Given 共振度 < 50%
  Then 该行背景显示浅红色 (#FF00001A)
  And 标签文字为红色

Scenario: 无共振数据显示灰色
  Given 无法计算共振度
  Then 该行背景显示浅灰色 (#8080801A)
  And 标签文字为灰色
```

---

## 八、跨周期分析（5_cross_timeframe.py）

### MI-001: 并行数据采集

**Epic**: Kanban - Market Insight
**验证AC**: MI-US1 - 并行数据采集

```gherkin
Scenario: 同时获取新闻/情绪/技术面数据
  Given 用户请求市场洞察
  When 并行调用开始
  Then 同时触发:
    - tv_financial_news (category, limit)
    - tv_market_sentiment (symbol, category, limit)
    - tv_combined_analysis (symbol, exchange, timeframe)
  And 等待所有响应完成

Scenario: 显示加载状态
  Given 并行数据采集中
  Then 显示 spinner "正在获取多市场数据..."
  And 三个数据源各自显示加载指示器

Scenario: 数据汇总展示
  Given 三个数据源全部返回
  Then 在同一页面展示:
    - 新闻列表
    - 情绪数据
    - 技术分析结果
```

---

### MI-002: 数据源失败不影响整体

**Epic**: Kanban - Market Insight
**验证AC**: MI-US1 - 并行数据采集

```gherkin
Scenario: 单个数据源失败时其他正常显示
  Given tv_financial_news 调用失败
  When 并行调用完成
  Then 显示可用数据（情绪+技术面）
  And 显示警告 "部分数据暂时不可用"

Scenario: 所有数据源失败
  Given 所有并行调用均失败
  Then 显示错误信息 "无法获取市场数据，请稍后重试"
  And 不显示空数据列表

Scenario: 超时处理
  Given 单个数据源 10 秒内未响应
  Then 认为该数据源超时
  And 继续等待其他数据源
  And 显示超时数据源的占位符
```

---

### SC-001: 交易所多选

**Epic**: Kanban - Scanner Config
**验证AC**: SC-US1 - 交易所多选

```gherkin
Scenario: 多选框支持 OKX/IBKR/NASDAQ/SSE/SZSE
  Given 页面加载
  Then 显示 5 个交易所复选框:
    - OKX (加密)
    - IBKR (期货)
    - NASDAQ (美股)
    - SSE (上交所)
    - SZSE (深交所)

Scenario: 至少选择一个交易所
  When 用户取消所有选择
  Then 显示错误 "请至少选择一个交易所"
  And 禁用扫描按钮

Scenario: 多选组合
  When 用户勾选 OKX 和 NASDAQ
  Then 参数 exchanges = ["okx", "nasdaq"]
```

---

### SC-002: 常用品种快捷选项

**Epic**: Kanban - Scanner Config
**验证AC**: SC-US1 - 交易所多选

```gherkin
Scenario: 点击常用品种快速填充
  Given 交易所已选择
  When 用户点击 "常用品种" 按钮
  Then 自动勾选该交易所的常用标的:
    - OKX: BTC, ETH, SOL
    - NASDAQ: QQQ, SPY
    - SSE: 600000, 600519

Scenario: 清除常用品种
  When 用户点击 "清除" 按钮
  Then 取消所有标的勾选
  And 保留交易所选择
```

---

### SC-101: 交易量突破参数

**Epic**: Kanban - Scanner Config
**验证AC**: SC-US2 - 扫描类型参数

```gherkin
Scenario: volume_breakout 类型参数
  When 用户选择扫描类型 = "volume_breakout"
  Then 显示参数输入框:
    - volume_multiplier: 数字输入 (范围 1.5-5.0，默认 2.0)
    - price_change_min: 数字输入 (范围 1.0-10.0，默认 3.0)
    - limit: 数字输入 (范围 5-50，默认 20)
```

---

### SC-102: 趋势分析参数

**Epic**: Kanban - Scanner Config
**验证AC**: SC-US2 - 扫描类型参数

```gherkin
Scenario: trending 类型参数
  When 用户选择扫描类型 = "trending"
  Then 显示参数输入框:
    - ma_period: 数字输入 (范围 5-200，默认 20)
    - price_change_min: 数字输入 (范围 1.0-10.0，默认 3.0)
    - limit: 数字输入 (范围 5-50，默认 20)
```

---

### SC-103: 连续K线参数

**Epic**: Kanban - Scanner Config
**验证AC**: SC-US2 - 扫描类型参数

```gherkin
Scenario: consecutive 类型参数
  When 用户选择扫描类型 = "consecutive"
  Then 显示参数输入框:
    - consecutive_count: 数字输入 (范围 3-20，默认 5)
    - change_min_pct: 数字输入 (范围 0.5-5.0，默认 1.0)
    - limit: 数字输入 (范围 5-50，默认 20)
```

---

### SC-104: 多周期变化参数

**Epic**: Kanban - Scanner Config
**验证AC**: SC-US2 - 扫描类型参数

```gherkin
Scenario: multi_changes 类型参数
  When 用户选择扫描类型 = "multi_changes"
  Then 显示参数输入框:
    - periods: 多选 (M5/M15/M30/H1/H4/D1)
    - change_threshold: 数字输入 (范围 1.0-20.0，默认 5.0)
    - limit: 数字输入 (范围 5-50，默认 20)
```

---

## 九、跨周期分析（5_cross_timeframe.py）

### CT-001: 矛盾检测逻辑

**Epic**: Kanban - Cross Timeframe
**验证AC**: CT-US1 - 跨周期矛盾检测

```gherkin
Scenario: 多周期 Z-Score 共振检测
  Given 多周期 timeframe_data
  When evaluate_signal 执行
  Then 收集所有周期的 Z-Score 值
  And 计算 avg_zscore = sum(z_scores) / count

Scenario: 相关性破裂检测
  Given 短期相关性 < 0.3
  When 检测执行
  Then has_corr_break = True
  And 添加 "相关性破裂" 到 reasons

Scenario: 信号评分 >= 2 且 Z-Score <= -3
  Given signal_score >= 2
  And zscore_red = all(abs(z) >= 3)
  And has_corr_red = all(c < -0.5)
  Then action = "🔥 强烈入场"

Scenario: 买入信号判断
  Given avg_zscore < 0 且 signal_score >= 2
  Then action = "🟢 买入"

Scenario: 卖出信号判断
  Given avg_zscore > 0 且 signal_score >= 2
  Then action = "🔴 卖出"
```

---

### CT-002: 矛盾评分计算

**Epic**: Kanban - Cross Timeframe
**验证AC**: CT-US1 - 矛盾信号评分计算

```gherkin
Scenario: 共振得分计算
  Given directions = ["up", "up", "down", "up", "neutral"]
  When calculate_resonance_en(directions) 执行
  Then score = (max(up_count, down_count) / total) * 100

Scenario: 全上涨高分
  Given directions 全为 "up"
  Then score >= 70
  And level = "高"

Scenario: 全下跌高分
  Given directions 全为 "down"
  Then score >= 70
  And level = "高"

Scenario: 矛盾检测
  Given up_tfs 包含短周期 (1m/5m)
  And down_tfs 包含长周期 (30m/1h)
  Then has_contradiction = True
  And contradictions 包含矛盾描述
```

---

## 九、市场分析 Agent（6_market_agent.py）

### AG-201: INDEX_MAP 关键词映射

**Epic**: Kanban - Agent
**验证AC**: AG-US3 - INDEX_MAP 关键词映射

```gherkin
Scenario: 映射"纳指"到 QQQ
  Given 用户输入包含 "纳指"
  When parse_targets 执行
  Then 返回 [("QQQ", "NASDAQ")]

Scenario: 映射"道指"到 DIA
  Given 用户输入包含 "道指" 或 "dow" 或 "dia"
  Then 返回 [("DIA", "NYSE")]

Scenario: 映射"标普"到 SPY
  Given 用户输入包含 "标普" 或 "spy" 或 "s&p"
  Then 返回 [("SPY", "NYSE")]

Scenario: 多关键词同时映射
  Given 用户输入 "纳指和道指劈差"
  When parse_targets 执行
  Then 返回 [("QQQ", "NASDAQ"), ("DIA", "NYSE")]

Scenario: 无匹配时默认 QQQ
  Given 用户输入不包含已知关键词
  When parse_targets 执行
  Then 返回 [("QQQ", "NASDAQ")] 作为默认
```

---

### AG-202: 并行数据采集

**Epic**: Kanban - Agent
**验证AC**: MI-US1 - 并行数据采集

```gherkin
Scenario: 并行调用三个数据源
  Given user_text = "纳指涨道指跌"
  When collect_data 执行
  Then 同时调用:
    - financial_news(symbol=None, category="all", limit=5)
    - market_sentiment(symbol="QQQ", category="all", limit=5)
    - combined_analysis(symbol="QQQ", exchange="NASDAQ", timeframe="1D")

Scenario: 搜索状态显示
  When collect_data 执行
  Then 显示 spinner "🔍 并行搜索中..."

Scenario: 单个数据源失败不影响整体
  Given market_sentiment 调用失败
  When collect_data 执行
  Then 返回结果仍包含 news 和 analysis
  And sentiment 字段为空或降级数据
```

---

## 十、多周期共振（4_resonance.py）

### RS-301: MA20 指标计算

**Epic**: Kanban - Resonance
**验证AC**: RS-US3 - MA20 指标计算

```gherkin
Scenario: MA20 计算
  Given chart_data 包含至少 20 条 K 线
  When 计算 MA20
  Then ma20_data 包含正确的平均值
  And 每条数据点 time 与 chart_data 对应

Scenario: MA20 数据点数量
  Given len(chart_data) = N
  When 计算 MA20 (period=20)
  Then len(ma20_data) = N - 19

Scenario: MA20 叠加显示
  Given ma20_data 已计算
  Then lineSeries.setData(ma20_data)
  And 图表上显示橙色线条
```

---

### RS-302: 支持自定义周期

**Epic**: Kanban - Resonance
**验证AC**: RS-US3 - MA20 指标计算

```gherkin
Scenario: 默认使用 MA20
  Given 页面加载
  Then 默认计算 MA20（周期 20）

Scenario: 用户修改 MA 周期
  When 用户输入周期 = 50
  Then 重新计算 MA50
  And 更新图表上的指标线

Scenario: 周期修改后重新渲染
  Given 用户修改了 MA 周期
  When 图表数据更新
  Then 使用新的周期计算均线
  And 线颜色保持橙色
```

---

## 十一、警报中心（1_alerts.py）

### AL-401: 相关性警报检测

**Epic**: Kanban - Alert Center
**验证AC**: AL-US4 - 相关性警报检测

```gherkin
Scenario: 短期相关性 < 0.3 触发警报
  Given 短期相关性值 = 0.25
  When 警报检测
  Then 添加到警报列表
  And level = "🟡"

Scenario: 长期相关性变化检测
  Given 长期相关性 = 0.35
  When 警报检测
  Then 检测是否有显著变化

Scenario: 多 Tab 相关性汇总
  Given 多个 Tab 都有相关性数据
  When 警报检测
  Then 汇总所有 Tab 的相关性
  And 显示相关性异常 Tab 列表
```

---

## 十二、P0 回归测试

### AG-001: 关键词解析（INDEX_MAP）

**Epic**: Kanban - Agent
**验证AC**: AG-US1 - 关键词解析

```gherkin
Scenario: 解析"纳指"
  Given 用户输入包含 "纳指"
  Then 映射: "纳指" -> symbol="QQQ", exchange="NASDAQ"

Scenario: 解析"道指"
  Then 映射: "道指" -> symbol="DIA", exchange="NYSE"

Scenario: 解析"标普500"
  Then 映射: "标普500" -> symbol="SPY", exchange="NYSE"

Scenario: 解析"油价"
  Then 映射: "油价" -> 相关大宗商品标的

Scenario: 自由文本多关键词
  Given 用户输入: "纳指和道指劈差，可能跟伊朗战争/油价有关"
  Then 提取关键词: ["纳指", "道指", "油价", "伊朗"]
  And 搜索 QQQ, DIA, 原油相关标的
```

---

### AG-101: 并行搜索与报告生成

**Epic**: Kanban - Agent
**验证AC**: AG-US2 - AI 市场分析报告

```gherkin
Scenario: 搜索状态显示
  Given 用户输入市场现象
  When 点击 "🔍 分析" 按钮
  Then 显示 spinner "🔍 分析中..."

Scenario: 并行调用 tv-mcp
  Then 同时调用:
    - tv_financial_news (category, limit)
    - tv_market_sentiment (symbol, category, limit)
    - tv_combined_analysis (symbol, exchange, timeframe)
  And 等待所有完成

Scenario: MiniMax API 调用
  Given 数据汇总完成
  Then 调用 POST https://api.minimax.chat/v1/chat/completions
  And 请求体包含:
    - model: "MiniMax-M2.1"
    - messages: system prompt + user input
    - reasoning: {"type": "disabled"}

Scenario: 报告格式
  Then 返回 MarketAnalysisReport 结构:
    - conclusion: 原因推断 (string)
    - confidence: 置信度 (0.0-1.0)
    - evidence.news: [新闻标题数组]
    - evidence.sentiment: 情绪摘要
    - evidence.technical: 技术面摘要
    - related_links: [URL数组]

Scenario: 无数据降级
  Given 所有 tv-mcp 返回空
  Then 显示 "暂无数据，请尝试其他关键词"

Scenario: API 超时
  Given 30秒内未返回
  Then 显示错误信息
  Or 重试机制触发
```

---

### AG-002: 显示解析结果

**Epic**: Kanban - Agent
**验证AC**: AG-US1 - 关键词解析

```gherkin
Scenario: 解析完成后显示标的映射
  Given 用户输入 "纳指"
  When 解析完成
  Then 显示: "纳指 → QQQ (NASDAQ)"

Scenario: 多关键词解析结果
  Given 用户输入 "纳指和道指"
  When 解析完成
  Then 显示两个映射结果:
    - "纳指 → QQQ (NASDAQ)"
    - "道指 → DIA (NYSE)"

Scenario: 无法识别时提示
  Given 用户输入 "未知关键词XYZ"
  When 解析完成且无匹配
  Then 显示 "未找到匹配标的，使用默认 QQQ"
  And 使用 QQQ 作为默认 symbol
```

---

### AG-102: 支持 PDF/报告导出

**Epic**: Kanban - Agent
**验证AC**: AG-US2 - AI 市场分析报告

```gherkin
Scenario: 导出报告按钮可见
  Given 分析报告已生成
  Then 显示 "导出报告" 按钮

Scenario: 点击导出生成 PDF
  When 用户点击 "导出报告"
  Then 生成 PDF 文件包含:
    - 标题: 市场分析报告
    - 内容: conclusion, confidence, evidence
    - 时间戳

Scenario: 报告文件名
  Then 文件名格式: "market_analysis_YYYYMMDD_HHMMSS.pdf"
```

---

## 十、P0 回归测试

### P0-001 ~ P0-004: 静态分析（自动化检查）

**类型**: 技术验证（非功能测试，无需用户故事关联）

```gherkin
Scenario: P0-001 color 变量已定义（静态检查）
  When 运行 ruff check kanban/pages/3_three_screen.py
  Then 无 NameError 关于 "color"
  And python -m py_compile kanban/pages/3_three_screen.py 成功

Scenario: P0-002 get_z120_status 已移除（静态检查）
  When grep "get_z120_status" notify/webhook_bridge.py
  Then 无匹配结果

Scenario: P0-003 无重复字典键（静态检查）
  When python -c "import ast; ast.parse(open('src/nl_parser.py').read())"
  Then 无 SyntaxWarning

Scenario: P0-004 OKX 下单成功（行为测试）
  Given config/okx.yaml flag="sim"
  And 账户有足够余额
  When POST /tv-webhook Payload = {"action": "buy", "symbol": "DOGE-USDT", "qty": 1}
  Then HTTP 200
  And $.order.code = "0"
  And $.order.data[0].ordId 正则匹配 "^[0-9]+$"
```

---

## 十一、代码质量（自动化检查）

```gherkin
Scenario: Ruff 检查通过
  When 运行 ruff check .
  Then 退出码 = 0
  And 无 ERROR 输出

Scenario: Ruff format 无需修改
  When 运行 ruff format --check .
  Then 退出码 = 0

Scenario: 所有 .py 文件语法正确
  When 运行 python -m py_compile 对所有 .py 文件
  Then 无 SyntaxError
```

---

## 附录：Schema 验证工具推荐

| 工具 | 用途 |
|------|------|
| `jq` | 命令行 JSON 验证 |
| `jsonschema` (Python) | 自动化测试中的 Schema 断言 |
| `chakram` / `supertest` | API 测试 + Schema 验证 |

**示例命令**:
```bash
# jq 验证 OrderObject
curl -s POST /tv-webhook | jq '.order | if .code == "0" then .data[0].ordId | test("^[0-9]+$") else empty end'

# jsonschema 验证
python -c "import jsonschema; jsonschema.validate(instance, schema='$OrderObject')"
```

---

## PMO 治理框架参考

| 文档 | 位置 |
|------|------|
| QA 角色手册 | ../../../../pmo/docs/role-qa.md |
| 测试报告模板 | ../../../../pmo/docs/test-report-template.md |
| verified-facts.md | ./verified-facts.md |
