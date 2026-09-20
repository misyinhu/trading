#!/usr/bin/env python3
"""
Webhook 交易功能测试
TDD - 先写测试，再实现功能
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import unittest
from unittest.mock import Mock, patch, MagicMock
from flask import Flask


class TestWebhookTrading(unittest.TestCase):
    """测试 Webhook 交易功能"""

    def setUp(self):
        """每个测试前初始化"""
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        
        # Mock IB 连接和飞书发送
        self.mock_ib = Mock()
        self.mock_ib.positions.return_value = []
        self.mock_ib.placeOrder.return_value = self._create_mock_trade()
        
        # Patch 所有外部依赖
        self.patches = [
            patch('client.ib_connection.get_ib_connection', return_value=self.mock_ib),
            patch('notify.webhook_bridge.send_feishu', return_value=(True, "OK")),
            patch('notify.webhook_bridge.get_tenant_token', return_value="mock_token"),
        ]
        
        for p in self.patches:
            p.start()
    
    def tearDown(self):
        """每个测试后清理"""
        for p in self.patches:
            p.stop()
    
    def _create_mock_trade(self):
        """创建模拟的交易对象"""
        mock_trade = Mock()
        mock_trade.orderStatus.status = 'Filled'
        mock_trade.orderStatus.filled = 1
        mock_trade.orderStatus.remaining = 0
        mock_trade.order.orderId = 123
        mock_trade.order.action = 'BUY'
        mock_trade.order.totalQuantity = 1
        mock_trade.log = []
        return mock_trade

    def test_parse_gc_buy_command(self):
        """测试解析买入 GC 命令"""
        from notify.nl_parser import parse_trading_command
        
        result = parse_trading_command("买入1手GC")
        self.assertEqual(result['action'], 'BUY')
        self.assertEqual(result['symbol'], 'GC')
        self.assertEqual(result['quantity'], 1)
    
    def test_parse_es_sell_command(self):
        """测试解析卖出 ES 命令"""
        from notify.nl_parser import parse_trading_command
        
        result = parse_trading_command("卖出1手ES")
        self.assertEqual(result['action'], 'SELL')
        self.assertEqual(result['symbol'], 'ES')
        self.assertEqual(result['quantity'], 1)
    
    def test_parse_mnq_buy_command(self):
        """测试解析买入 MNQ 命令"""
        from notify.nl_parser import parse_trading_command
        
        result = parse_trading_command("买入1手MNQ")
        self.assertEqual(result['action'], 'BUY')
        self.assertEqual(result['symbol'], 'MNQ')
        self.assertEqual(result['quantity'], 1)
    
    def test_parse_cl_close_command(self):
        """测试解析平仓 CL 命令"""
        from notify.nl_parser import parse_trading_command
        
        result = parse_trading_command("平仓CL")
        self.assertEqual(result['action'], 'CLOSE')
        self.assertEqual(result['symbol'], 'CL')
    
    def test_exchange_mapper_gc(self):
        """测试 GC 交易所映射"""
        from orders.exchange_mapper import get_exchange_for_symbol
        
        exchange = get_exchange_for_symbol('GC', 'FUT')
        self.assertEqual(exchange, 'COMEX')
    
    def test_exchange_mapper_es(self):
        """测试 ES 交易所映射"""
        from orders.exchange_mapper import get_exchange_for_symbol
        
        exchange = get_exchange_for_symbol('ES', 'FUT')
        self.assertEqual(exchange, 'CME')
    
    def test_exchange_mapper_mnq(self):
        """测试 MNQ 交易所映射"""
        from orders.exchange_mapper import get_exchange_for_symbol
        
        exchange = get_exchange_for_symbol('MNQ', 'FUT')
        self.assertEqual(exchange, 'CME')
    
    def test_exchange_mapper_mgc(self):
        """测试 MGC 交易所映射（智能推断）"""
        from orders.exchange_mapper import get_exchange_for_symbol
        
        exchange = get_exchange_for_symbol('MGC', 'FUT')
        self.assertEqual(exchange, 'COMEX')
    
    def test_exchange_mapper_6e(self):
        """测试 6E 交易所映射（外汇期货）"""
        from orders.exchange_mapper import get_exchange_for_symbol
        
        exchange = get_exchange_for_symbol('6E', 'FUT')
        self.assertEqual(exchange, 'CME')
    
    def test_exchange_mapper_cl(self):
        """测试 CL 交易所映射"""
        from orders.exchange_mapper import get_exchange_for_symbol
        
        exchange = get_exchange_for_symbol('CL', 'FUT')
        self.assertEqual(exchange, 'NYMEX')


class TestWebhookEndpoint(unittest.TestCase):
    """测试 Webhook 端点"""

    @patch('client.ib_connection.get_ib_connection')
    @patch('notify.webhook_bridge.send_feishu')
    @patch('notify.webhook_bridge.get_tenant_token')
    def test_feishu_webhook_buy_gc(self, mock_token, mock_send, mock_ib):
        """测试飞书 Webhook 买入 GC"""
        # Setup mocks
        mock_token.return_value = "mock_token"
        mock_send.return_value = (True, "OK")
        
        mock_ib_instance = Mock()
        mock_ib_instance.positions.return_value = []
        
        mock_trade = Mock()
        mock_trade.orderStatus.status = 'Filled'
        mock_trade.orderStatus.filled = 1
        mock_trade.order.orderId = 456
        mock_ib_instance.placeOrder.return_value = mock_trade
        mock_ib.return_value = mock_ib_instance
        
        # 创建测试客户端
        from notify.webhook_bridge import app
        app.config['TESTING'] = True
        client = app.test_client()
        
        # 发送测试请求
        response = client.post(
            '/feishu-webhook',
            data=json.dumps({
                "header": {"event_type": "im.message.receive_v1"},
                "event": {
                    "message": {
                        "message_id": "test_buy_gc_001",
                        "chat_id": "oc_test123",
                        "content": json.dumps({"text": "买入1手GC"})
                    }
                }
            }),
            content_type='application/json'
        )
        
        # 验证响应
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.data)
        self.assertEqual(response_data.get('status'), 'ok')
        
        # 验证飞书消息发送
        mock_send.assert_called()
        call_args = mock_send.call_args[0]
        self.assertIn('GC', call_args[0])
        self.assertIn('COMEX', call_args[0])
    
    @patch('client.ib_connection.get_ib_connection')
    @patch('notify.webhook_bridge.send_feishu')
    @patch('notify.webhook_bridge.get_tenant_token')
    def test_feishu_webhook_sell_es(self, mock_token, mock_send, mock_ib):
        """测试飞书 Webhook 卖出 ES"""
        mock_token.return_value = "mock_token"
        mock_send.return_value = (True, "OK")
        
        mock_ib_instance = Mock()
        mock_ib_instance.positions.return_value = []
        
        mock_trade = Mock()
        mock_trade.orderStatus.status = 'Filled'
        mock_trade.orderStatus.filled = 1
        mock_trade.order.orderId = 789
        mock_ib_instance.placeOrder.return_value = mock_trade
        mock_ib.return_value = mock_ib_instance
        
        from notify.webhook_bridge import app
        app.config['TESTING'] = True
        client = app.test_client()
        
        response = client.post(
            '/feishu-webhook',
            data=json.dumps({
                "header": {"event_type": "im.message.receive_v1"},
                "event": {
                    "message": {
                        "message_id": "test_sell_es_001",
                        "chat_id": "oc_test456",
                        "content": json.dumps({"text": "卖出1手ES"})
                    }
                }
            }),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.data)
        self.assertEqual(response_data.get('status'), 'ok')
        
        # 验证使用正确的交易所
        mock_send.assert_called()
        call_args = mock_send.call_args[0]
        self.assertIn('ES', call_args[0])
        self.assertIn('CME', call_args[0])
    
    @patch('notify.webhook_bridge.get_tenant_token')
    def test_health_endpoint(self, mock_token):
        """测试健康检查端点"""
        mock_token.return_value = "mock_token"
        
        from notify.webhook_bridge import app
        app.config['TESTING'] = True
        client = app.test_client()
        
        response = client.get('/health')
        
        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.data)
        self.assertEqual(response_data.get('status'), 'ok')


class TestMultipleSymbols(unittest.TestCase):
    """测试多个不同品种"""

    @patch('client.ib_connection.get_ib_connection')
    @patch('notify.webhook_bridge.send_feishu')
    @patch('notify.webhook_bridge.get_tenant_token')
    def test_various_symbols(self, mock_token, mock_send, mock_ib):
        """测试各种期货品种"""
        test_cases = [
            ("买入1手GC", "COMEX"),
            ("卖出1手ES", "CME"),
            ("买入1手NQ", "CME"),
            ("买入1手MNQ", "CME"),
            ("买入1手YM", "CBOT"),
            ("买入1手MYM", "CBOT"),
            ("买入1手CL", "NYMEX"),
            ("买入1手MCL", "NYMEX"),
            ("卖出1手6E", "CME"),
            ("买入1手ZB", "CBOT"),
        ]
        
        from notify.webhook_bridge import app
        app.config['TESTING'] = True
        client = app.test_client()
        
        mock_token.return_value = "mock_token"
        
        for i, (text, expected_exchange) in enumerate(test_cases):
            # Reset mock
            mock_ib_instance = Mock()
            mock_ib_instance.positions.return_value = []
            mock_trade = Mock()
            mock_trade.orderStatus.status = 'Filled'
            mock_trade.orderStatus.filled = 1
            mock_trade.order.orderId = 100 + i
            mock_ib_instance.placeOrder.return_value = mock_trade
            mock_ib.return_value = mock_ib_instance
            
            response = client.post(
                '/feishu-webhook',
                data=json.dumps({
                    "header": {"event_type": "im.message.receive_v1"},
                    "event": {
                        "message": {
                            "message_id": f"test_{i}",
                            "chat_id": "oc_test",
                            "content": json.dumps({"text": text})
                        }
                    }
                }),
                content_type='application/json'
            )
            
            self.assertEqual(response.status_code, 200, f"Failed for {text}")
            
            # 验证使用了正确的交易所
            mock_send.assert_called()
            call_args = mock_send.call_args[0]
            self.assertIn(expected_exchange, call_args[0], 
                         f"Expected {expected_exchange} in message for {text}")


if __name__ == '__main__':
    unittest.main(verbosity=2)