# Trading 项目 TDD + US-AC-TC 链路落地方案

> **版本**: v2.0（对照 Content Factory 补充 OpenAPI + 文档同步）
> **日期**: 2025-05-11
> **参考**: `docs/plans/content-factory-tdd-migration-plan.md`

## 0. OpenAPI 契约建立（Phase 0）— 止血优先

> **昨天·今天·明天 叙事**: 当前 CI 已有 orphan-test-check、ac-tc-coverage、pytest，同类领先。但缺 contract-validation 和 E2E 两个关键质量门禁。这是"能跑"到"可控"的必经台阶。

### 0.1 风险解读（非技术人员可读）

| 风险 | 后果 | 类比 |
|------|------|------|
| 无契约验证 | 两个人改同一 API，各自通过单元测试，集成爆雷，修复成本×10 | 没有交通规则，撞车后才知道错 |
| E2E 无法验证 | 每次上线手工回归，漏测分支可能生产故障 | 每次发车前靠人工检查刹车 |
| 版本漂移 | IB/OKX API 升级时不知道哪些字段变了，只能靠线上报警发现 | 没有基准线，变了也不知道 |

### 0.2 迭代 A：Phase 0 执行计划

**目标**: OpenAPI 契约 + CI contract-validation job + E2E mock 环境

| 行动 | 产出 | 负责人 | 预计耗时 |
|------|------|--------|---------|
| 0.2.1 为 webhook_bridge.py 生成 OpenAPI 3.0 契约（手动或 AI 反向生成） | `contracts/webhook_bridge.openapi.yaml` | DEV | 2h |
| 0.2.2 CI 新增 contract-validation job（复用 Content Factory 的 npx oas-validate） | `.github/workflows/tc-linkage.yml` 新 job | DEV | 0.5h |
| 0.2.3 在 CI 中直接调用 webhook_bridge 服务器端点进行 E2E 测试 | pytest + requests 调用 `https://trading-server/webhook` | QA | 2h |

**关键承诺**: 任何 PR 修改 webhook_bridge.py 但未同步更新 OpenAPI 文件，CI 立即失败。第三方接口变更时，用 oas-diff 自动生成影响分析报告。

### 0.3 验收标准

```bash
# 验收条件
1. contracts/webhook_bridge.openapi.yaml 存在且 YAML 语法正确
2. npx oas-validate contracts/webhook_bridge.openapi.yaml 通过
3. CI contract-validation job 在 PR 中运行且通过
4. E2E 测试调用真实服务器 URL（https://trading-server/webhook），不依赖 localhost
```

### 0.4 产出清单

```
contracts/
└── webhook_bridge.openapi.yaml  ← OpenAPI 3.0 契约
.github/workflows/
└── tc-linkage.yml               ← 新增 contract-validation job
tests/e2e/
└── webhook_integration/
    └── test_webhook_endpoint.py  ← E2E 测试（调用服务器 URL）
```

---

## 1. 背景与目标

### 1.1 当前状态

| 组件 | 现状 | 问题 |
|------|------|------|
| **US/AC** | `proposal.md` 纯文本 checklist | 非 Gherkin 格式，无法直接执行 |
| **TC** | `docs/test-cases.md` markdown | 独立文档，无 `@Tag` 绑定 |
| **测试代码** | `tests/` 有 11 个文件 | 散乱，无 `@AC` 标签，未绑定 AC |
| **契约** | 无 | 没有 OpenAPI 定义 |
| **CI** | Heartbeat (数量检查) | 无孤儿测试检测、无覆盖率验证 |

### 1.2 目标状态

```
proposal.md (US/AC)
    ↓ 转换
.feature (Gherkin AC) ← 双向绑定 proposal.md
    ↓ AI 生成
tests/unit/ ← @Tag 绑定 AC (pytest.mark.TC-xxx)
tests/e2e/ ← Playwright E2E
    ↓ CI
孤儿测试检测 + AC-TC 映射验证
    ↓
Harness Pipeline ← AC聚合报告 + UAT签字
```

### 1.3 Trading 项目特殊性

| 维度 | Content Factory | Trading |
|------|-----------------|---------|
| **技术栈** | Streamlit + SQLite | Streamlit + IB/OKX API |
| **API 形态** | app.py 函数 | webhook_bridge.py (Flask) |
| **OpenAPI** | 需手动创建 | 可从 Flask 导出 |
| **测试存量** | 2 个文件 | 11 个文件 (无 AC 绑定) |
| **模块** | 单一 app | kanban/ + webhook/ 双模块 |

