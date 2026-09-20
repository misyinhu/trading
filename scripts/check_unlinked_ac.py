#!/usr/bin/env python3
"""
检查 SPEC.md 中的 US 是否有对应的 .feature 覆盖
验证 SPEC.md Feature 列引用的文件是否存在
"""

import re
import sys
from pathlib import Path


def get_spec_feature_refs():
    """从 SPEC.md 提取 Feature 列引用的 .feature 文件"""
    refs = set()
    spec_file = Path("openspec/changes/kanban/SPEC.md")

    if not spec_file.exists():
        spec_file = Path("openspec/changes/kanban/spec.md")

    if spec_file.exists():
        content = spec_file.read_text()
        # 匹配 [xxx.feature](features/...)
        pattern = r"\[([^\]]+\.feature)\]\((features/[^\)]+)\)"
        for match in re.finditer(pattern, content):
            refs.add(match.group(2))

    return refs


def check_unlinked_ac():
    spec_refs = get_spec_feature_refs()

    missing = []
    for ref in sorted(spec_refs):
        feature_path = Path("openspec/changes/kanban") / ref
        if not feature_path.exists():
            missing.append(ref)

    if missing:
        print(f"❌ 发现 {len(missing)} 个 .feature 文件缺失:")
        for f in missing:
            print(f"   {f}")
        return 1

    print(f"✅ 所有 {len(spec_refs)} 个引用的 .feature 文件都存在")
    return 0


if __name__ == "__main__":
    sys.exit(check_unlinked_ac())
