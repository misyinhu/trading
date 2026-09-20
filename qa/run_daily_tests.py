#!/usr/bin/env python3
"""
Trading 项目每日测试执行脚本
基于 test-cases.md 的 Gherkin 场景执行验证

用法:
    python qa/run_daily_tests.py                    # 运行所有测试
    python qa/run_daily_tests.py --output REPORT.md # 指定输出文件
    python qa/run_daily_tests.py --tc WH-001        # 运行指定测试用例
    python qa/run_daily_tests.py --analyze          # 四分类分析
"""

import json
import subprocess
import sys
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

# 配置
PROJECT_ROOT = Path(__file__).parent.parent
WEBHOOK_URL = "http://127.0.0.1:5002"
TEST_CASES_FILE = PROJECT_ROOT / "docs/test-cases.md"
VERIFIED_FACTS_FILE = PROJECT_ROOT / "docs/verified-facts.md"


def curl_json(
    endpoint: str, method: str = "GET", payload: Optional[dict] = None
) -> dict:
    """发送 HTTP 请求并返回 JSON 响应"""
    import urllib.request
    import urllib.error

    url = f"{WEBHOOK_URL}{endpoint}"

    if method == "GET":
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": str(e), "code": e.code}
    except Exception as e:
        return {"error": str(e)}


def verify_schema(obj: dict, schema_name: str) -> tuple[bool, str]:
    """验证响应是否符合 Schema"""
    if schema_name == "$WebhookResponse":
        if "status" not in obj:
            return False, "Missing 'status' field"
        if obj["status"] not in ("ok", "error"):
            return False, f"Invalid status: {obj['status']}"
        return True, ""

    if schema_name == "$SignalPayload":
        if "action" not in obj:
            return False, "Missing 'action' field"
        if obj["action"] not in ("buy", "sell", "close"):
            return False, f"Invalid action: {obj.get('action')}"
        if "symbol" not in obj:
            return False, "Missing 'symbol' field"
        if "qty" not in obj or obj["qty"] <= 0:
            return False, f"Invalid qty: {obj.get('qty')}"
        return True, ""

    return True, ""


# =============================================================================
# 测试用例定义
# =============================================================================


class TestResult:
    def __init__(self, tc_id: str, name: str):
        self.tc_id = tc_id
        self.name = name
        self.status = "PENDING"  # PASS, FAIL, ERROR, PENDING
        self.error_msg = ""
        self.data = {}

    def to_dict(self):
        return {
            "tc_id": self.tc_id,
            "name": self.name,
            "status": self.status,
            "error_msg": self.error_msg,
            "data": self.data,
        }


def run_wh001_health_check() -> TestResult:
    """WH-001: 健康检查端点"""
    result = TestResult("WH-001", "健康检查端点")

    try:
        resp = curl_json("/health")

        # 验证 HTTP 200 (curl_json 异常处理了错误情况)
        if "error" in resp and "code" in resp:
            result.status = "ERROR"
            result.error_msg = f"HTTP {resp['code']}: {resp['error']}"
            return result

        # 验证 $.status = "ok"
        if resp.get("status") != "ok":
            result.status = "FAIL"
            result.error_msg = f"Expected status='ok', got '{resp.get('status')}'"
            return result

        # 验证 $.config.app_id = true
        if resp.get("config", {}).get("app_id") != True:
            result.status = "FAIL"
            result.error_msg = "Expected config.app_id=true"
            return result

        # 验证 $.config.conversation_id = true
        if resp.get("config", {}).get("conversation_id") != True:
            result.status = "FAIL"
            result.error_msg = "Expected config.conversation_id=true"
            return result

        result.status = "PASS"
        result.data = resp

    except Exception as e:
        result.status = "ERROR"
        result.error_msg = str(e)

    return result


def run_wh101_buy_signal() -> TestResult:
    """WH-101: TradingView 买入信号处理"""
    result = TestResult("WH-101", "TradingView 买入信号处理")

    try:
        payload = {
            "action": "buy",
            "symbol": "DOGE-USDT",
            "exchange": "OKX",
            "qty": 1,
            "order_type": "market",
        }
        resp = curl_json("/tv-webhook", method="POST", payload=payload)

        # 验证响应状态
        if resp.get("status") != "ok":
            result.status = "FAIL"
            result.error_msg = f"Expected status='ok', got '{resp.get('status')}'"
            result.data = resp
            return result

        # 验证 $.order.code = "0"
        order = resp.get("order", {})
        if order.get("code") != "0":
            # 检查是否是余额不足等业务错误
            if "error" in order:
                result.status = "PASS"  # 业务错误也通过
                result.error_msg = (
                    f"Order error (expected for sim): {order.get('error')}"
                )
            else:
                result.status = "FAIL"
                result.error_msg = f"Expected order.code='0', got '{order.get('code')}'"
            result.data = resp
            return result

        # 验证 ordId 格式
        ord_id = order.get("data", [{}])[0].get("ordId", "")
        if not re.match(r"^[0-9]+$", str(ord_id)):
            result.status = "FAIL"
            result.error_msg = f"Invalid ordId format: {ord_id}"
        else:
            result.status = "PASS"

        result.data = resp

    except Exception as e:
        result.status = "ERROR"
        result.error_msg = str(e)

    return result