---

## 2. 现状盘点

### 2.1 测试文件清单

| 文件 | pytest.mark | AC标签 | 状态 |
|------|------------|--------|------|
| `test_exchange_mapping.py` | ❌ | ❌ | 需迁移 |
| `test_nl_trading.py` | ❌ | ❌ | 需迁移 |
| `test_place_order_func.py` | ❌ | ❌ | 需迁移 |
| `test_spread_alert.py` | ❌ | ❌ | 需迁移 |
| `test_spread_engine.py` | ❌ | ❌ | 需迁移 |
| `test_trading.py` | ❌ | ❌ | 需迁移 |
| `test_trend_filter.py` | ❌ | ❌ | 需迁移 |
| `test_utils.py` | ❌ | ❌ | 需迁移 |
| `test_webhook_trading.py` | ❌ | ❌ | 需迁移 |
| `test_z120_history.py` | ❌ | ❌ | 需迁移 |
| `integration/` | ❌ | ❌ | 需迁移 |

**结论**：0/11 测试文件有 `@AC` 标签，全部需要迁移。

### 2.2 US-AC-TC 链路现状

| 模块 | US数 | AC数 | TC定义数 | TC绑定数 |
|------|------|------|---------|---------|
| **AL** (警报) | 4 | 12 | 12 | 0 |
| **NC** (新闻) | 5 | 16 | 16 | 0 |
| **MS** (扫描) | 3 | 8 | 8 | 0 |
| **RS** (共振) | 3 | 8 | 8 | 0 |
| **AG** (Agent) | 3 | 7 | 7 | 0 |
| **SC** (配置) | 2 | 6 | 6 | 0 |
| **MI** (洞察) | 1 | 2 | 2 | 0 |
| **TS** (三重滤网) | 1 | 2 | 2 | 0 |
| **其他** | 6 | 20 | 20 | 0 |
| **总计** | 28 | 81 | 81 | 0 |

**结论**：81 个 TC 定义，0 个有代码绑定。

---

## 3. 迁移阶段

### Phase 1: 文档层转换 - Gherkin Feature 文件（P0）

**目标**: 将 `proposal.md` 的 US/AC 转为 `.feature` 格式

**任务**:
- [ ] 1.1 提取 `openspec/changes/trading/kanban/proposal.md` 所有 US 和 AC
- [ ] 1.2 创建 `openspec/changes/trading/kanban/features/` 目录
- [ ] 1.3 为每个 AC 生成 Gherkin Scenario
- [ ] 1.4 建立 proposal.md 与 `.feature` 的双向链接

**产出**:
```
openspec/changes/trading/kanban/
├── features/
│   ├── alerts/
│   │   ├── AL-US1-cycle-setting.feature
│   │   ├── AL-US2-alert-trigger.feature
│   │   ├── AL-US3-alert-detail.feature
│   │   └── AL-US4-correlation.feature
│   ├── news/
│   │   ├── NC-US1-date-filter.feature
│   │   ├── NC-US2-category-filter.feature
│   │   ├── NC-US3-count-control.feature
│   │   ├── NC-US4-finance-tab.feature
│   │   └── NC-US5-sentiment-tab.feature
│   ├── scan/
│   │   ├── MS-US1-scan-type.feature
│   │   ├── MS-US2-market-select.feature
│   │   └── MS-US3-scan-execute.feature
│   └── ...
├── proposal.feature          ← 汇总文件
└── proposal.md              ← 保留（仅摘要）
```

**Gherkin 示例**:
```gherkin
@US-AL-US1 @AC-AL-US1-1
Feature: 警报周期设置

  Background:
    Given 用户已登录 Kanban 系统
    And 在警报中心页面

  @AC-AL-US1-1 @happy-path
  Scenario: 切换警报周期
    When 用户选择周期 "M30"
    Then 调用 get_all_tv_indicators(timeframe="M30")
    And 页面数据更新为 M30 周期

  @AC-AL-US1-2 @edge
  Scenario: 切换到不支持的周期
    When 用户选择周期 "1D"
    Then 显示错误 "不支持该周期"
    And 保持当前周期不变
```

---

