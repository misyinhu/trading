# Kanban 设计

## 架构

```
┌──────────────────────────────────────────────────────────────────┐
│                      Kanban Streamlit App                        │
├────────────┬────────────┬────────────┬────────────┬──────────────┤
│News Center │   Alerts   │Market Scan │Three Screen│  Resonance   │
├────────────┴────────────┴────────────┴────────────┴──────────────┤
│                    Cross Timeframe                                │
├─────────────────────────────────────────────────────────────────┤
│                       src/ modules                               │
├──────────┬──────────┬──────────┬──────────┬──────────┬───────────┤
│  data.py │analysis.py│   tv.py  │three_filter│config.py│components.py
└──────────┴──────────┴──────────┴──────────┴──────────┴───────────┘
                              │
                    ┌─────────┴─────────┐
                    │   quant-core API  │
                    └─────────┬─────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
      OKX API            IBKR API           TradingView
```

## 页面详情

### 0_news_center.py - 新闻事件中心
- 抓取市场新闻
- 事件分类显示

### 1_alerts.py - 警报中心
- RSI/价格阈值监控
- 自定义警报规则

### 2_market_scan.py - 市场扫描
- 多品种快速扫描
- 支持 OKX/SSE/SZSE/IB

### 3_three_screen.py - 三重滤网
- M30 趋势判断
- M5 入场点
- M1 确认

### 4_resonance.py - 多周期共振
- 多周期方向汇总
- 共振度评分 (高≥75%, 中≥50%)
- TradingView lightweight-charts 图表
- MA20 叠加

### 5_cross_timeframe.py - 跨周期分析
- 周期对比视图
- 矛盾检测 (多周期方向冲突)

## src/ 模块

| 模块 | 功能 | 关键函数 |
|------|------|----------|
| `data.py` | 行情获取、符号映射 | `fetch_multi_timeframe()`, `load_instruments_config()` |
| `analysis.py` | RSI/MA/共振计算 | `calculate_resonance_en()`, `detect_contradictions()` |
| `tv.py` | TradingView CDP | `get_chart_targets()`, `run_tv_cmd()` |
| `three_filter.py` | 三重滤网信号 | `calculate_three_filter()` |
| `config.py` | 配置常量 | `QUANT_CORE_URL`, `TIMEFRAMES` |
| `components.py` | 可复用 UI | - |

## 配置

```yaml
# instruments.yaml
instruments:
  - symbol: "BTC-USDT-SWAP", source: "okx"
  - symbol: "MNQ", source: "ib", exchange: "CME"

# config.py
TIMEFRAMES = ["1m", "5m", "30m", "4h", "1D"]
QUANT_CORE_URL = "http://100.82.238.11:8005"
CLIENT_ID = "10"
```

## 接口

```python
# 数据获取
fetch_multi_timeframe(symbol, timeframes) -> dict
load_instruments_config() -> list
get_source_for_symbol(symbol) -> str  # okx/ib/tradingview

# 分析
calculate_resonance_en(directions) -> {score, level, distribution}
detect_contradictions(timeframe_data) -> {has_contradiction, contradictions}
calculate_rsi_local(prices, period=14) -> float
calculate_trend(ohlc_df) -> {trend, rsi}

# TradingView CDP
get_chart_targets() -> list
run_tv_cmd(cmd_args) -> dict
```