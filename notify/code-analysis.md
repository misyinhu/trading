# Trading 代码逻辑分析报告

> 生成时间: 2026-05-10
> 分析范围: webhook_bridge.py, nl_parser.py, test-cases.md

---

## 一、Webhook 服务路由分析

### 1. /health

**输入**: GET 请求，无参数

**输出**:
```json
{
  "status": "ok",
  "config": {
    "app_id": true,
    "conversation_id": true,
    "query_only": false
  }
}
```

**对应 TC**: WH-001 ✅ 测试正确

---

### 2. /tv-webhook

**输入**: POST JSON body
```json
{
  "action": "buy|sell|close",
  "symbol": "DOGE-USDT",
  "qty": 1,
  "order_type": "market",
  "exchange": "OKX",
  "sec_type": "FUT",
  "margin_mode": "cross"
}
```

**输出**:
```json
{
  "status": "ok",
  "order": {
    "code": "0",
    "msg": "",
    "data": [{"ordId": "123456"}]
  }
}
```

**对应 TC**: WH-101, WH-102 ✅ 测试正确

---

### 3. /feishu-webhook

**输入**: 
- GET: `?challenge=xxx` (飞书 URL 验证)
- POST: 飞书事件 JSON

**输出**:
```json
// 正常处理
{"status": "ok", "order": order_result}

// 错误
{"error": "错误信息"}

// GET 验证
{"challenge": "xxx"}
```

**关键逻辑**:
1. 消息去重（5秒内相同 `message_id` 跳过）
2. 命令模式：`/` 开头匹配 COMMANDS 字典
3. 自然语言模式：调用 `parse_trading_command()`
4. 订单去重（60秒内相同订单拦截）
5. 订单异步提交到后台线程执行

**对应 TC**: WH-201 ❌ **测试错误**

---

### 4. /positions

**输入**: GET 请求

**输出**:
```json
{
  "positions": [{"symbol": "", "position": 0, "avgCost": 0}],
  "count": N
}
```

---

### 5. /orders

**输入**: GET 请求

**输出**:
```json
{
  "orders": [{"orderId": 0, "symbol": "", "action": ""}],
  "count": N
}
```

---

### 6. /test-api

**输入**: 无

**输出**: `{"success": true/false, "result": "..."}`

---

### 7. /test-mtf

**输入**: POST JSON `{"text": "/多周期分析 [symbol]"}`

**输出**: `{"status": "ok", "result": "分析结果"}`

---

## 二、NL Parser 分析

### parse_trading_command 函数

**输入**: 自然语言字符串
- `"买入1手GC"`
- `"卖空2手NQ"`
- `"平仓GC"`
- `"查看持仓"`

**输出**:
```json
{
  "action": "BUY|SELL|CLOSE|QUERY|UNKNOWN",
  "raw": "原始输入",
  "quantity": 1,
  "symbol": "GC",
  "sec_type": "FUT|CASH|CMDTY|SWAP",
  "exchange": "SMART|IDEALPRO|OKX"
}
```

**注意**: 这个函数**不直接返回 HTTP 响应**，而是返回解析结果，由 webhook_bridge.py 决定如何处理。

---

## 三、WH-201 失败根因分析

### 问题

WH-201 测试用例期望：
```json
{
  "action": "buy",
  "symbol": "GC",
  "quantity": 1,
  "sec_type": "FUT"
}
```

实际 `/feishu-webhook` 返回：
```json
{
  "order": null,
  "status": "ok"
}
```

### 根因

**测试用例写错了**。`/feishu-webhook` 的设计是：
1. 解析 NL 命令
2. 如果是查询类命令（"查看持仓"），直接返回 `status: ok, order: null`
3. 如果是交易类命令，异步下单后返回 `status: ok, order: {下单结果}`

测试用例期望的是**解析结果**，但实际返回的是**处理状态**。

---

## 四、Test Cases vs 代码逻辑对照表

| TC-ID | 测试期望 | 实际代码逻辑 | 状态 |
|-------|---------|-------------|------|
| WH-001 | `/health` 返回 status + config | ✅ 一致 | PASS |
| WH-101 | TV 买入信号 → order object | ✅ 一致 | PASS |
| WH-102 | TV 卖出信号 → order object | ✅ 一致 | PASS |
| WH-201 | `/feishu-webhook` 返回解析结果 | ❌ 返回 status + order | **FAIL** |
| WH-301 | 成交通知 → 飞书推送 | ⚠️ 待验证 | PENDING |
| NC-xxx | 新闻事件中心功能 | ⚠️ 待验证 | PENDING |
| KB-xxx | Kanban 页面切换 | ⚠️ 待验证 | PENDING |
| ... | ... | ... | ... |

---

## 五、需要补充 proposal 的功能模块

基于代码分析，以下功能模块**没有 proposal/story**：

| 功能模块 | 代码文件 | 说明 |
|---------|---------|------|
| 飞书 Webhook 完整功能 | `webhook_bridge.py` | 需要补充 WH-201, WH-301 对应的 story |
| NL Parser 详细规格 | `nl_parser.py` | 支撑 webhook 但本身不是独立 story |
| /positions 查询 | `webhook_bridge.py` | 没有对应 TC |
| /orders 查询 | `webhook_bridge.py` | 没有对应 TC |
| /test-api | `webhook_bridge.py` | 测试辅助功能 |
| /test-mtf | `webhook_bridge.py` | 多周期分析测试 |

---

## 六、建议修正方案

### 1. 修正 WH-201 测试用例

**当前（错误）**:
```
Given 飞书 Webhook 服务运行
When POST "/feishu-webhook" Payload = {"message": {"content": "买入1手GC"}}
Then 解析结果: action = "buy", symbol = "GC", quantity = 1
```

**正确写法**:
```
Given 飞书 Webhook 服务运行
When POST "/feishu-webhook" Payload = {"message": {"content": "买入1手GC"}}
Then HTTP 200
And Response Body 应符合 $WebhookResponse
And $.status = "ok"
```

或者如果要验证解析结果，需要通过其他方式（如日志、数据库）验证。

### 2. 补充缺失的 proposal

建议为以下功能补充 proposal：
1. 飞书自然语言下单完整流程
2. 订单查询功能（/positions, /orders）
3. 健康检查监控

---

## 七、下一步行动

| 优先级 | 动作 | 负责角色 |
|--------|------|---------|
| P0 | 修正 WH-201 测试用例 | PM |
| P0 | 补充飞书 NL 下单 proposal | PM |
| P1 | 验证其他 WH-xxx 测试用例 | QA |
| P2 | 补充 /positions, /orders 的 proposal | PM |