### Phase 2: 测试目录结构重建（P0）

**目标**: 按标准结构重建 `tests/`

**任务**:
- [ ] 2.1 创建标准目录结构
- [ ] 2.2 将现有测试文件迁移到 `tests/legacy/`
- [ ] 2.3 创建新的测试文件带 AC 绑定

**标准目录结构**:
```
tests/
├── unit/                    ← 单元测试 (pytest)
│   ├── __init__.py
│   ├── test_alerts.py       ← @pytest.mark.TC-AL-001
│   ├── test_news.py         ← @pytest.mark.TC-NC-001
│   ├── test_market_scan.py  ← @pytest.mark.TC-MS-001
│   └── ...
├── integration/             ← 集成测试
│   ├── __init__.py
│   ├── test_webhook_commands.py
│   └── test_okx_trading.py
├── e2e/                    ← Playwright E2E
│   ├── __init__.py
│   ├── alerts.spec.ts
│   └── news.spec.ts
├── fixtures/                ← pytest fixtures
│   └── conftest.py
├── legacy/                  ← 旧测试文件归档
│   └── (现有 11 个测试文件)
└── helpers/                ← 测试辅助
    └── mock_ib.py
```

---

### Phase 3: 测试代码 AC 绑定（P0）

**目标**: 为每个 TC 生成带 `@pytest.mark.TC-xxx` 绑定的测试代码

**任务**:
- [ ] 3.1 为 81 个 TC 生成测试代码骨架
- [ ] 3.2 嵌入 `@pytest.mark.TC-xxx` 和 `@pytest.mark.AC-xxx` 标签
- [ ] 3.3 验证测试可运行

**测试代码示例**:
```python
# tests/unit/test_alerts.py
import pytest

@pytest.mark.TC-AL-001
@pytest.mark.AC-AL-US1-1
def test_alert_cycle_default():
    """TC-AL-001 @AC-AL-US1-1 默认周期为 15s"""
    # Given: 页面加载
    # When: 初始化警报中心
    # Then: 默认选择 "15s" 周期
    # And: 调用 get_all_tv_indicators(timeframe="15s")
    pass

@pytest.mark.TC-AL-002
@pytest.mark.AC-AL-US1-1
def test_alert_cycle_switch():
    """TC-AL-002 @AC-AL-US1-1 切换周期后检测逻辑更新"""
    # Given: 用户已选择周期 "15s"
    # When: 用户切换为 "1m"
    # Then: 调用 get_all_tv_indicators(timeframe="1m")
    # And: 页面数据更新为 1m 周期
    pass
```

---

### Phase 3.x: 前端交互测试（Playwright E2E）

**工具**: Playwright (`npx playwright test`)

#### §3.x.1 Trading 前端页面元素映射表

> 基于 `openspec/changes/trading/kanban/proposal.md` 的 US/AC 定义

