#!/usr/bin/env python3
"""
检查孤儿 .feature 文件（没有被 SPEC.md 引用的 feature）
"""

import re
import sys
from pathlib import Path


def get_spec_feature_refs():
    """从 SPEC.md 中提取被引用的 feature 文件"""
    refs = set()
    spec_file = Path("openspec/changes/kanban/SPEC.md")

    if not spec_file.exists():
        spec_file = Path("openspec/changes/kanban/spec.md")

    if spec_file.exists():
        content = spec_file.read_text()
        pattern = r"\[([A-Z]{2}-US\d+(?:-\d+)?\.feature)\]"
        refs.update(re.findall(pattern, content))

    return refs


def check_orphan_features():
    orphan_features = []
    features_dir = Path("openspec/changes/kanban/features")

    if not features_dir.exists():
        print("⚠️ features 目录不存在，跳过检查")
        return 0

    spec_refs = get_spec_feature_refs()

    for feature_file in features_dir.glob("**/*.feature"):
        rel_path = feature_file.relative_to(features_dir)
        feature_name = rel_path.name

        if feature_name not in spec_refs:
            orphan_features.append(str(rel_path))

    if orphan_features:
        print(
            f"❌ 发现 {len(orphan_features)} 个孤儿 feature 文件（未被 SPEC.md 引用）:"
        )
        for f in orphan_features:
            print(f"   {f}")
        return 1

    print("✅ 所有 feature 文件都被 SPEC.md 引用")
    return 0


if __name__ == "__main__":
    sys.exit(check_orphan_features())
