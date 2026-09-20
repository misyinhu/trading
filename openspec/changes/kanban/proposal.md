# Kanban Epic - 多周期分析 Dashboard

## 1. 目标

构建一个多周期共振分析 Dashboard，用于信号扫描、矛盾检测、图表可视化。

## 2. 范围

**包含**:
- 多数据源行情获取 (OKX/IBKR)
- 6 个 Streamlit 分析页面
- 多周期共振分析
- 三重滤网策略
- TradingView 图表集成 (lightweight-charts)
- 警报与新闻事件中心

**不包含**:
- 实盘交易执行 (由 notify/webhook_bridge.py 处理)
- 复杂策略回测

## 3. 核心功能

| 页面 | 功能 |
|------|------|
| 新闻事件中心 | 市场新闻/事件 |
| **市场洞察** | **AI 分析调研（现象 → 结论）** |
| 警报中心 | RSI/价格异常警报 |
| 市场扫描 | 多品种快速扫描 |
| 三重滤网 | M30/M5/M1 三周期验证 |
| 多周期共振 | 共振度评分 + TradingView 图表 |
| 跨周期分析 | 多周期对比 + 矛盾检测 |

## 4. 数据源

- **OKX**: 加密货币永续 (DOGE/ETH/BTC)
- **IBKR**: 芝商所期货 (MNQ/MYM/RB/HO/MHG/MGC)
- **NASDAQ**: 股票 (AAPL/TSLA)

## 5. 成功标准

- 6 页 Streamlit 应用正常运行
- 多数据源行情获取
- 多周期共振分析
- TradingView 图表渲染
- 三重滤网扫描
- 矛盾检测

## 6. 风险

- 数据源延迟导致共振判断不准
- quant-core API 限流

---

## TDD 权威来源

**US/AC 表格已迁移至 SPEC.md**，作为 TDD 唯一权威来源。

- 详细 AC 定义: `SPEC.md` → AC Tables
- Gherkin 测试: `features/*.feature`
- 测试执行: `qa/run_daily_tests.py`
