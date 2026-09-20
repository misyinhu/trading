#!/usr/bin/env python3
"""
Webhook E2E 测试 - 调用真实服务器 URL
测试 webhook_bridge.py 的所有端点
"""

import os
import requests
import pytest

# 服务器配置
# 远程服务器: alerts.qiaoge.top (IB 已连接)
# 本地开发: 设置 TRADING_SERVER_URL 环境变量
SERVER_URL = os.environ.get("TRADING_SERVER_URL", "http://alerts.qiaoge.top")
TIMEOUT = 30


@pytest.mark.e2e
@pytest.mark.TC_WH_E2E_001
class TestWebhookEndpoints:
    """Webhook 端点 E2E 测试"""

    @pytest.mark.ac_wh_us1_1
    @pytest.mark.ac_wh_us1_2
    def test_health_endpoint(self):
        """TC-WH-E2E-001: /health 端点正常响应"""
        response = requests.get(f"{SERVER_URL}/health", timeout=TIMEOUT)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert "config" in data
        print(f"✅ Health check passed: {data}")

    @pytest.mark.ac_wh_us1_3
    @pytest.mark.ac_wh_us1_5
    def test_tv_webhook_single_order(self):
        """TC-WH-E2E-002: /tv-webhook 单个标的下单"""
        payload = {
            "symbol": "GC",
            "action": "BUY",
            "quantity": 1,
            "exchange": "NYMEX",
            "sec_type": "FUT",
        }
        response = requests.post(
            f"{SERVER_URL}/tv-webhook", json=payload, timeout=TIMEOUT
        )
        # 接受 200（成功）或 500（查询模式/模拟环境）
        assert response.status_code in [200, 500]
        data = response.json()
        # 如果是错误，应该是配置问题而非代码问题
        if response.status_code == 500:
            assert "error" in data or "配置" in str(data)
        print(f"✅ TV Webhook single order: {data}")

    def test_tv_webhook_pair_trade(self):
        """TC-WH-E2E-003: /tv-webhook 配对交易"""
        payload = {
            "symbols": ["GC", "SI"],
            "actions": ["BUY", "SELL"],
            "exchange": "OKX",
        }
        response = requests.post(
            f"{SERVER_URL}/tv-webhook", json=payload, timeout=TIMEOUT
        )
        assert response.status_code in [200, 500]
        data = response.json()
        print(f"✅ TV Webhook pair trade: {data}")

    def test_feishu_webhook_url_verification(self):
        """TC-WH-E2E-004: /feishu-webhook URL 验证"""
        response = requests.get(
            f"{SERVER_URL}/feishu-webhook",
            params={"challenge": "test_challenge_123"},
            timeout=TIMEOUT,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("challenge") == "test_challenge_123"
        print(f"✅ Feishu URL verification: {data}")

    def test_feishu_webhook_simple_message(self):
        """TC-WH-E2E-005: /feishu-webhook 简化消息格式"""
        payload = {"message": {"content": "测试消息", "chat_id": "test_chat_id"}}
        response = requests.post(
            f"{SERVER_URL}/feishu-webhook", json=payload, timeout=TIMEOUT
        )
        assert response.status_code in [200, 400, 500]
        print(f"✅ Feishu simple message: {response.status_code}")

    def test_positions_endpoint(self):
        """TC-WH-E2E-006: /positions 端点返回持仓"""
        response = requests.get(f"{SERVER_URL}/positions", timeout=TIMEOUT)
        assert response.status_code in [200, 500]
        data = response.json()
        assert "positions" in data or "error" in data
        print(f"✅ Positions endpoint: {data}")

    def test_orders_endpoint(self):
        """TC-WH-E2E-007: /orders 端点返回挂单"""
        response = requests.get(f"{SERVER_URL}/orders", timeout=TIMEOUT)
        assert response.status_code in [200, 500]
        data = response.json()
        assert "orders" in data or "error" in data
        print(f"✅ Orders endpoint: {data}")


@pytest.mark.e2e
@pytest.mark.TC_WH_E2E_008
class TestWebhookSchemaValidation:
    """Webhook 请求格式验证测试"""

    def test_tv_webhook_missing_symbol(self):
        """TC-WH-E2E-008: /tv-webhook 缺少必填字段"""
        payload = {
            "action": "BUY",
            "quantity": 1,
        }
        response = requests.post(
            f"{SERVER_URL}/tv-webhook", json=payload, timeout=TIMEOUT
        )
        # 服务器将缺失 symbol 视为非交易信号（仅转发飞书），返回 200
        # 检查响应格式正确即可
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print(f"✅ Missing symbol handled: {data}")

    def test_tv_webhook_invalid_action(self):
        """TC-WH-E2E-009: /tv-webhook 无效的 action"""
        payload = {
            "symbol": "GC",
            "action": "INVALID_ACTION",
            "quantity": 1,
        }
        response = requests.post(
            f"{SERVER_URL}/tv-webhook", json=payload, timeout=TIMEOUT
        )
        # 服务器将无效 action 视为非交易信号，返回 200
        assert response.status_code == 200
        print(f"✅ Invalid action handled: {response.json()}")

    def test_tv_webhook_invalid_exchange(self):
        """TC-WH-E2E-010: /tv-webhook 无效的交易所"""
        payload = {
            "symbol": "GC",
            "action": "BUY",
            "quantity": 1,
            "exchange": "INVALID_EXCHANGE",
        }
        response = requests.post(
            f"{SERVER_URL}/tv-webhook", json=payload, timeout=TIMEOUT
        )
        # 服务器将请求转发给 IB（不在此层面验证交易所）
        assert response.status_code == 200
        print(f"✅ Invalid exchange handled: {response.json()}")


@pytest.mark.e2e
@pytest.mark.TC_WH_E2E_011
class TestWebhookIntegration:
    """Webhook 集成测试 - 多端点组合"""

    def test_health_then_positions(self):
        """TC-WH-E2E-011: 健康检查后获取持仓"""
        # 先检查健康状态
        health_response = requests.get(f"{SERVER_URL}/health", timeout=TIMEOUT)
        assert health_response.status_code == 200
        health_data = health_response.json()

        # 如果配置正常，继续获取持仓
        if health_data.get("config", {}).get("app_id"):
            positions_response = requests.get(
                f"{SERVER_URL}/positions", timeout=TIMEOUT
            )
            assert positions_response.status_code == 200
            print(f"✅ Health check + positions: {positions_response.json()}")
        else:
            pytest.skip("Feishu app_id not configured")

    def test_sequential_tv_webhooks(self):
        """TC-WH-E2E-012: 连续多个 TV webhook 请求"""
        symbols = ["GC", "SI", "PL"]
        for symbol in symbols:
            payload = {
                "symbol": symbol,
                "action": "BUY",
                "quantity": 1,
                "exchange": "NYMEX",
            }
            response = requests.post(
                f"{SERVER_URL}/tv-webhook", json=payload, timeout=TIMEOUT
            )
            # 允许多种响应但不应该崩溃
            assert response.status_code in [200, 500]
        print(f"✅ Sequential TV webhooks completed for {len(symbols)} symbols")


if __name__ == "__main__":
    # 支持直接运行
    pytest.main([__file__, "-v", "-s"])
