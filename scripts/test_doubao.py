#!/usr/bin/env python3
"""测试火山引擎豆包大模型 API"""

import os
import json
import requests

# 配置：统一走 ARK_API_KEY（plan/v3 + ark-code-latest），不再硬编码凭证
BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
API_KEY = os.environ.get("ARK_API_KEY", "")

# 测试消息
TEST_MESSAGES = [
    "你好，请介绍一下你自己",
    "平掉BTC仓位",
    "买入1手GC",
]

def chat(prompt: str, model: str = "ark-code-latest") -> dict:
    """调用豆包 API"""
    if not API_KEY:
        raise RuntimeError("未设置 ARK_API_KEY 环境变量")
    url = f"{BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
    }
    
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    return resp.json()


# Trading 意图识别 Prompt
TRADING_PROMPT = """你是一个交易指令解析器。根据用户的消息，识别交易意图。

支持的指令格式：
- 买入/卖出: "买入1手GC", "卖空2手NQ"
- 平仓: "平掉BTC仓位", "平仓GC"
- 查询: "查看持仓", "账户余额"

请以 JSON 格式返回：
{"action": "BUY|SELL|CLOSE|QUERY", "symbol": "标的产品", "quantity": 数量, "raw": "原始消息"}

如果无法识别，返回：{"action": "UNKNOWN", "raw": "原始消息"}
"""


def test_trading_intent():
    """测试交易意图识别"""
    test_cases = [
        "平掉BTC仓位",
        "买入1手GC",
        "查看当前持仓",
        "卖空2手NQ",
        "今天天气怎么样",
    ]
    
    print("\n=== 交易意图识别测试 ===\n")
    for msg in test_cases:
        payload = {
            "model": "ark-code-latest",
            "messages": [
                {"role": "system", "content": TRADING_PROMPT},
                {"role": "user", "content": msg}
            ],
            "temperature": 0.3,
        }
        
        url = f"{BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        }
        
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            result = resp.json()
            
            # 正确解析
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = json.loads(content)
            
            print(f"输入: {msg}")
            print(f"解析: {json.dumps(parsed, ensure_ascii=False)}\n")
        except Exception as e:
            print(f"输入: {msg}")
            print(f"错误: {e}\n")


if __name__ == "__main__":
    # 测试基本对话
    print("=== 基本对话测试 ===")
    result = chat("你好，请用一句话介绍豆包大模型")
    print(result.get("choices", [{}])[0].get("message", {}).get("content", ""))
    
    # 测试交易意图
    test_trading_intent()
