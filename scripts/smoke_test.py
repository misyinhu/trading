#!/usr/bin/env python3
"""部署后烟雾测试 — 验证所有核心组件可用。

用法:
    python scripts/smoke_test.py [--url http://localhost:5002]

退出码: 0 = 全部通过, 1 = 有失败
"""
import sys, json, argparse
import requests


def check(url: str, label: str) -> bool:
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if resp.status_code != 200:
            print(f"  ❌ {label}: HTTP {resp.status_code}")
            return False
        print(f"  ✅ {label}: {json.dumps(data, ensure_ascii=False)[:120]}")
        return True
    except Exception as e:
        print(f"  ❌ {label}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Trading 系统烟雾测试")
    parser.add_argument("--url", default="http://localhost:5002", help="trading 服务地址")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    failures = 0

    print(f"🔍 Trading 烟雾测试 — {base}\n")

    # 1. 基础健康检查
    if not check(f"{base}/health", "GET /health"):
        failures += 1

    # 2. 深度健康检查
    if not check(f"{base}/health/full", "GET /health/full"):
        failures += 1

    # 3. 信号提交
    try:
        resp = requests.post(f"{base}/api/signals", json={
            "source": "smoke-test",
            "symbol": "TEST",
            "direction": "long",
            "quantity": 1,
            "reason": "烟雾测试",
            "strategy": "smoke",
        }, timeout=10)
        data = resp.json()
        if resp.status_code in (200, 201) and "signal_id" in data:
            print(f"  ✅ POST /api/signals: signal_id={data['signal_id'][:20]}... status={data.get('status')}")
        else:
            print(f"  ❌ POST /api/signals: {resp.status_code} {json.dumps(data, ensure_ascii=False)[:120]}")
            failures += 1
    except Exception as e:
        print(f"  ❌ POST /api/signals: {e}")
        failures += 1

    # 4. 信号查询（不存在的信号应返回 404）
    try:
        resp = requests.get(f"{base}/api/signals/nonexistent", timeout=10)
        if resp.status_code == 404:
            print(f"  ✅ GET /api/signals/<id>: 正确返回 404")
        else:
            print(f"  ⚠️ GET /api/signals/<id>: HTTP {resp.status_code} (expected 404)")
    except Exception as e:
        print(f"  ❌ GET /api/signals/<id>: {e}")
        failures += 1

    print(f"\n{'✅ 全部通过' if failures == 0 else f'❌ {failures} 项失败'}")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()