| US | AC | 页面 | 关键元素 | 测试方式 |
|-----|-----|------|----------|----------|
| **NC (新闻事件中心)** | | pages/0_news_center.py | | |
| NC-US1 | AC-NC-001 | /news | 日期选择器 (st.date_input) | browser_fill + snapshot |
| NC-US1 | AC-NC-001 | /news | 新闻列表 (st.dataframe) | snapshot 验证 |
| NC-US2 | AC-NC-101 | /news | 分类选择器 (st.multiselect) | browser_select |
| NC-US3 | AC-NC-201 | /news | 数量滑块 (st.slider) | browser_click + snapshot |
| NC-US4 | AC-NC-301 | /news | Tab: 财经新闻 | snapshot |
| NC-US5 | AC-NC-401 | /news | Tab: 市场情绪 | snapshot |
| **AL (警报中心)** | | pages/1_alerts.py | | |
| AL-US1 | AC-AL-001 | /alerts | 周期选择器 (st.selectbox) | browser_select |
| AL-US2 | AC-AL-201 | /alerts | RSI/价格警报触发 | snapshot |
| AL-US3 | AC-AL-301 | /alerts | 警报详情展开 | browser_click + snapshot |
| **MS (市场扫描)** | | pages/2_market_scan.py | | |
| MS-US1 | AC-MS-001 | /market-scan | 扫描类型选择 (st.selectbox) | browser_select |
| MS-US1 | AC-MS-002 | /market-scan | 参数输入框 | browser_fill |
| MS-US2 | AC-MS-101 | /market-scan | 市场多选 (st.multiselect) | browser_select |
| MS-US3 | AC-MS-301 | /market-scan | 执行按钮 (st.button) | browser_click |
| MS-US3 | AC-MS-301 | /market-scan | 进度条 (st.progress) | snapshot |
| MS-US3 | AC-MS-302 | /market-scan | 结果表格 (st.dataframe) | snapshot |
| **TS (三重滤网)** | | pages/3_three_screen.py | | |
| TS-US1 | AC-TS-201 | /three-screen | M30/M5/M1 信号显示 | snapshot |
| TS-US1 | AC-TS-201 | /three-screen | 买卖信号/阻力位/支撑位 | snapshot |
| TS-US1 | AC-TS-202 | /three-screen | 信号一致高亮 | snapshot |
| **RS (多周期共振)** | | pages/4_resonance.py | | |
| RS-US1 | AC-RS-001 | /resonance | TradingView 图表 | snapshot |
| RS-US1 | AC-RS-001 | /resonance | 缩放/滚动交互 | browser_click |
| RS-US2 | AC-RS-201 | /resonance | 共振度评分 (0-100) | snapshot |
| RS-US2 | AC-RS-202 | /resonance | 共振/矛盾颜色标识 | snapshot |
| RS-US3 | AC-RS-301 | /resonance | MA20 指标叠加 | snapshot |
| **CT (跨周期分析)** | | pages/5_cross_timeframe.py | | |
| CT-US1 | AC-CT-001 | /cross-timeframe | Z-Score 共振检测 | snapshot |
| CT-US1 | AC-CT-001 | /cross-timeframe | 相关性破裂检测 | snapshot |
| CT-US1 | AC-CT-002 | /cross-timeframe | 矛盾信号评分 | snapshot |
| CT-US1 | AC-CT-002 | /cross-timeframe | 强烈入场信号 | snapshot |
| **AG (市场洞察)** | | pages/6_agent.py | | |
| AG-US1 | AC-AG-001 | /agent | 关键词输入框 | browser_fill |
| AG-US1 | AC-AG-002 | /agent | 解析结果显示 | snapshot |
| AG-US2 | AC-AG-101 | /agent | AI 分析报告 | snapshot |
| AG-US3 | AC-AG-201 | /agent | INDEX_MAP 映射结果 | snapshot |

**前置条件**:
- Trading Kanban app 运行在 `http://localhost:8501`
- 使用 Playwright MCP 或原生 Playwright

---

#### §3.x.2 交互测试实现（Playwright E2E）

**Streamlit 页面交互测试规范**:

