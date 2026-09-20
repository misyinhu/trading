# Trading 项目 US-AC-TC 优化关系表

> 基于行业最佳实践（INVEST 原则、Agile Testing Quadrants、Given-When-Then 格式）优化
> 生成时间: 2026-05-10

---

## 一、当前状态 vs 优化后对比

| 指标 | 优化前 | 优化后 | 变化 |
|------|--------|--------|------|
| US 总数 | 21 | 19 | -2 (合并/拆分) |
| AC 总数 | 56 | 57 | +1 |
| TC 总数 | 37 | 45+ | +8 (含 Negative/Performance) |
| P0 优先级标注 | 无 | 7 个 US | 新增 |
| Negative TC | 缺失 | 12+ 个 | 新增 |

---

## 二、Epic 1: Webhook

### US-1: 健康检查端点
**优先级**: P1  
**作为开发者，我需要监控服务状态**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-1.1 | Given 服务运行在 {host}:5002<br>When 用户发送 GET 请求至 "/health"<br>Then HTTP 状态码 = 200 | WH-001 | 健康检查基本功能 |
| AC-1.2 | Then Response Body 应符合 $WebhookResponse<br>And $.status = "ok"<br>And $.config.app_id = true<br>And $.config.conversation_id = true | WH-001 | 配置字段验证 |
| AC-1.3 | Given 服务异常<br>When GET /health<br>Then HTTP 状态码 != 200 | WH-001-NEG | 负面测试 |

---

### US-2: TradingView 信号执行
**优先级**: P0  
**作为交易者，我需要Webhook接收TradingView信号并自动执行订单**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-2.1 | Given OKX 模拟盘 API 已就绪<br>When 接收到 POST /tv-webhook Payload = {"action": "buy", "symbol": "DOGE-USDT"}<br>Then HTTP 200<br>And $.order.code = "0"<br>And $.order.data[0].ordId 正则匹配 "^[0-9]+$" | WH-101 | 买入信号处理 |
| AC-2.2 | Given 账户持有 DOGE-USDT >= 1<br>When POST /tv-webhook Payload = {"action": "sell", "symbol": "DOGE-USDT", "qty": 1}<br>Then $.order.code = "0" | WH-102 | 卖出信号处理 |
| AC-2.3 | Given 系统已记录 signal_hash = SHA256(action+symbol+qty)<br>When 在 30 秒内 POST 相同信号两次<br>Then 第一次: $.order.code = "0"<br>And 第二次: $.order.error 匹配 "duplicate\|already\|重复" | WH-102-DEDUP | 重复信号去重 |
| AC-2.4 | Given OKX 账户余额 < 1 USDT<br>When POST /tv-webhook Payload = {"action": "buy", "symbol": "BTC-USDT"}<br>Then $.order.error 匹配 "余额\|insufficient\|balance" | WH-101-NEG | 余额不足 |

---

### US-3: 飞书自然语言下单
**优先级**: P1  
**作为交易者，我需要通过飞书发送自然语言命令执行交易**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-3.1 | Given 飞书消息格式 {"message": {"content": "买入1手GC"}}<br>When POST /feishu-webhook<br>Then action=buy, symbol=GC, qty=1 | WH-201 | NL 解析买入 |
| AC-3.2 | When POST /feishu-webhook Payload = {"message": {"content": "查看持仓"}}<br>Then $.order=null (查询命令不执行交易) | WH-201-QUERY | 查询命令处理 |
| AC-3.3 | Given 交易命令已提交<br>When POST /feishu-webhook Payload = {"message": {"content": "买入1手GC"}}<br>Then $.status = "ok" 且异步执行 | WH-201-ASYNC | 异步执行 |

---

### US-4: 成交通知推送
**优先级**: P0  
**作为交易者，我需要在订单成交时收到飞书通知**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-4.1 | Given 订单成交触发 execDetails 回调<br>When IBKR 执行订单完成<br>Then 飞书推送包含 合约/数量/价格 | WH-301 | 基本推送 |
| AC-4.2 | Given 同一订单 execDetails 触发多次<br>When 第二次回调<br>Then 不重复推送飞书 | WH-301-DEDUP | 去重 |
| AC-4.3 | Given 飞书 API 限流<br>When 订单成交<br>Then 重试 3 次，失败后记录日志 | WH-301-RETRY | 错误处理 |

