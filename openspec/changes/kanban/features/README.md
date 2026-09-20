# Kanban Epic - Feature 文件汇总
> 本目录包含所有用户故事的 Gherkin Feature 文件
> 每个 Feature 对应 proposal.md 中的一个 US
> AC 标签格式: @AC-{模块}-US{编号}-{序号}
> TC 标签格式: @TC-{模块}-{序号}

## 文件清单

### 1. 警报中心 (Alerts)

| 文件 | US | AC数 | TC数 |
|------|-----|------|------|
| `alerts/AL-US1-4.feature` | AL-US1~US4 | 12 | 12 |

### 2. 新闻中心 (News)

| 文件 | US | AC数 | TC数 |
|------|-----|------|------|
| `news/NC-US1-5.feature` | NC-US1~US5 | 16 | 16 |

### 3. 市场扫描 (Market Scan)

| 文件 | US | AC数 | TC数 |
|------|-----|------|------|
| `scan/MS-US1-3.feature` | MS-US1~US3 | 8 | 8 |

### 4. 多周期共振 (Resonance)

| 文件 | US | AC数 | TC数 |
|------|-----|------|------|
| `resonance/RS-US1-3.feature` | RS-US1~US3 | 8 | 8 |

### 5. 三重滤网 (Three Screen)

| 文件 | US | AC数 | TC数 |
|------|-----|------|------|
| `three_screen/TS-US1.feature` | TS-US1 | 2 | 2 |

### 6. 市场分析 Agent

| 文件 | US | AC数 | TC数 |
|------|-----|------|------|
| `agent/AG-US1-3.feature` | AG-US1~US3 | 7 | 7 |

### 7. 跨周期分析 (Cross Timeframe)

| 文件 | US | AC数 | TC数 |
|------|-----|------|------|
| `cross_timeframe/CT-US1.feature` | CT-US1 | 4 | 4 |

## 统计汇总

| 指标 | 值 |
|------|---|
| Feature 文件总数 | 7 |
| US 总数 | 17 |
| AC 总数 | 57 |
| TC 总数 | 57 |

## 标签规范

### US 标签
- 格式: `@US-{模块}-{US序号}`
- 示例: `@US-AL-US1`, `@US-NC-US3`

### AC 标签
- 格式: `@AC-{模块}-US{序号}-{AC序号}`
- 示例: `@AC-AL-US1-1`, `@AC-NC-US3-2`

### TC 标签
- 格式: `@TC-{模块}-{TC序号}`
- 示例: `@TC-AL-001`, `@TC-NC-101`

### 场景类型标签
- `@happy-path`: 正常流程
- `@edge`: 边界/异常情况

## 与 proposal.md 的双向链接

每个 Feature 文件顶部的 `@US-XXX` 标签链接回 proposal.md 中的对应 US。
TC 定义中的 `@TC-XXX` 标签链接回 `docs/test-cases.md` 中的对应 TC。

## CI 验证

```bash
# 统计 AC 数量
grep -c "@AC-" openspec/changes/trading/kanban/features/**/*.feature

# 统计 TC 数量
grep -c "@TC-" openspec/changes/trading/kanban/features/**/*.feature

# 验证格式
npx gherkin-lint features/
```
