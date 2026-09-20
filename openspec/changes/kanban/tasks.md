# Kanban 任务清单

## Phase 1: 核心功能 ✅

- [x] Streamlit 多页面结构 (6 pages)
- [x] 数据获取模块 (OKX/IBKR)
- [x] RSI/MA 计算 (`analysis.py`)
- [x] 趋势检测 (`calculate_trend`)
- [x] 共振度计算 (`calculate_resonance_en`)
- [x] 矛盾检测 (`detect_contradictions`)
- [x] 三重滤网策略 (`three_filter.py`)

## Phase 2: 图表集成 ✅

- [x] lightweight-charts 集成
- [x] TradingView CDP 连接 (`tv.py`)
- [x] 多图表渲染
- [x] MA20 叠加
- [x] 实时数据格式化

## Phase 3: 数据源 ✅

- [x] OKX 加密永续合约
- [x] IBKR 芝商所期货
- [x] NASDAQ 股票
- [x] instruments.yaml 配置

## Phase 4: 优化 🔄

- [ ] 实时数据自动刷新
- [ ] 图表交互增强
- [ ] 性能优化 (大数据量)

## Phase 5: 增强 📋

- [ ] 新闻数据源接入 (0_news_center.py)
- [ ] 更多技术指标
- [ ] 警报历史记录
- [ ] 移动端适配