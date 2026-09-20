#!/usr/bin/env python3
"""
按 AC 聚合测试通过率报告
读取 JUNIT XML 生成按 AC 聚合的测试报告
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict
import re


def parse_junit_xml(xml_file):
    if not Path(xml_file).exists():
        print(f"⚠️  {xml_file} 不存在，跳过")
        return {}

    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"⚠️  XML 解析错误: {e}")
        return {}

    results = defaultdict(lambda: {"passed": 0, "failed": 0, "total": 0})

    for testcase in root.iter("testcase"):
        classname = testcase.get("classname", "")
        name = testcase.get("name", "")

        tc_match = re.search(r"@TC-([A-Z]{2})-(\d+)", classname + name)
        if not tc_match:
            continue

        module = tc_match.group(1)
        tc_num = tc_match.group(2)
        tc_key = f"{module}-{tc_num}"

        results[tc_key]["total"] += 1

        failure = testcase.find("failure")
        if failure is not None:
            results[tc_key]["failed"] += 1
        else:
            results[tc_key]["passed"] += 1

    return results


def generate_ac_report(results):
    if not results:
        print("⚠️  没有测试结果数据")
        return

    total_tc = len(results)
    passed_tc = sum(1 for r in results.values() if r["failed"] == 0)
    total_tests = sum(r["total"] for r in results.values())
    passed_tests = sum(r["passed"] for r in results.values())

    print("\n" + "=" * 60)
    print("AC 覆盖率报告")
    print("=" * 60)
    print(f"\nTC 总数: {total_tc}")
    print(f"有测试的 TC: {passed_tc} ({passed_tc / total_tc * 100:.1f}%)")
    print(
        f"测试通过率: {passed_tests}/{total_tests} ({passed_tests / total_tests * 100:.1f}%)"
    )

    print("\n" + "-" * 60)
    print(f"{'TC':<15} {'通过':<8} {'失败':<8} {'状态'}")
    print("-" * 60)

    for tc_key in sorted(results.keys()):
        r = results[tc_key]
        status = "✅" if r["failed"] == 0 else "❌"
        print(f"{tc_key:<15} {r['passed']:<8} {r['failed']:<8} {status}")

    print("=" * 60)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="按 AC 聚合测试报告")
    parser.add_argument(
        "xml_file", nargs="?", default="report.xml", help="JUNIT XML 文件路径"
    )
    args = parser.parse_args()

    results = parse_junit_xml(args.xml_file)
    generate_ac_report(results)


if __name__ == "__main__":
    main()