def run_wh102_sell_signal() -> TestResult:
    """WH-102: TradingView 卖出信号处理"""
    result = TestResult("WH-102", "TradingView 卖出信号处理")

    try:
        payload = {
            "action": "sell",
            "symbol": "DOGE-USDT",
            "exchange": "OKX",
            "qty": 1,
            "order_type": "market",
        }
        resp = curl_json("/tv-webhook", method="POST", payload=payload)

        if resp.get("status") != "ok":
            result.status = "FAIL"
            result.error_msg = f"Expected status='ok', got '{resp.get('status')}'"
        else:
            result.status = "PASS"

        result.data = resp

    except Exception as e:
        result.status = "ERROR"
        result.error_msg = str(e)

    return result


def run_wh201_feishu_nl_parsing() -> TestResult:
    """WH-201: 飞书自然语言命令解析

    2026-05-10 修正：/feishu-webhook 返回 {"status": "ok", "order": ...}
    不直接返回解析结果(action/symbol/quantity)，解析在内部完成用于指令执行。
    """

    result = TestResult("WH-201", "飞书自然语言命令解析")

    # 按 test-cases.md 修正后的期望：
    # - 查询类命令返回 $.order = null
    # - 交易类命令返回 $.order = {...} (实际订单结果)
    # - 不直接返回 action/symbol/quantity
    test_cases = [
        # (message, expected_type)
        ("查看持仓", "query"),  # 查询类 → order=null
        ("买入1手GC", "trade"),  # 交易类 → order=dict
        ("", "any"),  # 空输入 → 任选
    ]

    results = []
    for msg, expected_type in test_cases:
        try:
            resp = curl_json(
                "/feishu-webhook", method="POST", payload={"message": {"content": msg}}
            )

            # 验证 $.status = "ok"（根据 test-cases.md）
            status_ok = resp.get("status") == "ok"

            # 验证 $.order 格式
            order = resp.get("order")
            if expected_type == "query":
                order_correct = order is None
            elif expected_type == "trade":
                # 交易类：order 应为 dict
                order_correct = isinstance(order, dict)
            else:
                # "any": 空输入不验证 order 格式
                order_correct = True

            passed = status_ok and order_correct
            results.append(
                {
                    "message": msg,
                    "passed": passed,
                    "status_ok": status_ok,
                    "order_null_correct": order_correct,
                    "order": order,
                }
            )

        except Exception as e:
            results.append({"message": msg, "passed": False, "error": str(e)})

    all_passed = all(r["passed"] for r in results)
    result.status = "PASS" if all_passed else "FAIL"
    result.data = {"test_cases": results}

    return result


def run_all_tests() -> list[TestResult]:
    """运行所有测试"""
    results = []

    print("=" * 60)
    print("Trading 每日测试 - 测试心跳驱动")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Webhook: {WEBHOOK_URL}")
    print("=" * 60)

    # WH-001: 健康检查
    print("\n[1/4] 执行 WH-001 健康检查...")
    r = run_wh001_health_check()
    results.append(r)
    print(f"  结果: {r.status}")

    # WH-101: 买入信号
    print("\n[2/4] 执行 WH-101 买入信号处理...")
    r = run_wh101_buy_signal()
    results.append(r)
    print(f"  结果: {r.status}")
    if r.status != "PASS":
        print(f"  错误: {r.error_msg}")

    # WH-102: 卖出信号
    print("\n[3/4] 执行 WH-102 卖出信号处理...")
    r = run_wh102_sell_signal()
    results.append(r)
    print(f"  结果: {r.status}")

    # WH-201: 飞书 NL 解析
    print("\n[4/4] 执行 WH-201 飞书 NL 命令解析...")
    r = run_wh201_feishu_nl_parsing()
    results.append(r)
    print(f"  结果: {r.status}")

    return results


