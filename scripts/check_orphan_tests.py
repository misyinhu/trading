#!/usr/bin/env python3
"""
检查孤儿测试（无 @pytest.mark.TC 标签的测试）
"""

import re
import sys
from pathlib import Path


def check_orphan_tests():
    orphan_tests = []
    test_files = list(Path("tests").glob("**/*.py"))

    for test_file in test_files:
        if "legacy" in str(test_file):
            continue

        content = test_file.read_text()

        if "@pytest.mark" not in content:
            continue

        class_blocks = re.split(r"\nclass ", content)

        for i, block in enumerate(class_blocks):
            if i == 0:
                full_block = block
            else:
                full_block = "class " + block

            class_name_match = re.search(r"class (\w+):", block)
            if not class_name_match:
                continue
            class_name = class_name_match.group(1)

            if "legacy" in class_name.lower():
                continue

            has_class_tc_marker = bool(
                re.search(r"@pytest\.mark\.TC-[A-Z]{2}-\d+", block)
            )

            test_funcs = re.findall(r"def (test_\w+)\(", block)

            for func_name in test_funcs:
                func_start = block.find(f"def {func_name}(")
                func_end = block.find("\n    def ", func_start)
                if func_end == -1:
                    func_end = block.find("\nclass ", func_start)
                if func_end == -1:
                    func_end = len(block)

                func_block = block[func_start:func_end]

                has_method_tc_marker = bool(
                    re.search(r"@pytest\.mark\.TC-[A-Z]{2}-\d+", func_block)
                )
                has_tc_tag = bool(re.search(r"@TC-[A-Z]{2}-\d+", func_block))

                if has_class_tc_marker or has_method_tc_marker or has_tc_tag:
                    continue

                orphan_tests.append((str(test_file), f"{class_name}.{func_name}"))

    if orphan_tests:
        print(f"❌ 发现 {len(orphan_tests)} 个孤儿测试（无 @TC 标签）:")
        for file_path, func_name in orphan_tests:
            print(f"   {file_path}: {func_name}")
        return 1

    print("✅ 所有测试都有 @TC 标签")
    return 0


if __name__ == "__main__":
    sys.exit(check_orphan_tests())
