# Webhook 任务清单

## Phase 1: 核心功能 ✅

- [x] Flask Webhook 服务 (webhook_bridge.py)
- [x] TradingView Webhook 端点 (`/tv-webhook`)
- [x] 飞书 Webhook 端点 (`/feishu-webhook`)
- [x] NL 命令解析 (nl_parser.py)
- [x] 正则模式: 买入/卖出/平仓/查看

## Phase 2: 执行 ✅

- [x] 后台线程下单 (ThreadPoolExecutor)
- [x] place_order_func.py 集成
- [x] 期货/外汇/商品品种支持
- [x] 订单状态追踪

## Phase 3: 通知 ✅

- [x] execDetails 成交回调
- [x] 飞书实时成交推送
- [x] 去重机制 (exec_id set)
- [x] 健康检查端点 (`/health`)

## Phase 4: 优化 🔄

- [ ] 添加限价单/止损单支持
- [ ] 订单预检风控
- [ ] 更好的错误处理

## Phase 5: 增强 📋

- [ ] 支持更多 NL 命令模式
- [ ] 多语言命令支持
- [ ] 订单历史记录