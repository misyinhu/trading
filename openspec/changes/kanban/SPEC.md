# Kanban SPEC

[![CI Status](https://github.com/trading/workflows/tc-linkage.yml/badge.svg)](https://github.com/trading/actions)
[![OpenAPI Contract](https://img.shields.io/badge/OpenAPI-validated-green)](contracts/webhook_bridge.openapi.yaml)

> **双向链接**: 本文档是 TDD 唯一权威来源，与 Gherkin Feature 文件双向同步。
> - Gherkin 测试: `features/*.feature`
> - 测试执行: `qa/run_daily_tests.py`
> - UAT 签字: `docs/UAT-signoff.md`

## Scope
Multi-timeframe analysis Dashboard with 6 Streamlit pages.

## Pages
| # | 页面 | 功能 |
|---|------|------|
| 0 | 新闻事件中心 | 市场新闻抓取 |
| 1 | 警报中心 | RSI/价格异常警报 |
| 2 | 市场扫描 | 多品种快速扫描 |
| 3 | 三重滤网 | M30/M5/M1 三周期验证 |
| 4 | 多周期共振 | 共振度 + TV 图表 |
| 5 | 跨周期分析 | 周期对比 + 矛盾检测 |
| 6 | 市场洞察 | 现象 → AI 分析报告 |

## Data Sources
| Source | 品种 | 类型 |
|--------|------|------|
| OKX | DOGE/ETH/BTC | 加密永续 |
| IBKR | MNQ/MYM/RB/HO/MHG/MGC | 芝商所期货 |
| NASDAQ | AAPL/TSLA | 股票 |

## Core Analysis
- **RSI**: period=14
- **MA**: 20/60 均线
- **共振度**: 高≥75%, 中≥50%, 低<50%
- **矛盾检测**: 多周期方向冲突

## Tech Stack
- Streamlit (多页面)
- lightweight-charts (TradingView 图表)
- pandas, numpy
- quant-core API

## Config
- QUANT_CORE_URL: http://100.82.238.11:8005
- CLIENT_ID: 10
- TIMEFRAMES: 1m, 5m, 30m, 4h, 1D

---

## AC Tables (TDD 唯一权威来源)

> **双向链接规范**: 每个 US/AC 必须链接到对应的 `.feature` 文件。
> 格式: `[feature:features/{module}/{prefix}—US{n}-{suffix}.feature]`

### Navigation (KB)

| US | AC | 验收标准 | TC | Feature |
|----|----|---------|-----|---------|
| KB-US1 | AC_KB_US1_1 | 侧边栏显示 6 个页面入口 | TC-KB-001 | [KB-US1.feature](features/navigation/KB-US1.feature) |
| KB-US1 | AC_KB_US1_2 | 点击页面名称跳转到对应页面 | TC-KB-001 | |
| KB-US1 | AC_KB_US1_3 | 当前页面高亮显示 | TC-KB-001 | |
| KB-US1 | AC_KB_US1_4 | 侧边栏显示图标和页面名称 | TC-KB-001 | |
| KB-US1 | AC_KB_US1_5 | 页面加载时默认展开侧边栏 | TC-KB-001 | |
| KB-US1 | AC_KB_US1_6 | 鼠标悬停页面入口显示提示 | TC-KB-001 | |
| KB-US1 | AC_KB_US1_7 | 鼠标悬停时入口样式变化 | TC-KB-001 | |
| KB-US1 | AC_KB_US1_8 | 跳转后高亮跟随切换 | TC-KB-001 | |
| KB-US1 | AC_KB_US1_9 | 页面直接访问时高亮正确 | TC-KB-001 | |
| KB-US1 | AC_KB_US1_10 | News Center/Alerts/Resonance 跳转 | TC-KB-001 | |

### News Center (NC)

| US | AC | 验收标准 | TC | Feature |
|----|----|---------|-----|---------|
| NC-US1 | AC_NC_US1_1 | 日期选择器支持选择开始/结束日期 | TC-NC-001 | [NC-US1-5.feature](features/news/NC-US1-5.feature) |
| NC-US1 | AC_NC_US1_2 | 默认显示最近 7 天新闻 | TC-NC-001 | |
| NC-US1 | AC_NC_US1_3 | 选择日期后新闻列表更新 | TC-NC-001 | |
| NC-US2 | AC_NC_US2_4 | 下拉选择器支持 财经/加密/宏观 分类 | TC-NC-101 | (NC-US2~5 在 NC-US1-5.feature 中) |
| NC-US2 | AC_NC_US2_5 | 多选支持 | TC-NC-101 | |
| NC-US2 | AC_NC_US2_6 | 筛选后列表更新 | TC-NC-102 | |
| NC-US3 | AC_NC_US3_7 | 滑块控制显示数量 (10-100) | TC-NC-201 | |
| NC-US3 | AC_NC_US3_8 | 实时更新显示 | TC-NC-202 | |
| NC-US4 | AC_NC_US4_9 | Tab 显示 "财经新闻" 标题 | TC-NC-301 | |
| NC-US4 | AC_NC_US4_10 | 列表显示新闻标题/来源/时间 | TC-NC-302 | |
| NC-US5 | AC_NC_US4_11 | Tab 显示 "市场情绪" 标题 | TC-NC-401 | |
| NC-US5 | AC_NC_US4_12 | 显示 Reddit/社交媒体情绪数据 | TC-NC-402 | |
| NC-US4 | AC_NC_US5_13 | Tab 切换显示加载动画 | TC-NC-301 | [NC-US1-5.feature](features/news/NC-US1-5.feature) |
| NC-US4 | AC_NC_US5_14 | 新闻列表点击展开详情 | TC-NC-302 | |
| NC-US5 | AC_NC_US5_15 | 情绪数据加载状态显示 | TC-NC-402 | |
| NC-US5 | AC_NC_US5_16 | 社交媒体数据手动刷新 | TC-NC-402 | |
| NC-US5 | AC_NC_US5_17 | 无情绪数据时显示空状态 | TC-NC-402 | |

### Alerts (AL)

| US | AC | 验收标准 | TC | Feature |
|----|----|---------|-----|---------|
| AL-US1 | AC_AL_US1_1 | 下拉选择 M30/M5/M1 周期 | TC-AL-001 | [AL-US1-4.feature](features/alerts/AL-US1-4.feature) |
| AL-US1 | AC_AL_US1_2 | 切换周期后检测逻辑更新 | TC-AL-002 | |
| AL-US2 | AC_AL_US1_3 | RSI 超买/超卖时触发警报 | TC-AL-201 | (AL-US2~4 在 AL-US1-4.feature 中) |
| AL-US2 | AC_AL_US1_4 | 价格异动时触发警报 | TC-AL-201 | |
| AL-US2 | AC_AL_US1_5 | 警报列表实时更新 | TC-AL-202 | |
| AL-US3 | AC_AL_US1_6 | 点击警报展开详情 | TC-AL-301 | |
| AL-US3 | AC_AL_US1_7 | 显示触发时间/指标/阈值 | TC-AL-302 | |
| AL-US4 | AC_AL_US1_8 | 短期相关性低于阈值触发警报 | TC-AL-401 | (AL-US4 在 AL-US1-4.feature 中) |
| AL-US4 | AC_AL_US1_9 | 长期相关性变化检测 | TC-AL-401 | |
| AL-US4 | AC_AL_US1_10 | 多 Tab 相关性汇总显示 | TC-AL-402 | |
| AL-US4 | AC_AL_US1_11 | 相关性矩阵热力图可视化显示 | TC-AL-403 | |
| AL-US5 | AC_AL_US1_12 | 用户可自定义警报阈值(RSI/价格/相关性) | TC-AL-501 | |
| AL-US5 | AC_AL_US1_13 | 警报声音开关可独立控制 | TC-AL-502 | |

### Market Scan (MS)

| US | AC | 验收标准 | TC | Feature |
|----|----|---------|-----|---------|
| MS-US1 | AC_MS_US1_1 | 下拉选择 快速扫描/深度扫描 | TC-MS-001 | [MS-US1-3.feature](features/scan/MS-US1-3.feature) |
| MS-US1 | AC_MS_US1_2 | 参数输入框根据类型变化 | TC-MS-002 | |
| MS-US2 | AC_MS_US1_3 | 多选框选择 OKX/IBKR/NASDAQ | TC-MS-101 | (MS-US2~3 在 MS-US1-3.feature 中) |
| MS-US2 | AC_MS_US2_4 | 支持全选/取消全选 | TC-MS-102 | |
| MS-US3 | AC_MS_US2_5 | 点击执行按钮开始扫描 | TC-MS-301 | |
| MS-US3 | AC_MS_US2_6 | 进度条显示扫描进度 | TC-MS-301 | |
| MS-US3 | AC_MS_US3_7 | 结果显示在表格中 | TC-MS-302 | |
| MS-US1 | AC_MS_US1_8 | 深度扫描模式参数校验 | TC-MS-001 | [MS-US1-3.feature](features/scan/MS-US1-3.feature) |
| MS-US2 | AC_MS_US2_9 | 交易所连接失败时提示错误 | TC-MS-101 | |
| MS-US3 | AC_MS_US3_10 | 扫描超时（30s）处理 | TC-MS-301 | |
| MS-US3 | AC_MS_US3_11 | 用户可取消扫描 | TC-MS-301 | |
| MS-US3 | AC_MS_US3_12 | 无市场数据时提示 | TC-MS-301 | |
| MS-US3 | AC_MS_US3_13 | 结果为空时显示空状态 | TC-MS-302 | |
| MS-US3 | AC_MS_US3_14 | 表格列排序功能 | TC-MS-302 | |

### Three Screen (TS)

| US | AC | 验收标准 | TC | Feature |
|----|----|---------|-----|---------|
| TS-US1 | AC_TS_US1_1 | 显示 M30/M5/M1 三个周期信号 | TC-TS-201 | [TS-US1.feature](features/three_screen/TS-US1.feature) |
| TS-US1 | AC_TS_US1_2 | 显示买卖信号/阻力位/支撑位 | TC-TS-201 | |
| TS-US1 | AC_TS_US1_3 | 信号一致时高亮显示 | TC-TS-202 | |
| TS-US1 | AC_TS_US1_4 | 周期无信号时显示"待确认" | TC-TS-201 | |
| TS-US1 | AC_TS_US1_5 | 多周期信号冲突时提示 | TC-TS-201 | |
| TS-US1 | AC_TS_US1_6 | 三周期信号状态汇总显示 | TC-TS-202 | |
| TS-US1 | AC_TS_US1_7 | 信号最后更新时间显示 | TC-TS-202 | |

### Resonance (RS)

| US | AC | 验收标准 | TC | Feature |
|----|----|---------|-----|---------|
| RS-US1 | AC_RS_US1_1 | 图表渲染 K 线数据 | TC-RS-001 | [RS-US1-3.feature](features/resonance/RS-US1-3.feature) |
| RS-US1 | AC_RS_US1_2 | 支持缩放/滚动 | TC-RS-001 | |
| RS-US1 | AC_RS_US2_3 | 显示技术指标 | TC-RS-002 | |
| RS-US2 | AC_RS_US2_4 | 计算各周期共振得分 (0-100) | TC-RS-201 | (RS-US2~3 在 RS-US1-3.feature 中) |
| RS-US2 | AC_RS_US2_5 | 显示共振/矛盾提示 | TC-RS-201 | |
| RS-US2 | AC_RS_US2_6 | 颜色标识强度 | TC-RS-202 | |
| RS-US3 | AC_RS_US3_7 | MA20 计算正确 | TC-RS-301 | (RS-US3 在 RS-US1-3.feature 中) |
| RS-US3 | AC_RS_US3_8 | MA20 数据点数量正确 | TC-RS-301 | |
| RS-US3 | AC_RS_US3_9 | MA20 叠加显示在图表 | TC-RS-301 | |
| RS-US3 | AC_RS_US3_10 | 默认使用 MA20 (周期 20) | TC-RS-302 | |
| RS-US3 | AC_RS_US3_11 | 用户可修改 MA 周期 | TC-RS-302 | |
| RS-US3 | AC_RS_US3_12 | 周期修改后重新渲染 | TC-RS-302 | |
| RS-US1 | AC_RS_US1_13 | 无 K 线数据时显示空状态 | TC-RS-001 | [RS-US1-3.feature](features/resonance/RS-US1-3.feature) |
| RS-US2 | AC_RS_US2_14 | 多周期方向冲突时显示警告 | TC-RS-201 | |
| RS-US3 | AC_RS_US3_15 | MA20 数据点数量验证 (N-19) | TC-RS-301 | |
| RS-US3 | AC_RS_US3_16 | 用户自定义 MA 周期生效 | TC-RS-302 | |
| RS-US3 | AC_RS_US3_17 | MA 周期修改后图表更新 | TC-RS-302 | |
| RS-US1 | AC_RS_US1_18 | 指标线颜色正确显示 | TC-RS-002 | |

### Agent (AG)

| US | AC | 验收标准 | TC | Feature |
|----|----|---------|-----|---------|
| AG-US1 | AC_AG_US1_1 | 输入关键词 (如 "黄金", "BTC") | TC-AG-001 | [AG-US1-3.feature](features/agent/AG-US1-3.feature) |
| AG-US1 | AC_AG_US1_2 | 解析为市场代码 (INDEX_MAP) | TC-AG-001 | |
| AG-US1 | AC_AG_US1_3 | 显示解析结果 | TC-AG-002 | |
| AG-US2 | AC_AG_US2_4 | 调用外部 AI 生成分析 | TC-AG-101 | (AG-US2~3 在 AG-US1-3.feature 中) |
| AG-US2 | AC_AG_US2_5 | 显示结论/置信度/证据 | TC-AG-101 | |
| AG-US2 | AC_AG_US2_6 | 支持 PDF/报告导出 | TC-AG-101 | |
| AG-US1 | AC_AG_US1_7 | 无法识别关键词时显示错误提示并使用默认标的 | TC-AG-002 | |
| AG-US2 | AC_AG_US2_8 | 所有数据源返回空时显示降级提示 | TC-AG-101 | |
| AG-US2 | AC_AG_US2_9 | AI API 超时(30秒)时显示超时错误并提供重试 | TC-AG-101 | |
| AG-US2 | AC_AG_US2_10 | PDF 导出失败时显示错误提示 | TC-AG-102 | |
| AG-US3 | AC_AG_US3_11 | 支持查询历史分析报告 | TC-AG-201 | |
| AG-US3 | AC_AG_US3_12 | 历史报告列表支持分页显示 | TC-AG-201 | |
| AG-US3 | AC_AG_US3_13 | 无历史记录时显示空状态提示 | TC-AG-202 | |
| AG-US3 | AC_AG_US3_14 | 支持按时间范围筛选历史记录 | TC-AG-202 | |

### Cross-Timeframe (CT)

| US | AC | 验收标准 | TC | Feature |
|----|----|---------|-----|---------|
| CT-US1 | AC_CT_US1_1 | 多周期 Z-Score 共振检测 | TC-CT-001 | [CT-US1.feature](features/cross_timeframe/CT-US1.feature) |
| CT-US1 | AC_CT_US1_2 | 相关性破裂检测 | TC-CT-001 | |
| CT-US1 | AC_CT_US1_3 | 矛盾信号识别 | TC-CT-001 | |
| CT-US1 | AC_CT_US1_4 | 强烈入场信号识别 | TC-CT-002 | |
| CT-US1 | AC_CT_US1_5 | 买入信号判断 | TC-CT-002 | |
| CT-US1 | AC_CT_US1_6 | 卖出信号判断 | TC-CT-002 | |
| CT-US1 | AC_CT_US1_7 | 无信号时显示中性 | TC-CT-002 |