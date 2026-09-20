# Trading AC Coverage Status

| AC Code | Module | US | Scenario | Status | Test Function | Last Verified |
|---------|--------|-----|----------|--------|---------------|---------------|
| al-us1-1 | alerts | US1 | 警报周期选择 | ✅ Done | test_alert_cycle_selection | 2026-05-13 |
| al-us1-2 | alerts | US1 | 切换周期后检测逻辑更新 | ✅ Done | test_cycle_switch_updates_data | 2026-05-13 |
| al-us1-3 | alerts | US1 | 警报触发条件判断 | ✅ Done | test_alert_trigger_* | 2026-05-13 |
| al-us1-4 | alerts | US1 | 警报列表实时更新 | ✅ Done | test_alert_list_realtime | 2026-05-13 |
| al-us1-5 | alerts | US1 | 警报详情展示 | ✅ Done | test_alert_detail_* | 2026-05-13 |
| al-us1-6 | alerts | US1 | RSI/MA20 阈值可配置 | ✅ Done | test_alert_thresholds_* | 2026-05-13 |
| al-us1-7 | alerts | US1 | 多指标相关性警报 | ✅ Done | test_correlation_alert | 2026-05-13 |
| al-us1-8 | alerts | US1 | 警报声音控制 | ✅ Done | test_alert_sound_control | 2026-05-13 |
| al-us1-9 | alerts | US1 | 相关性汇总 | ✅ Done | test_correlation_summary | 2026-05-13 |
| al-us1-10 | alerts | US1 | Z-score 共振检测 | ✅ Done | test_zscore_resonance_detection | 2026-05-13 |
| al-us1-11 | alerts | US1 | 相关性突破检测 | ✅ Done | test_correlation_break_detection | 2026-05-13 |
| al-us1-12 | alerts | US1 | 信号评分计算 | ✅ Done | test_signal_score_calculation | 2026-05-13 |
| al-us1-13 | alerts | US1 | 警报阈值 | ✅ Done | test_alert_thresholds | 2026-05-13 |
| ag-us1-1 | agent | US1 | 自然语言命令解析 | ✅ Done | test_nl_command_parser | 2026-05-13 |
| ag-us1-2 | agent | US1 | 通知去重 | ✅ Done | test_notification_dedup | 2026-05-13 |
| ag-us1-3 | agent | US1 | 健康端点 | ✅ Done | test_health_endpoint | 2026-05-13 |
| ag-us1-7 | agent | US1 | TV Webhook | ✅ Done | test_tv_webhook | 2026-05-13 |
| ag-us2-4 | agent | US2 | 关键词解析 | ✅ Done | test_keyword_parsing | 2026-05-13 |
| ag-us2-5 | agent | US2 | 解析结果展示 | ✅ Done | test_parse_result_display | 2026-05-13 |
| ag-us2-6 | agent | US2 | 默认回退 | ✅ Done | test_default_fallback | 2026-05-13 |
| ag-us2-8 | agent | US2 | 索引映射 | ✅ Done | test_index_map_mapping | 2026-05-13 |
| ag-us2-9 | agent | US2 | 解析结果处理 | ✅ Done | (covered by keyword parsing tests) | 2026-05-13 |
| ag-us2-10 | agent | US2 | 指令执行 | ✅ Done | (covered by agent tests) | 2026-05-13 |
| ag-us3-11 | agent | US3 | AI 报告生成 | ✅ Done | test_ai_report_generation | 2026-05-13 |
| ag-us3-12 | agent | US3 | PDF 导出 | ✅ Done | test_pdf_export | 2026-05-13 |
| ag-us3-13 | agent | US3 | 报告展示 | ✅ Done | (covered by AI report tests) | 2026-05-13 |
| ag-us3-14 | agent | US3 | 报告分享 | ✅ Done | (covered by AI report tests) | 2026-05-13 |
| ct-us1-1 | cross_timeframe | US1 | 多周期图表展示 | ✅ Done | test_multi_timeframe_chart | 2026-05-13 |
| ct-us1-2 | cross_timeframe | US1 | 周期切换逻辑 | ✅ Done | test_period_switch_logic | 2026-05-13 |
| ct-us1-3 | cross_timeframe | US1 | 指标同步更新 | ✅ Done | test_indicator_sync | 2026-05-13 |
| ct-us1-4 | cross_timeframe | US1 | 跨周期信号综合 | ✅ Done | test_cross_period_signal | 2026-05-13 |
| ct-us1-5 | cross_timeframe | US1 | 多周期数据缓存 | ✅ Done | test_data_cache | 2026-05-13 |
| ct-us1-6 | cross_timeframe | US1 | 图表渲染性能 | ✅ Done | test_chart_render_perf | 2026-05-13 |
| ct-us1-7 | cross_timeframe | US1 | 图表缩放/平移 | ✅ Done | test_chart_zoom_pan | 2026-05-13 |
| ts-us1-1 | three_screen | US1 | 三屏信号展示 | ✅ Done | test_three_screen_signal_display | 2026-05-13 |
| ts-us1-2 | three_screen | US1 | 信号高亮 | ✅ Done | test_signal_highlighting | 2026-05-13 |
| ts-us1-3 | three_screen | US1 | 多指标支持 | ✅ Done | test_multi_indicator_support | 2026-05-13 |
| ts-us1-4 | three_screen | US1 | 信号历史记录 | ✅ Done | test_signal_history | 2026-05-13 |
| ts-us1-5 | three_screen | US1 | 信号筛选 | ✅ Done | test_signal_filter | 2026-05-13 |
| ts-us1-6 | three_screen | US1 | 信号导出 | ✅ Done | test_signal_export | 2026-05-13 |
| ts-us1-7 | three_screen | US1 | 信号阈值配置 | ✅ Done | test_signal_threshold_config | 2026-05-13 |
| rs-us1-1 | resonance | US1 | 共振评分展示 | ✅ Done | test_resonance_score_display | 2026-05-13 |
| rs-us1-2 | resonance | US1 | 共振颜色编码 | ✅ Done | test_resonance_color_coding | 2026-05-13 |
| rs-us1-13 | resonance | US1 | MA20 计算 | ✅ Done | test_ma20_calculation | 2026-05-13 |
| rs-us1-18 | resonance | US1 | MA20 展示 | ✅ Done | test_ma20_display | 2026-05-13 |
| rs-us2-3 | resonance | US2 | 自定义周期 | ✅ Done | test_custom_period | 2026-05-13 |
| rs-us2-4 | resonance | US2 | 指标颜色 | ✅ Done | test_indicator_colors | 2026-05-13 |
| rs-us2-5 | resonance | US2 | RSI 计算 | ✅ Done | test_rsi_calculation | 2026-05-13 |
| rs-us2-6 | resonance | US2 | RSI 展示 | ✅ Done | test_rsi_display | 2026-05-13 |
| rs-us2-14 | resonance | US2 | RSI 阈值 | ✅ Done | test_rsi_threshold | 2026-05-13 |
| rs-us3-7 | resonance | US3 | 信号评分 | ✅ Done | test_signal_score | 2026-05-13 |
| rs-us3-8 | resonance | US3 | 评分趋势 | ✅ Done | test_score_trend | 2026-05-13 |
| rs-us3-9 | resonance | US3 | 共振确认 | ✅ Done | test_resonance_confirm | 2026-05-13 |
| rs-us3-10 | resonance | US3 | 共振强度 | ✅ Done | test_resonance_strength | 2026-05-13 |
| rs-us3-11 | resonance | US3 | 共振时间窗口 | ✅ Done | test_resonance_window | 2026-05-13 |
| rs-us3-12 | resonance | US3 | 共振警报 | ✅ Done | test_resonance_alert | 2026-05-13 |
| rs-us3-15 | resonance | US3 | 共振历史 | ✅ Done | test_resonance_history | 2026-05-13 |
| rs-us3-16 | resonance | US3 | 共振报告 | ✅ Done | test_resonance_report | 2026-05-13 |
| rs-us3-17 | resonance | US3 | 共振优化建议 | ✅ Done | test_resonance_optimization | 2026-05-13 |
| ms-us1-1 | market_scan | US1 | 扫描类型展示 | ✅ Done | test_scan_type_display | 2026-05-13 |
| ms-us1-2 | market_scan | US1 | 扫描类型参数 | ✅ Done | test_scan_type_params | 2026-05-13 |
| ms-us1-3 | market_scan | US1 | 市场选择 | ✅ Done | test_market_selection | 2026-05-13 |
| ms-us1-8 | market_scan | US1 | 全选/取消全选 | ✅ Done | test_select_all_deselect | 2026-05-13 |
| ms-us2-4 | market_scan | US2 | 扫描执行 | ✅ Done | test_scan_execution | 2026-05-13 |
| ms-us2-5 | market_scan | US2 | 扫描结果展示 | ✅ Done | test_scan_result_display | 2026-05-13 |
| ms-us2-6 | market_scan | US2 | 空扫描结果 | ✅ Done | test_empty_scan_result | 2026-05-13 |
| ms-us2-9 | market_scan | US2 | 扫描历史 | ✅ Done | test_scan_history | 2026-05-13 |
| ms-us3-7 | market_scan | US3 | 扫描结果导出 | ✅ Done | test_scan_export | 2026-05-13 |
| ms-us3-10 | market_scan | US3 | 扫描优化 | ✅ Done | test_scan_optimization | 2026-05-13 |
| ms-us3-11 | market_scan | US3 | 扫描调度 | ✅ Done | test_scan_schedule | 2026-05-13 |
| ms-us3-12 | market_scan | US3 | 扫描通知 | ✅ Done | test_scan_notification | 2026-05-13 |
| ms-us3-13 | market_scan | US3 | 扫描报告 | ✅ Done | test_scan_report | 2026-05-13 |
| ms-us3-14 | market_scan | US3 | 扫描分析 | ✅ Done | test_scan_analysis | 2026-05-13 |
| ms-us3-15 | market_scan | US3 | 扫描API | ✅ Done | test_scan_api | 2026-05-13 |
| nc-us1-1 | news_center | US1 | 新闻日期筛选 | ✅ Done | test_news_date_filter | 2026-05-13 |
| nc-us1-2 | news_center | US1 | 新闻分类筛选 | ✅ Done | test_news_category_filter | 2026-05-13 |
| nc-us1-3 | news_center | US1 | 新闻数量控制 | ✅ Done | test_news_count_control | 2026-05-13 |
| nc-us2-4 | news_center | US2 | 财经新闻标签 | ✅ Done | test_finance_news_tab | 2026-05-13 |
| nc-us2-5 | news_center | US2 | 市场情绪标签 | ✅ Done | test_market_sentiment_tab | 2026-05-13 |
| nc-us2-6 | news_center | US2 | 新闻详情 | ✅ Done | test_news_detail | 2026-05-13 |
| nc-us3-7 | news_center | US3 | 新闻图表渲染 | ✅ Done | test_chart_rendering | 2026-05-13 |
| nc-us3-8 | news_center | US3 | 技术指标 | ✅ Done | test_technical_indicators | 2026-05-13 |
| nc-us4-9 | news_center | US4 | 新闻列表 | ✅ Done | test_news_list | 2026-05-13 |
| nc-us4-10 | news_center | US4 | 新闻搜索 | ✅ Done | test_news_search | 2026-05-13 |
| nc-us4-11 | news_center | US4 | 新闻收藏 | ✅ Done | test_news_favorite | 2026-05-13 |
| nc-us4-12 | news_center | US4 | 新闻分享 | ✅ Done | test_news_share | 2026-05-13 |
| nc-us5-13 | news_center | US5 | 新闻通知 | ✅ Done | test_news_notification | 2026-05-13 |
| nc-us5-14 | news_center | US5 | 通知设置 | ✅ Done | test_notification_settings | 2026-05-13 |
| nc-us5-15 | news_center | US5 | 通知历史 | ✅ Done | test_notification_history | 2026-05-13 |
| nc-us5-16 | news_center | US5 | 通知筛选 | ✅ Done | test_notification_filter | 2026-05-13 |
| nc-us5-17 | news_center | US5 | 通知导出 | ✅ Done | test_notification_export | 2026-05-13 |
| wh-us1-1 | webhook | US1 | Webhook 注册 | ✅ Done | test_webhook_register | 2026-05-13 |
| wh-us1-2 | webhook | US1 | Webhook 触发 | ✅ Done | test_webhook_trigger | 2026-05-13 |
| wh-us1-3 | webhook | US1 | Webhook 验证 | ✅ Done | test_webhook_verify | 2026-05-13 |
| wh-us1-4 | webhook | US1 | Webhook 重试 | ✅ Done | test_webhook_retry | 2026-05-13 |
| wh-us1-5 | webhook | US1 | Webhook 日志 | ✅ Done | test_webhook_log | 2026-05-13 |
| wh-us1-6 | webhook | US1 | Webhook 统计 | ✅ Done | test_webhook_stats | 2026-05-13 |
| wh-us1-7 | webhook | US1 | Webhook 过滤 | ✅ Done | test_webhook_filter | 2026-05-13 |
| wh-us1-8 | webhook | US1 | Webhook 排序 | ✅ Done | test_webhook_sort | 2026-05-13 |
| wh-us1-9 | webhook | US1 | Webhook 搜索 | ✅ Done | test_webhook_search | 2026-05-13 |
| wh-us1-10 | webhook | US1 | Webhook 编辑 | ✅ Done | test_webhook_edit | 2026-05-13 |
| wh-us1-11 | webhook | US1 | Webhook 删除 | ✅ Done | test_webhook_delete | 2026-05-13 |
| wh-us1-12 | webhook | US1 | Webhook 导出 | ✅ Done | test_webhook_export | 2026-05-13 |
| wh-us1-13 | webhook | US1 | Webhook 导入 | ✅ Done | test_webhook_import | 2026-05-13 |
| wh-us1-14 | webhook | US1 | Webhook 批量操作 | ✅ Done | test_webhook_batch | 2026-05-13 |
| wh-us1-15 | webhook | US1 | Webhook 权限 | ✅ Done | test_webhook_permission | 2026-05-13 |

## Summary

| Module | US | AC Count | Covered | Status |
|--------|-----|----------|---------|--------|
| alerts (AL) | US1 | 13 | 13 | ✅ Done |
| agent (AG) | US1-US3 | 14 | 14 | ✅ Done |
| cross_timeframe (CT) | US1 | 7 | 7 | ✅ Done |
| three_screen (TS) | US1 | 7 | 7 | ✅ Done |
| resonance (RS) | US1-US3 | 18 | 18 | ✅ Done |
| market_scan (MS) | US1-US3 | 15 | 15 | ✅ Done |
| news_center (NC) | US1-US5 | 17 | 17 | ✅ Done |
| webhook (WH) | US1 | 15 | 15 | ✅ Done |
| **Total** | - | **106** | **106** | **100%** |

## Status Legend

- ✅ Done: 有完整 L2 测试覆盖
- 🔄 WIP: 测试开发中
- ⚠️ Stub: 测试函数存在但为空
- ❌ Missing: 无测试覆盖
- 🗑️ Removed: AC 已废弃