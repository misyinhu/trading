#!/usr/bin/env python3
"""
验证 SPEC.md AC 表与 Feature 文件的双向链接完整性
AC 映射规则: SPEC AC-N → Feature @AC-{US}-N (同一 US 内的序号对应)
"""

import re
import sys
from pathlib import Path


def parse_spec_ac_table():
    ac_map = {}
    spec_file = Path("openspec/changes/kanban/SPEC.md")

    if not spec_file.exists():
        print("❌ SPEC.md 不存在")
        return ac_map

    content = spec_file.read_text()
    rows = content.split("\n")

    for row in rows:
        if "|" not in row:
            continue
        cols = [c.strip() for c in row.split("|")]
        if len(cols) < 6:
            continue

        us_cell = cols[1]
        ac_cell = cols[2]
        feature_cell = cols[5]

        us_match = re.match(r"([A-Z]{2})-US(\d+)", us_cell)
        # 支持新格式 AC_KB_1 和旧格式 KB-AC1
        ac_match = re.match(r"AC_([A-Z]+)_(\d+)", ac_cell)
        if not ac_match:
            ac_match = re.match(r"([A-Z]{2})-AC(\d+)", ac_cell)

        if us_match and ac_match:
            module = us_match.group(1)
            us_num = us_match.group(2)
            ac_num = ac_match.group(2)

            key = (module, us_num, ac_num)
            ac_map[key] = {
                "spec_ac": f"{module}-AC{ac_num}",
                "feature_ref": feature_cell,
            }

    return ac_map


def check_feature_contains_ac(module, us_num, feature_file, spec_ac_name):
    if not feature_file.exists():
        return False, []

    content = feature_file.read_text()
    # 支持两种格式：
    # 1. 新格式: @AC_KB_1 (直接匹配AC名称)
    # 2. 旧格式: @AC-KB-US1-1 (带US后缀)
    patterns = [
        rf"@AC_{module}_(\d+)",  # 新格式
        rf"@AC-{module}-US{us_num}-(\d+)",  # 旧格式
    ]
    matches = []
    for pattern in patterns:
        found = re.findall(pattern, content)
        matches.extend([f"{module}_AC{m}" for m in found])
    return len(matches) > 0, matches


def find_feature_for_us(module, us_num, features_dir):
    """查找包含该 US 的 feature 文件"""
    if not features_dir.exists():
        return None

    for feature_file in features_dir.glob("**/*.feature"):
        content = feature_file.read_text()
        pattern = rf"@US-{module}-US{us_num}\b"
        if re.search(pattern, content):
            return feature_file
    return None


def verify_bidirectional_link():
    ac_map = parse_spec_ac_table()
    issues = []
    coverage = {}
    features_dir = Path("openspec/changes/kanban/features")

    for (module, us_num, ac_num), info in ac_map.items():
        feature_ref = info["feature_ref"]

        # 解析 feature 路径
        feature_path = None
        if "(" in feature_ref and ")" in feature_ref:
            feature_path_str = feature_ref.split("(")[1].split(")")[0]
            feature_path = Path("openspec/changes/kanban") / feature_path_str
        elif "features/" in feature_ref:
            feature_path = features_dir / feature_ref.replace("features/", "")

        if feature_path and feature_path.exists():
            has_ac, ac_tags = check_feature_contains_ac(
                module, us_num, feature_path, info["spec_ac"]
            )
            if has_ac:
                coverage[(module, us_num, ac_num)] = "ok"
            else:
                coverage[(module, us_num, ac_num)] = "missing_ac"
                issues.append(
                    f"{module}-AC{ac_num} (US{us_num}): Feature存在但无 @AC-{module}-US{us_num}-* 标签"
                )
        else:
            # 查找是否有其他 feature 包含此 US
            alt_feature = find_feature_for_us(module, us_num, features_dir)
            if alt_feature:
                has_ac, ac_tags = check_feature_contains_ac(
                    module, us_num, alt_feature, info["spec_ac"]
                )
                if has_ac:
                    coverage[(module, us_num, ac_num)] = "ok"
                else:
                    coverage[(module, us_num, ac_num)] = "missing_ac"
                    issues.append(
                        f"{module}-AC{ac_num} (US{us_num}): Feature存在但无 @AC-{module}-US{us_num}-* 标签"
                    )
            else:
                if "暂无" in feature_ref or "待建设" in feature_ref:
                    coverage[(module, us_num, ac_num)] = "pending"
                else:
                    coverage[(module, us_num, ac_num)] = "missing_file"
                    issues.append(
                        f"{module}-AC{ac_num} (US{us_num}): Feature文件不存在或未找到"
                    )

    print("=" * 60)
    print("AC-Feature 双向链接验证报告")
    print("=" * 60)

    total = len(ac_map)
    ok = sum(1 for v in coverage.values() if v == "ok")
    pending = sum(1 for v in coverage.values() if v == "pending")
    missing_ac = sum(1 for v in coverage.values() if v == "missing_ac")
    missing_file = sum(1 for v in coverage.values() if v == "missing_file")

    print(f"\n总计: {total} AC")
    print(f"  ✅ 链接正常: {ok}")
    print(f"  ⏳ 待建设: {pending}")
    print(f"  ⚠️  Feature存在但AC标签缺失: {missing_ac}")
    print(f"  ❌ Feature文件缺失: {missing_file}")

    if issues:
        print(f"\n❌ 问题列表:")
        for issue in issues[:10]:
            print(f"   {issue}")
        if len(issues) > 10:
            print(f"   ... 还有 {len(issues) - 10} 个问题")
        return 1

    print(f"\n✅ 所有 AC 都有正确的 Feature 链接")
    return 0


if __name__ == "__main__":
    sys.exit(verify_bidirectional_link())
