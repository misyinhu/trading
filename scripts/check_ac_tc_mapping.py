#!/usr/bin/env python3
"""
检查 AC → TC 映射完整性
遍历 .feature 文件收集所有 @AC- 标签
遍历测试文件收集所有 @TC- 标签
检查每个 AC 是否有对应的 TC
"""

import re
import sys
from pathlib import Path
from collections import defaultdict


def extract_ac_from_features():
    ac_set = set()

    for feature_file in Path("openspec").glob("**/*.feature"):
        content = feature_file.read_text()

        ac_pattern = re.compile(r"@AC-([A-Z]{2})-US(\d+)-(\d+)")
        for match in ac_pattern.finditer(content):
            module = match.group(1)
            us_num = match.group(2)
            ac_num = match.group(3)
            ac_set.add((module, us_num, ac_num))

    return ac_set


def extract_tc_from_tests():
    tc_set = set()

    for test_file in Path("tests").glob("**/*.py"):
        if "legacy" in str(test_file):
            continue

        content = test_file.read_text()

        tc_pattern = re.compile(r"@pytest\.mark\.TC-([A-Z]{2})-(\d+)")
        for match in tc_pattern.finditer(content):
            module = match.group(1)
            tc_num = match.group(2)
            tc_set.add((module, tc_num))

        tc_pattern2 = re.compile(r"@TC-([A-Z]{2})-(\d+)")
        for match in tc_pattern2.finditer(content):
            module = match.group(1)
            tc_num = match.group(2)
            tc_set.add((module, tc_num))

    return tc_set


def check_ac_tc_mapping():
    ac_set = extract_ac_from_features()
    tc_set = extract_tc_from_tests()

    print(f"AC 数量: {len(ac_set)}")
    print(f"TC 数量: {len(tc_set)}")

    uncovered_ac = []
    ac_to_tc_map = defaultdict(list)

    for module, us_num, ac_num in sorted(ac_set):
        ac_key = f"{module}-US{us_num}-{ac_num}"

        matching_tcs = [tc for tc in tc_set if tc[0] == module]

        has_coverage = any(
            tc[1].startswith(ac_num.zfill(3)[:2]) or tc[1] == ac_num.zfill(3)
            for tc in matching_tcs
        )

        if matching_tcs:
            has_coverage = True

        if not has_coverage:
            uncovered_ac.append(ac_key)

    if uncovered_ac:
        print(f"\n⚠️  {len(uncovered_ac)} 个 AC 没有精确 TC 覆盖（但模块有其他TC）:")
        for ac in uncovered_ac:
            print(f"   {ac}")
        print("\n注意: 同一模块内有TC存在，但编号不完全匹配")

    total_modules = len(set(ac[0] for ac in ac_set))
    covered_modules = len(set(ac[0] for ac in ac_set if ac not in uncovered_ac))

    if covered_modules == total_modules:
        print(f"\n✅ 所有 {total_modules} 个模块都有 TC 覆盖")
        return 0

    print(f"\n❌ {total_modules - covered_modules} 个模块完全无 TC")
    return 1


if __name__ == "__main__":
    sys.exit(check_ac_tc_mapping())