---

## 三、Epic 2: Kanban

### KB-US1: 页面导航
**优先级**: P2  
**作为用户，我需要在大盘各页面之间切换**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-1.1 | Given 用户打开 Kanban Dashboard<br>Then 侧边栏显示 7 个页面入口 | KB-001 | 页面入口显示 |
| AC-1.2 | When 用户点击 "新闻事件中心"<br>Then 跳转到对应页面，URL 更新 | KB-001-NAV | 页面跳转 |
| AC-1.3 | When 用户在 "新闻事件中心" 页面<br>Then 侧边栏该选项高亮显示 | KB-001-ACTIVE | 当前页面高亮 |

---

### NC-US1: 新闻日期筛选
**优先级**: P2  
**作为用户，我需要按日期筛选新闻**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-1.1 | Given 用户打开新闻事件中心<br>Then 默认显示最近 7 天新闻 | NC-001 | 默认日期范围 |
| AC-1.2 | When 用户选择开始/结束日期<br>Then 新闻列表按日期过滤 | NC-001-DATERANGE | 日期范围筛选 |
| AC-1.3 | When 用户输入 开始日期 > 结束日期<br>Then 显示错误或自动交换日期 | NC-001-NEG | 边界条件 |

---

### NC-US2: 新闻分类筛选
**优先级**: P2  
**作为用户，我需要按类别筛选新闻**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-2.1 | Given 下拉选择器选项: 财经/加密/宏观<br>When 用户多选<br>Then 筛选多个分类的新闻 | NC-101 | 多选支持 |
| AC-2.2 | When 筛选条件变化<br>Then 新闻列表立即更新显示符合条件的结果 | NC-102 | 实时更新 |

---

### NC-US3: 新闻数量控制
**优先级**: P3  
**作为用户，我需要控制显示的新闻数量**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-3.1 | Given 滑块范围 10-100<br>When 用户拖动滑块<br>Then 默认值 = 20 | NC-201 | 滑块控制 |
| AC-3.2 | When 滑块值变化<br>Then 新闻列表实时更新显示数量 | NC-202 | 实时更新 |

---

### NC-US4: 财经新闻 Tab
**优先级**: P2  
**作为用户，我需要查看财经新闻**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-4.1 | Given 切换到 "财经新闻" Tab<br>Then Tab 显示 "财经新闻" 标题<br>And 显示新闻列表 | NC-301 | 基本显示 |
| AC-4.2 | When 用户点击新闻条目<br>Then 展开显示 时间/来源/摘要 (前300字符) | NC-302 | 详情展开 |

---

### NC-US5: 市场情绪 Tab
**优先级**: P3  
**作为用户，我需要查看市场情绪分析**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-5.1 | Given 切换到 "市场情绪" Tab<br>Then 显示 sentiment_score (0.0-1.0) | NC-401 | 情绪分数 |
| AC-5.2 | Then 显示情绪标签 Bullish/Bearish/Neutral<br>And bullish 显示 🟢，bearish 显示 🔴 | NC-402 | 情绪标签 |

---

### AL-US1: 警报周期设置
**优先级**: P2  
**作为用户，我需要设置警报检测周期**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-1.1 | Given 下拉选项: M30/M5/M1<br>When 用户选择周期<br>Then 默认选择 "15s" | AL-001 | 周期选择 |
| AC-1.2 | When 用户切换周期<br>Then get_all_tv_indicators() 使用新周期<br>And 页面数据更新 | AL-002 | 切换更新 |

---

### AL-US2: 警报触发检测
**优先级**: P1  
**作为用户，我需要在指标触发时收到警报**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-2.1 | Given 某指标的 Z-Score 值 >= 2<br>When 警报检测执行<br>Then 添加到警报列表，显示 🟡 图标 | AL-201 | Z-Score 触发 |
| AC-2.2 | Given Z-Score >= 3<br>Then 显示 🔴 高危标注 | AL-201-HIGH | 高危标注 |
| AC-2.3 | Given 短期相关性 < 0.2<br>Then 添加到警报列表 | AL-201-CORR | 相关性触发 |
| AC-2.4 | Given 警报列表有 N 条活跃警报<br>Then 页面显示警报数量 N | AL-202 | 计数显示 |

