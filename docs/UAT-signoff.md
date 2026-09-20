# UAT 签字流程

> **版本**: v1.0
> **日期**: 2025-05-11
> **用途**: Sprint 结束时的正式验收签字流程

---

## 前置条件

在开始 UAT 签字前，必须满足：

- [ ] 所有 AC 都有 TC 覆盖（CI `ac-tc-coverage` green）
- [ ] 所有测试通过率 ≥ 95%（CI `pytest` green）
- [ ] E2E 测试全部通过（CI `e2e` green）
- [ ] OpenAPI 契约验证通过（CI `contract-validation` green）

---

## Sprint 完成标准

每个 US 必须同时满足：

1. **AC 覆盖率 100%**（每个 AC 都有 TC）
2. **TC 通过率 ≥ 95%**
3. **UAT 全部签字完成**

---

## 签字人

| 角色 | 姓名 | 日期 | 签字 |
|------|------|------|------|
| 产品负责人 (PM) | | | ☐ |
| 开发负责人 (DEV) | | | ☐ |
| QA 负责人 (QA) | | | ☐ |

---

## US 验收清单

| US | 模块 | 功能描述 | PM | DEV | QA | 备注 |
|----|------|---------|-----|-----|-----|------|
| KB-US1 | Navigation | 侧边栏导航 | ☐ | ☐ | ☐ | |
| NC-US1 | News | 日期筛选 | ☐ | ☐ | ☐ | |
| NC-US2 | News | 分类筛选 | ☐ | ☐ | ☐ | |
| NC-US3 | News | 数量控制 | ☐ | ☐ | ☐ | |
| NC-US4 | News | 财经Tab | ☐ | ☐ | ☐ | |
| NC-US5 | News | 情绪Tab | ☐ | ☐ | ☐ | |
| AL-US1 | Alerts | 周期设置 | ☐ | ☐ | ☐ | |
| AL-US2 | Alerts | 警报触发 | ☐ | ☐ | ☐ | |
| AL-US3 | Alerts | 警报详情 | ☐ | ☐ | ☐ | |
| MS-US1 | Scan | 扫描类型 | ☐ | ☐ | ☐ | |
| MS-US2 | Scan | 市场选择 | ☐ | ☐ | ☐ | |
| MS-US3 | Scan | 扫描执行 | ☐ | ☐ | ☐ | |
| TS-US1 | ThreeScreen | 三周期信号 | ☐ | ☐ | ☐ | |
| RS-US1 | Resonance | K线图表 | ☐ | ☐ | ☐ | |
| RS-US2 | Resonance | 共振评分 | ☐ | ☐ | ☐ | |
| RS-US3 | Resonance | 指标显示 | ☐ | ☐ | ☐ | |
| AG-US1 | Agent | 关键词解析 | ☐ | ☐ | ☐ | |
| AG-US2 | Agent | AI分析 | ☐ | ☐ | ☐ | |
| AG-US3 | Agent | PDF导出 | ☐ | ☐ | ☐ | |
| CT-US1 | CrossTimeframe | 矛盾检测 | ☐ | ☐ | ☐ | |

---

## 签字流程

1. **DEV 完成开发** → 更新 `SPEC.md` 中 TC 列
2. **QA 执行测试** → 验证通过后更新 `docs/verified-facts.md`
3. **PM 审查** → 确认所有 US/AC 符合预期
4. **三方签字** → 在本文件签字
5. **PMO 归档** → 合并 `SPEC.md` 到 `openspec/specs/`

---

## 异常处理

| 情况 | 处理方式 |
|------|---------|
| AC 无法自动化测试 | 手动测试 + QA 签字确认 |
| 测试失败无法修复 | 创建 Issue + 延期 UAT |
| PM 拒绝签字 | 记录原因 + 退回 DEV 修复 |