```typescript
// tests/e2e/kanban/alerts.spec.ts
import { test, expect } from '@playwright/test';

/**
 * Phase 3.x 前端交互测试
 * 工具: Playwright
 * 定位符: Streamlit 元素使用 data-testid 或 aria-label
 * 交互模式: page.selectbox(), page.fill(), page.click()
 */

test.describe('AL-US1 警报周期设置', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.goto('/alerts');
    await expect(page.locator('[data-testid=stSelectbox]')).toBeVisible();
  });

  test('AL-TC-001: 切换周期后数据更新', async ({ page }) => {
    // 1. 验证初始状态
    const cycleSelect = page.locator('[data-testid=stSelectbox]').first();
    await expect(cycleSelect).toBeVisible();
    
    // 2. 触发交互：切换周期
    await cycleSelect.selectOption('M30');
    
    // 3. 验证 spinner 显示（加载中）
    await expect(page.locator('[data-testid=stSpinner]')).toBeVisible();
    
    // 4. 验证结果：数据更新
    await expect(page.locator('.alert-data')).toContainText('M30');
    
    // 5. 验证 spinner 消失（加载完成）
    await expect(page.locator('[data-testid=stSpinner]')).toBeHidden();
  });

  test('AL-TC-002: 切换到不支持的周期显示错误', async ({ page }) => {
    // 1. 切换到不支持的周期
    await page.locator('[data-testid=stSelectbox]').first().selectOption('1D');
    
    // 2. 验证错误提示
    await expect(page.locator('[data-testid=stAlert]')).toContainText('不支持该周期');
    
    // 3. 验证周期保持不变
    await expect(page.locator('.current-cycle')).toContainText('15s');
  });
});

test.describe('NC-US1 新闻日期筛选', () => {
  
  test('NC-TC-001: 日期范围选择器正常工作', async ({ page }) => {
    await page.goto('/news');
    
    // 1. 验证日期输入框存在
    const dateInput = page.locator('[data-testid=stDateInput]');
    await expect(dateInput).toBeVisible();
    
    // 2. 选择日期范围
    await page.locator('[data-testid=stDateInput] input').fill('2024-01-01');
    
    // 3. 验证筛选结果更新
    await expect(page.locator('.news-list')).toBeVisible();
  });
});

test.describe('MS-US1 市场扫描', () => {
  
  test('MS-TC-001: 扫描类型切换正常', async ({ page }) => {
    await page.goto('/market-scan');
    
    // 1. 验证扫描类型选择器
    const scanTypeSelect = page.locator('[data-testid=stSelectbox]').filter({ hasText: '扫描类型' });
    await expect(scanTypeSelect).toBeVisible();
    
    // 2. 切换扫描类型
    await scanTypeSelect.selectOption('价差扫描');
    
    // 3. 验证结果区域更新
    await expect(page.locator('.scan-results')).toBeVisible();
    await expect(page.locator('.scan-results').locator('tr')).toHaveCount({ minimum: 1 });
  });
});

test.describe('Webook E2E（调用服务器 URL）', () => {
  
  const SERVER_URL = process.env.TRADING_SERVER_URL || 'https://trading-server';
  
  test('WB-TC-001: webhook 端点正常响应', async ({ request }) => {
    // 注意：此测试调用真实服务器 URL，不使用 localhost
    const response = await request.post(`${SERVER_URL}/webhook`, {
      data: {
        event: 'test',
        timestamp: new Date().toISOString(),
        payload: { symbol: 'FU', action: 'BUY' }
      }
    });
    
    expect(response.status()).toBe(200);
    const json = await response.json();
    expect(json.status).toBe('success');
  });
});
```

**Streamlit 元素定位规范**:

| 元素类型 | 定位方式 | 示例 |
|---------|---------|------|
| Selectbox | `data-testid=stSelectbox` + 文本过滤 | `page.locator('[data-testid=stSelectbox]').filter({hasText: '周期'})` |
| TextInput | `data-testid=stTextInput` | `page.locator('[data-testid=stTextInput] input').fill('FU')` |
| DateInput | `data-testid=stDateInput` | `page.locator('[data-testid=stDateInput] input')` |
| Button | `data-testid=stButton` | `page.locator('[data-testid=stButton]').filter({hasText: '提交'})` |
| Spinner | `data-testid=stSpinner` | `expect(page.locator('[data-testid=stSpinner]')).toBeVisible()` |
| Alert/Error | `data-testid=stAlert` | `expect(page.locator('[data-testid=stAlert]')).toContainText('错误')` |
| DataFrame | `data-testid=stDataFrame` | `page.locator('[data-testid=stDataFrame]')` |

**E2E 验收标准**:

```bash
# Phase 3.x 验收条件
1. 每个 Kanban 页面至少有 1 个 E2E 测试覆盖核心交互
2. Playwright 测试使用 page.locator() 定位元素，不使用 XPath
3. 每个测试包含:
   - beforeEach 导航到目标页面
   - 交互前状态验证
   - 交互触发 (selectOption, fill, click)
   - 交互后结果断言 (toBeVisible, toContainText, toHaveCount)
4. webhook E2E 测试调用真实服务器 URL（https://trading-server），不依赖 localhost
5. CI 中 E2E 测试通过: npx playwright test tests/e2e/ --reporter=list
```

---

### Phase 4: CI 链路验证（P1）

**目标**: 建立 GitHub Actions CI 验证链路

**任务**:
- [ ] 4.1 创建 `.github/` 目录和 workflows
- [ ] 4.2 实现孤儿测试检测（无 `@TC` 标签的测试报警）
- [ ] 4.3 实现 AC→TC 映射完整性检查
- [ ] 4.4 添加测试覆盖率报告
- [ ] 4.5 添加 Playwright E2E 测试到 CI

