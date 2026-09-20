#!/usr/bin/env python3
"""
为所有 .feature 文件添加 @spec 头部链接
"""

import re
from pathlib import Path

SPEC_MD_PATH = "../SPEC.md"

# 映射表：feature文件 → SPEC.md中的anchor
FEATURE_TO_SPEC_ANCHOR = {
    "alerts/AL-US1-4.feature": "alerts-al-us1-cycle-setting",
    "alerts/AL-US2-4.feature": "alerts-al-us2-alert-trigger",
    "alerts/AL-US3-4.feature": "alerts-al-us3-alert-detail",
    "alerts/AL-US4-4.feature": "alerts-al-us4-correlation",
    "news/NC-US1-5.feature": "news-nc-us1-date-filter",
    "news/NC-US2-5.feature": "news-nc-us2-category-filter",
    "news/NC-US3-5.feature": "news-nc-us3-count-control",
    "news/NC-US4-5.feature": "news-nc-us4-finance-tab",
    "news/NC-US5-5.feature": "news-nc-us5-sentiment-tab",
    "scan/MS-US1-3.feature": "scan-ms-us1-scan-type",
    "scan/MS-US2-3.feature": "scan-ms-us2-market-select",
    "scan/MS-US3-3.feature": "scan-ms-us3-scan-execute",
    "three_screen/TS-US1.feature": "three-screen-ts-us1",
    "resonance/RS-US1-3.feature": "resonance-rs-us1-chart",
    "resonance/RS-US2-3.feature": "resonance-rs-us2-resonance",
    "resonance/RS-US3-3.feature": "resonance-rs-us3-indicator",
    "agent/AG-US1-3.feature": "agent-ag-us1-keyword",
    "agent/AG-US2-3.feature": "agent-ag-us2-ai-analysis",
    "agent/AG-US3-3.feature": "agent-ag-us3-pdf-export",
    "cross_timeframe/CT-US1.feature": "cross-timeframe-ct-us1",
    "config/KB-US1.feature": "navigation-kb-us1",
}


def add_spec_header(feature_file: Path, anchor: str) -> bool:
    content = feature_file.read_text()

    # 检查是否已有 @spec 头部
    if "# @spec:" in content:
        print(f"  ⏭️  已存在 @spec: {feature_file.name}")
        return False

    # 构建新头部
    new_header = f"# @spec: {SPEC_MD_PATH}#{anchor}\n# @CI: https://github.com/trading/workflows/tc-linkage.yml\n# @last-updated: 2025-05-11\n"

    # 在第一个 @tag 前插入
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("@"):
            lines.insert(i, new_header)
            break

    feature_file.write_text("\n".join(lines))
    print(f"  ✅ 添加 @spec: {feature_file.name} → {anchor}")
    return True


def main():
    features_dir = Path("openspec/changes/kanban/features")

    print("为所有 .feature 文件添加 @spec 头部链接...")
    updated = 0
    for feature_file in features_dir.glob("**/*.feature"):
        rel_path = feature_file.relative_to(features_dir)
        anchor = FEATURE_TO_SPEC_ANCHOR.get(str(rel_path))
        if anchor:
            if add_spec_header(feature_file, anchor):
                updated += 1
        else:
            print(f"  ⚠️  无映射: {rel_path}")

    print(f"\n完成: {updated} 个文件已更新")


if __name__ == "__main__":
    main()