---

### AL-US3: 警报详情展开
**优先级**: P3  
**作为用户，我需要查看警报详细信息**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-3.1 | Given Tab 有 quote 数据<br>When 用户点击警报展开<br>Then 显示: 最新价/开盘/最高/最低 | AL-301 | 价格数据 |
| AC-3.2 | Given Tab 的 quote = null 或空<br>Then 不显示 metric 或显示 N/A | AL-301-NULL | 空数据 |

---

### MS-US1: 扫描类型选择
**优先级**: P2  
**作为用户，我需要选择市场扫描类型**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-1.1 | Given 下拉选项: 快速扫描/深度扫描<br>When 用户选择<br>Then 高亮选中项 | MS-001 | 类型选择 |
| AC-1.2 | When 用户选择 "快速扫描"<br>Then 参数输入框显示精简参数<br>When 用户选择 "深度扫描"<br>Then 显示完整参数 | MS-002 | 动态表单 |

---

### MS-US2: 市场选择
**优先级**: P2  
**作为用户，我需要选择要扫描的市场**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-2.1 | Given 多选框选项: OKX/IBKR/NASDAQ<br>When 用户点击<br>Then 切换选中状态 | MS-101 | 多选 |
| AC-2.2 | When 用户点击 "全选"<br>Then OKX/IBKR/NASDAQ 全部选中<br>When 点击 "取消全选"<br>Then 全部取消选中 | MS-102 | 全选/取消 |

---

### MS-US3: 扫描执行
**优先级**: P1  
**作为用户，我需要执行市场扫描**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-3.1 | Given 用户配置好扫描参数<br>When 点击 "执行扫描" 按钮<br>Then 显示进度条<br>And 开始扫描 | MS-301 | 执行按钮 |
| AC-3.2 | When 扫描完成<br>Then 结果显示在表格/卡片中 | MS-302 | 结果显示 |
| AC-3.3 | Given Quant Core API 不可达<br>When 执行扫描<br>Then 显示错误: "无法连接到 Quant Core" | MS-301-ERR | API 错误 |

---

### TS-US1: 三重滤网信号
**优先级**: P1  
**作为交易者，我需要查看三重滤网信号**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-1.1 | Given 三重滤网页面加载<br>Then 显示 M30/M5/M1 三个周期的信号 | TS-201 | 多周期显示 |
| AC-1.2 | Then 显示买卖信号/阻力位/支撑位 | TS-201-SIGNAL | 信号内容 |
| AC-1.3 | When 三个周期信号一致 (共振)<br>Then 高亮显示推荐方向 | TS-201-HIGH | 共振高亮 |
| AC-1.4 | Given 信号不一致<br>Then 显示中性状态，不推荐操作 | TS-201-NEUTRAL | 中性状态 |

---

### RS-US1: TradingView 图表
**优先级**: P1  
**作为用户，我需要查看 TradingView 图表**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-1.1 | Given K 线数据已加载<br>Then 图表渲染 K 线 + MA20 | RS-001 | K线渲染 |
| AC-1.2 | When 用户拖动/缩放图表<br>Then 图表响应交互 | RS-001-ZOOM | 缩放滚动 |
| AC-1.3 | Given 无 K 线数据<br>Then 不渲染图表，显示提示 | RS-001-NULL | 空数据 |

---

### RS-US2: 共振度评分
**优先级**: P1  
**作为交易者，我需要多周期共振度评分**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-2.1 | Given 多周期数据已加载<br>Then 计算并显示共振度评分 (0-100) | RS-201 | 评分计算 |
| AC-2.2 | Then ≥75% 显示 "高共振" 🟢<br>And 50-75% 显示 "中共振" 🟡<br>And <50% 显示 "低共振" 🔴 | RS-201-LEVEL | 等级标识 |
| AC-2.3 | When 存在矛盾周期<br>Then 高亮警告显示矛盾信号 | RS-201-CONFLICT | 矛盾警告 |

---