**CI 工作流**:
```yaml
# .github/workflows/tc-linkage.yml
name: TC Linkage Check

on:
  pull_request:
    paths:
      - 'tests/**'
      - 'openspec/**'
      - 'src/**'

jobs:
  orphan-test-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Detect orphan tests (no @TC marker)
        run: |
          # 找出没有 @pytest.mark.TC 的测试
          grep -rL "@pytest.mark.TC" tests/unit/*.py || echo "FAIL: Orphan tests found"

  ac-tc-coverage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Check AC-TC mapping completeness
        run: python scripts/check_ac_tc_mapping.py

  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Run unit tests
        run: pytest tests/unit/ tests/integration/ --junitxml=report.xml
      
      - name: Upload test results
        uses: actions/upload-artifact@v4
        with:
          name: pytest-results
          path: report.xml

  e2e:
    runs-on: ubuntu-latest
    container: mcr.microsoft.com/playwright:v1.40.0
    env:
      TRADING_SERVER_URL: ${{ secrets.TRADING_SERVER_URL }}
    steps:
      - uses: actions/checkout@v4
      
      - name: Install dependencies
        run: npm install && npx playwright install-deps
      
      - name: Run Playwright E2E tests
        run: npx playwright test tests/e2e/ --reporter=list
        env:
          TRADING_SERVER_URL: ${{ secrets.TRADING_SERVER_URL }}

  contract-validation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Validate OpenAPI contract
        run: npx oas-validate contracts/webhook_bridge.openapi.yaml
```

**检查脚本 `scripts/check_ac_tc_mapping.py`**:
```python
#!/usr/bin/env python3
"""检查 AC → TC 映射完整性"""
import re
import sys
from pathlib import Path

AC_PATTERN = re.compile(r'@AC-([A-Z]{2})-US(\d+)-(\d+)')
TC_PATTERN = re.compile(r'@pytest\.mark\.TC-([A-Z]{2})-(\d+)')

def main():
    ac_set = set()
    tc_set = set()
    
    # 扫描 .feature 文件收集 AC
    for feature_file in Path('openspec').glob('**/*.feature'):
        content = feature_file.read_text()
        ac_set.update(AC_PATTERN.findall(content))
    
    # 扫描测试文件收集 TC
    for test_file in Path('tests').glob('**/*.py'):
        content = test_file.read_text()
        tc_set.update(TC_PATTERN.findall(content))
    
    # 检查覆盖率
    missing = ac_set - tc_set
    if missing:
        print(f"❌ {len(missing)} AC 没有对应的 TC:")
        for ac in sorted(missing):
            print(f"   AC-{ac[0]}-US{ac[1]}-{ac[2]}")
        sys.exit(1)
    else:
        print(f"✅ 全部 {len(ac_set)} AC 都有 TC 覆盖")
        sys.exit(0)

if __name__ == '__main__':
    main()
```

---

### Phase 5: 文档同步与 UAT 流程（P1）— 完整闭环

> **昨天·今天·明天 叙事**: 当前 Phase 5 只有 `scripts/aggregate_ac_report.py`（半自动报告），没有正式签字和双向追溯。对比 Content Factory 模板，缺失 proposal ↔ .feature 双向链接、CI 可见性、UAT 审批门禁。这是"有测试"到"可验收"的必经台阶。

### 5.1 风险解读（非技术人员可读）

| 风险 | 后果 | 类比 |
|------|------|------|
| 双向链接断裂 | proposal.md（需求）与 .feature（测试）成孤岛，后期"改需求忘改测试"成为常态 | 地图和 GPS 不同步 |
| 无 CI 可见性 | PM、业务方看不到每个 US 的健康度，只能问 QA"测完了吗" | 飞机起飞前没有仪表盘 |
| UAT 无签字流程 | 没有正式"完成"定义，开发反复被要求补测，PM 无法结项 | 验收没有签字就交钥匙 |

### 5.2 迭代 B：Phase 5 执行计划

**目标**: proposal ↔ .feature 双向链接 + CI 状态徽章 + Harness UAT 审批

| 行动 | 产出 | 负责人 | 预计耗时 |
|------|------|--------|---------|
| 5.2.1 在 `proposal.md` 增加状态徽章，链接到 CI 测试报告 | `proposal.md` 中的 ![TC](badge) | DEV | 1h |
| 5.2.2 建立双向链接规范：.feature 第一行注释包含 @proposal US-xxx；proposal.md 的 AC 末尾标注 → feature:features/xxx.feature | 更新 PMO-GOVERNANCE.md | PMO | 0.5h |
| 5.2.3 新增 CI 检查：orphan-feature-check（无主 .feature）+ unlinked-proposal-check（无对应 .feature 的 AC） | `.github/workflows/tc-linkage.yml` 新 job | DEV | 2h |
| 5.2.4 预发布环境增加 UAT 签字步骤：部署后自动生成待办清单（每个 US 一个 checkbox），PM 在 Harness 中勾选后才允许进入生产 | Harness Approval 步骤 + 脚本 | DEV/SRE | 3h |