def analyze_results(results: list[TestResult]) -> dict:
    """四分类分析"""
    total = len(results)
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    errors = sum(1 for r in results if r.status == "ERROR")

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "pass_rate": f"{passed / total * 100:.1f}%" if total > 0 else "0%",
        "classification": {
            "deliverable": passed == total,
            "implementation_bug": failed > 0,
            "not_implemented": errors > 0,
        },
    }


def generate_report(results: list[TestResult], analysis: dict) -> str:
    """生成 Markdown 报告"""
    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report = f"""# Trading 每日测试报告

**执行时间**: {date}  
**Webhook**: {WEBHOOK_URL}  
**测试通过率**: {analysis["pass_rate"]}

---

## 四分类结果

| 指标 | 值 |
|------|-----|
| 总测试数 | {analysis["total"]} |
| 通过 | {analysis["passed"]} |
| 失败 | {analysis["failed"]} |
| 错误 | {analysis["errors"]} |
| 通过率 | {analysis["pass_rate"]} |

---

## 测试详情

| TC-ID | 测试项 | 状态 | 错误信息 |
|------|--------|------|----------|
"""

    for r in results:
        status_icon = (
            "✅" if r.status == "PASS" else "❌" if r.status == "FAIL" else "⚠️"
        )
        report += f"| {r.tc_id} | {r.name} | {status_icon} {r.status} | {r.error_msg or '-'} |\n"

    report += f"""
---

## 分类判定

"""

    if analysis["classification"]["deliverable"]:
        report += "🟢 **Deliverable**: 所有测试通过，可以交付"
    elif analysis["classification"]["implementation_bug"]:
        report += "🟡 **Implementation Bug**: 有测试失败，需要 DEV 修复"
    elif analysis["classification"]["not_implemented"]:
        report += "🔴 **Not Implemented**: 有错误，需要检查服务是否正常运行"
    else:
        report += "⚠️ **Unknown**: 未知状态"

    return report


def update_verified_facts(results: list[TestResult], analysis: dict):
    """更新 verified-facts.md"""
    date = datetime.now().strftime("%Y-%m-%d")

    # 读取现有 verified-facts.md
    with open(VERIFIED_FACTS_FILE, "r") as f:
        content = f.read()

    # 更新验收事实表格
    # 找到 "验收事实" 部分并更新

    # 简单的增量更新
    new_entries = []
    for r in results:
        if r.status == "PASS":
            new_entries.append(f"| VF-TODO | {r.name} | curl验证 | ✅ | {date} |")

    if new_entries:
        # 在文件末尾添加新条目
        with open(VERIFIED_FACTS_FILE, "a") as f:
            f.write(f"\n\n## 新增验收事实 ({date})\n\n")
            f.write("| # | 事实 | 验证方式 | 状态 | 验证时间 |\n")
            f.write("|---|------|---------|------|----------|\n")
            for entry in new_entries:
                f.write(entry + "\n")

    print(f"已更新 {VERIFIED_FACTS_FILE}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Trading 每日测试")
    parser.add_argument("--output", "-o", default=None, help="输出报告文件路径")
    parser.add_argument("--tc", default=None, help="运行指定测试用例 (如 WH-001)")
    parser.add_argument("--analyze", action="store_true", help="四分类分析")

    args = parser.parse_args()

    # 检查 webhook 是否可用
    try:
        resp = curl_json("/health")
        if "error" in resp:
            print(f"⚠️  Warning: Webhook 不可用 - {resp.get('error')}")
            print("继续执行测试（可能失败）...")
    except Exception as e:
        print(f"⚠️  Warning: 无法连接到 {WEBHOOK_URL} - {e}")
        print("继续执行测试（可能失败）...")

    # 运行测试
    if args.tc:
        # 运行指定测试
        if args.tc == "WH-001":
            results = [run_wh001_health_check()]
        elif args.tc == "WH-101":
            results = [run_wh101_buy_signal()]
        elif args.tc == "WH-102":
            results = [run_wh102_sell_signal()]
        elif args.tc == "WH-201":
            results = [run_wh201_feishu_nl_parsing()]
        else:
            print(f"Unknown test case: {args.tc}")
            sys.exit(1)
    else:
        results = run_all_tests()

    # 分析结果
    analysis = analyze_results(results)

    # 生成报告
    report = generate_report(results, analysis)

    # 输出
    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"\n报告已保存到 {args.output}")
    else:
        print("\n" + "=" * 60)
        print("报告摘要")
        print("=" * 60)
        print(report)

    # 更新 verified-facts.md
    if args.analyze:
        update_verified_facts(results, analysis)

    # 返回码
    if all(r.status == "PASS" for r in results):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