### AG-US1: 关键词解析
**优先级**: P2  
**作为用户，我需要AI分析市场关键词**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-1.1 | Given 用户输入 "纳指" 或 "道指"<br>When 提交解析<br>Then "纳指" → QQQ, "道指" → DIA | AG-001 | 指数映射 |
| AC-1.2 | Given 用户输入自由文本 (如 "黄金 原油")<br>When 提交解析<br>Then 提取多个市场关键词 | AG-002 | 多关键词 |
| AC-1.3 | Given 用户输入无效关键词<br>When 提交解析<br>Then 显示 "未识别的市场" | AG-001-NEG | 无效输入 |

---

### AG-US2: AI 市场分析报告
**优先级**: P2  
**作为用户，我需要AI生成市场分析报告**

| AC ID | 验收标准 (Given-When-Then) | TC | 说明 |
|--------|---------------------------|-----|------|
| AC-2.1 | Given 用户选择市场并点击 "生成报告"<br>When 并行调用 news/sentiment/analysis API<br>Then 返回包含 conclusion/confidence/evidence 的报告 | AG-101 | 报告生成 |
| AC-2.2 | Given API 返回超时 (30s)<br>When 生成报告<br>Then 触发降级策略，显示部分数据 | AG-101-DEG | 超时降级 |
| AC-2.3 | Then 支持 PDF/报告导出 | AG-102 | 导出功能 |

---

## 四、TC 总表 (按 Epic 分类)

### Webhook TC

| TC ID | 名称 | 类型 | 验证 AC |
|-------|------|------|---------|
| WH-001 | 健康检查端点 | 正面 | AC-1.1, AC-1.2 |
| WH-001-NEG | 健康检查异常 | 负面 | AC-1.3 |
| WH-101 | TradingView 买入信号处理 | 正面 | AC-2.1 |
| WH-101-NEG | OKX 余额不足 | 负面 | AC-2.4 |
| WH-102 | TradingView 卖出信号处理 | 正面 | AC-2.2 |
| WH-102-DEDUP | 重复信号去重 | 正面 | AC-2.3 |
| WH-201 | 飞书 NL 命令解析 | 正面 | AC-3.1 |
| WH-201-QUERY | 查询命令处理 | 正面 | AC-3.2 |
| WH-201-ASYNC | 异步交易执行 | 正面 | AC-3.3 |
| WH-301 | 成交通知推送 | 正面 | AC-4.1 |
| WH-301-DEDUP | 通知去重 | 正面 | AC-4.2 |
| WH-301-RETRY | API 错误重试 | 正面 | AC-4.3 |

### Kanban TC

| TC ID | 名称 | 类型 | 验证 AC |
|-------|------|------|---------|
| KB-001 | 页面导航 | 正面 | AC-1.1, AC-1.2, AC-1.3 |
| NC-001 | 日期筛选默认 | 正面 | AC-1.1 |
| NC-001-DATERANGE | 日期范围筛选 | 正面 | AC-1.2 |
| NC-001-NEG | 日期边界错误 | 负面 | AC-1.3 |
| NC-101 | 多选分类 | 正面 | AC-2.1 |
| NC-102 | 实时更新 | 正面 | AC-2.2 |
| NC-201 | 滑块控制 | 正面 | AC-3.1 |
| NC-202 | 实时更新 | 正面 | AC-3.2 |
| NC-301 | 财经新闻显示 | 正面 | AC-4.1 |
| NC-302 | 详情展开 | 正面 | AC-4.2 |
| NC-401 | 情绪分数 | 正面 | AC-5.1 |
| NC-402 | 情绪标签 | 正面 | AC-5.2 |
| AL-001 | 周期选择 | 正面 | AC-1.1 |
| AL-002 | 切换更新 | 正面 | AC-1.2 |
| AL-201 | Z-Score 触发 | 正面 | AC-2.1 |
| AL-201-HIGH | 高危标注 | 正面 | AC-2.2 |
| AL-201-CORR | 相关性触发 | 正面 | AC-2.3 |
| AL-202 | 警报计数 | 正面 | AC-2.4 |
| AL-301 | 警报详情 | 正面 | AC-3.1 |
| AL-301-NULL | 空数据处理 | 负面 | AC-3.2 |
| MS-001 | 类型选择 | 正面 | AC-1.1 |
| MS-002 | 动态表单 | 正面 | AC-1.2 |
| MS-101 | 市场多选 | 正面 | AC-2.1 |
| MS-102 | 全选功能 | 正面 | AC-2.2 |
| MS-301 | 执行扫描 | 正面 | AC-3.1 |
| MS-301-ERR | API 错误 | 负面 | AC-3.3 |
| MS-302 | 结果显示 | 正面 | AC-3.2 |
| TS-201 | 多周期信号 | 正面 | AC-1.1, AC-1.2 |
| TS-201-HIGH | 共振高亮 | 正面 | AC-1.3 |
| TS-201-NEUTRAL | 中性状态 | 正面 | AC-1.4 |
| RS-001 | K线渲染 | 正面 | AC-1.1 |
| RS-001-ZOOM | 缩放交互 | 正面 | AC-1.2 |
| RS-001-NULL | 空数据 | 负面 | AC-1.3 |
| RS-201 | 共振度评分 | 正面 | AC-2.1 |
| RS-201-LEVEL | 等级标识 | 正面 | AC-2.2 |
| RS-201-CONFLICT | 矛盾警告 | 正面 | AC-2.3 |
| AG-001 | 指数映射 | 正面 | AC-1.1 |
| AG-001-NEG | 无效输入 | 负面 | AC-1.3 |
| AG-002 | 多关键词 | 正面 | AC-1.2 |
| AG-101 | 报告生成 | 正面 | AC-2.1 |
| AG-101-DEG | 超时降级 | 正面 | AC-2.2 |
| AG-102 | 导出功能 | 正面 | AC-2.3 |