**关键承诺**: PM 打开任何一个 proposal.md 就能看到该 US 的测试通过率；每个 sprint 结束，UAT 签字成为自动化门禁，再无"我觉得好了"的主观判断。

### 5.3 双向链接规范

**proposal.md 中**:
```markdown
## 警报中心 (AL)

| US | AC | Feature 文件 | CI 状态 |
|----|----|-------------|---------|
| US1 | AC1-3 | [AL-US1-cycle-setting.feature](./openspec/changes/trading/kanban/features/alerts/AL-US1-cycle-setting.feature) | ![TC](https://github.com/.../badge.svg) |
```

**.feature 文件 Header**:
```gherkin
# @proposal: ../proposal.md#al-us1-cycle-setting
# @CI: https://github.com/.../workflows/tc-linkage.yml
# @last-updated: 2025-05-11
```

### 5.4 UAT 签字流程

**文件**: `docs/UAT-signoff.md`

```markdown
# UAT 签字流程

## 前置条件
- [ ] 所有 AC 都有 TC 覆盖（CI green）
- [ ] 所有测试通过率 ≥ 95%
- [ ] E2E 测试全部通过

## 签字人
- [ ] 产品负责人: __________ 日期: __________
- [ ] 开发负责人: __________ 日期: __________
- [ ] QA 负责人: __________ 日期: __________

## Sprint 完成标准
每个 US 必须同时满足：
1. AC 覆盖率 100%（每个 AC 都有 TC）
2. TC 通过率 ≥ 95%
3. UAT 全部签字完成
```

### 5.5 产出清单

```
docs/
└── UAT-signoff.md                    ← UAT 签字模板
proposal.md                           ← 更新：双向链接 + CI 徽章
.openspec/changes/trading/kanban/features/**/*.feature  ← 更新：Header 链接
.github/workflows/
└── tc-linkage.yml                   ← 新增 orphan-feature-check, unlinked-proposal-check jobs
tests/e2e/
└── webhook_integration/
    └── test_webhook_endpoint.py      ← E2E 测试（调用服务器 URL）
```

---

## 6. 资源估算

| Phase | 工作量 | 优先级 |
|-------|--------|--------|
| Phase 0 (OpenAPI 契约) | 0.5d | P0 |
| Phase 1 (Gherkin) | 2d | P0 |
| Phase 2 (目录结构) | 0.5d | P0 |
| Phase 3 (AC 绑定) | 3d | P0 |
| Phase 4 (CI) | 1d | P1 |
| Phase 5 (文档同步 + UAT) | 1d | P1 |

**总计**: ~8d (约 1.5 周)

---

## 附录 A: Trading 模块清单

| 模块 | 前缀 | US数 | AC数 |
|------|------|------|------|
| 警报中心 | AL | 4 | 12 |
| 新闻中心 | NC | 5 | 16 |
| 市场扫描 | MS | 3 | 8 |
| 多周期共振 | RS | 3 | 8 |
| 市场分析 Agent | AG | 3 | 7 |
| 扫描配置 | SC | 2 | 6 |
| 市场洞察 | MI | 1 | 2 |
| 三重滤网 | TS | 1 | 2 |
| 跨周期矛盾 | CT | 1 | 4 |
| 其他 | KB/PM | 5 | 16 |
| **总计** | | **28** | **81** |

---

## 附录 B: 测试文件迁移清单

| 文件 | 目标位置 | 优先级 |
|------|---------|--------|
| `test_alerts.py` | `tests/unit/test_alerts.py` | P0 |
| `test_news.py` | `tests/unit/test_news.py` | P0 |
| `test_market_scan.py` | `tests/unit/test_market_scan.py` | P0 |
| `test_webhook_trading.py` | `tests/integration/test_webhook_commands.py` | P1 |
| `test_place_order_func.py` | `tests/unit/test_orders.py` | P1 |
| 其他 | `tests/legacy/` | P2 |