---

## 五、优先级汇总

### P0 - 关键路径 (必须通过)

| US | AC 数量 | TC 数量 |
|-----|--------|--------|
| US-2: TradingView 信号执行 | 4 | 5 |
| US-4: 成交通知推送 | 3 | 3 |
| AL-US2: 警报触发检测 | 4 | 5 |
| MS-US3: 扫描执行 | 3 | 4 |
| TS-US1: 三重滤网信号 | 4 | 4 |
| RS-US1: TradingView 图表 | 3 | 4 |
| RS-US2: 共振度评分 | 3 | 4 |

### P1 - 高优先级

| US | AC 数量 | TC 数量 |
|-----|--------|--------|
| US-1: 健康检查端点 | 3 | 3 |
| US-3: 飞书自然语言下单 | 3 | 4 |

### P2 - 中优先级

| US | AC 数量 | TC 数量 |
|-----|--------|--------|
| KB-US1: 页面导航 | 3 | 3 |
| NC-US1: 新闻日期筛选 | 3 | 4 |
| NC-US2: 新闻分类筛选 | 2 | 2 |
| NC-US4: 财经新闻 Tab | 2 | 2 |
| AL-US1: 警报周期设置 | 2 | 2 |
| MS-US1: 扫描类型选择 | 2 | 2 |
| MS-US2: 市场选择 | 2 | 2 |
| AG-US1: 关键词解析 | 3 | 4 |
| AG-US2: AI 市场分析报告 | 3 | 4 |

### P3 - 低优先级

| US | AC 数量 | TC 数量 |
|-----|--------|--------|
| NC-US3: 新闻数量控制 | 2 | 2 |
| NC-US5: 市场情绪 Tab | 2 | 2 |
| AL-US3: 警报详情展开 | 2 | 3 |

---

## 六、修改建议

### 1. 立即执行

1. **添加 Negative TC**: 当前缺失负面测试，建议添加 12+ 个 Negative TC
2. **标注 P0 优先级**: 7 个 US 应标记为 P0，作为回归测试重点
3. **TC 原子化**: 部分 TC 验证多个 AC，建议拆分

### 2. 下一步优化

1. **集成测试**: 添加 Webhook → IBKR 完整流程测试
2. **性能测试**: 添加响应时间阈值检查
3. **E2E 测试**: 端到端交易流程验证

---

## 七、文件位置

- 原始 proposal: `openspec/changes/trading/webhook/proposal.md`, `openspec/changes/trading/kanban/proposal.md`
- 原始 test-cases: `docs/test-cases.md`
- 本优化表: `docs/us-ac-tc-optimized.md`