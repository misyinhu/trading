# 详细测试用例设计文档

## 概述

本文档为现存代码提供详细的测试用例设计，包括单元测试、集成测试和端到端测试。

## 测试框架选择

- **主要框架**: pytest
- **Mock 工具**: unittest.mock / pytest-mock
- **覆盖率工具**: pytest-cov
- **参数化测试**: pytest.mark.parametrize

## 目录结构设计

```
tests/
├── __init__.py
├── conftest.py                    # pytest 配置和 fixtures
├── test_data/                     # 测试数据
│   ├── sample_config.json
│   ├── sample_prices.csv
│   └── nlp_samples.json
├── unit/                          # 单元测试
│   ├── __init__.py
│   ├── test_spread_engine.py
│   ├── test_config_parser.py
│   ├── test_feishu_client.py
│   ├── test_webhook_bridge.py
│   ├── test_nlp_parser.py
│   └── test_cli_main.py
├── integration/                   # 集成测试
│   ├── __init__.py
│   ├── test_flow_nlp_to_trade.py
│   ├── test_webhook_to_feishu.py
│   └── test_config_to_engine.py
└── e2e/                          # 端到端测试
    ├── __init__.py
    ├── test_full_flow.py
    └── test_error_handling.py
```

## 详细测试用例设计

### 1. 核心功能测试 (test_spread_engine.py)

#### 1.1 SpreadEngine 类测试

```python
import pytest
import pandas as pd
import numpy as np
from universal_spread.core.spread_engine import SpreadEngine

class TestSpreadEngine:
    @pytest.fixture
    def sample_assets(self):
        return {
            "asset1": {
                "symbol": "MNQ",
                "multiplier": 2.0,
                "ratio1": 1
            },
            "asset2": {
                "symbol": "MYM", 
                "multiplier": 0.5,
                "ratio2": 2
            }
        }

    @pytest.fixture
    def spread_engine(self, sample_assets):
        return SpreadEngine(sample_assets["asset1"], sample_assets["asset2"])

    # 测试用例1: 正常价差价值计算
    @pytest.mark.parametrize("price1,price2,expected", [
        (100.0, 50.0, 100.0),  # 100*2.0*1 - 50*0.5*2 = 200 - 50 = 150
        (150.0, 75.0, 225.0),  # 150*2.0*1 - 75*0.5*2 = 300 - 75 = 225
        (200.0, 100.0, 300.0), # 200*2.0*1 - 100*0.5*2 = 400 - 100 = 300
    ])
    def test_calculate_spread_value_normal(self, spread_engine, price1, price2, expected):
        result = spread_engine.calculate_spread_value(price1, price2)
        assert abs(result - expected) < 0.001

    # 测试用例2: 边界条件
    @pytest.mark.parametrize("price1,price2", [
        (0.0, 0.0),
        (1000000.0, 1000000.0),
        (-100.0, 50.0),
    ])
    def test_calculate_spread_value_boundary(self, spread_engine, price1, price2):
        result = spread_engine.calculate_spread_value(price1, price2)
        assert isinstance(result, float)
        assert not np.isnan(result)
        assert not np.isinf(result)

    # 测试用例3: 异常输入
    @pytest.mark.parametrize("price1,price2", [
        (None, 50.0),
        (100.0, None),
        ("invalid", 50.0),
        (100.0, "invalid"),
    ])
    def test_calculate_spread_value_invalid(self, spread_engine, price1, price2):
        with pytest.raises((TypeError, ValueError)):
            spread_engine.calculate_spread_value(price1, price2)

    # 测试用例4: 价差比率计算
    @pytest.mark.parametrize("price1,price2,expected", [
        (100.0, 50.0, 4.0),    # (100*2.0*1) / (50*0.5*2) = 200/50 = 4.0
        (150.0, 75.0, 4.0),    # (150*2.0*1) / (75*0.5*2) = 300/75 = 4.0
    ])
    def test_calculate_spread_ratio_normal(self, spread_engine, price1, price2, expected):
        result = spread_engine.calculate_spread_ratio(price1, price2)
        assert abs(result - expected) < 0.001

    # 测试用例5: 除零处理
    def test_calculate_spread_ratio_zero_division(self, spread_engine):
        result = spread_engine.calculate_spread_ratio(100.0, 0.0)
        assert result == 0.0
```

#### 1.2 HistoricalDeviationDetector 类测试

```python
class TestHistoricalDeviationDetector:
    @pytest.fixture
    def detector(self):
        return HistoricalDeviationDetector(threshold=1000, lookback_days=7)

    @pytest.fixture
    def sample_spread_ratios(self):
        # 创建7天的价差比率数据
        data = [1.0, 1.1, 0.9, 1.2, 0.8, 1.15, 0.85]  # 模拟历史数据
        return pd.Series(data)

    @pytest.fixture
    def extended_spread_ratios(self):
        # 创建15天的价差比率数据
        data = [1.0, 1.1, 0.9, 1.2, 0.8, 1.15, 0.85,  # 前7天
                1.05, 1.25, 0.75, 1.3, 0.7, 1.35, 0.65,  # 后8天
                5.0]  # 当前价差，明显偏离历史
        return pd.Series(data)

    # 测试用例6: 正常信号检测 - MAX_SIGNAL
    def test_detect_opportunity_max_signal(self, detector, extended_spread_ratios):
        result = detector.detect_opportunity(extended_spread_ratios)
        assert result["signal_type"] == "MAX_SIGNAL"
        assert result["threshold_exceeded"] == True
        assert result["action"] == "LONG_ASSET1_SHORT_ASSET2"
        assert "timestamp" in result

    # 测试用例7: 正常信号检测 - MIN_SIGNAL
    def test_detect_opportunity_min_signal(self, detector, extended_spread_ratios):
        # 创建一个触发 MIN_SIGNAL 的序列
        data = [1.0, 1.1, 0.9, 1.2, 0.8, 1.15, 0.85,
                1.05, 1.25, 0.75, 1.3, 0.7, 1.35, 0.65,
                0.1]  # 当前价差，明显低于历史最小值
        spread_ratios = pd.Series(data)
        result = detector.detect_opportunity(spread_ratios)
        assert result["signal_type"] == "MIN_SIGNAL"
        assert result["threshold_exceeded"] == True
        assert result["action"] == "SHORT_ASSET1_LONG_ASSET2"

    # 测试用例8: 无信号检测
    def test_detect_opportunity_no_signal(self, detector, sample_spread_ratios):
        result = detector.detect_opportunity(sample_spread_ratios)
        assert result["signal_type"] == "NO_SIGNAL"
        assert result["threshold_exceeded"] == False
        assert result["action"] == "HOLD"

    # 测试用例9: 数据不足处理
    @pytest.mark.parametrize("data_length", [1, 3, 5])
    def test_detect_opportunity_insufficient_data(self, detector, data_length):
        spread_ratios = pd.Series([1.0] * data_length)
        result = detector.detect_opportunity(spread_ratios)
        assert result["signal_type"] == "NO_SIGNAL"
        assert f"数据不足，需要至少{detector.lookback_days}天历史数据" in result["reason"]

    # 测试用例10: 历史统计信息
    def test_get_historical_stats(self, detector, sample_spread_ratios):
        stats = detector.get_historical_stats(sample_spread_ratios)
        assert "current" in stats
        assert "max_7d" in stats
        assert "min_7d" in stats
        assert "mean_7d" in stats
        assert "std_7d" in stats
        assert stats["current"] == 0.85  # 最后一个值
        assert stats["max_7d"] == 1.2
        assert stats["min_7d"] == 0.8
```

### 2. 配置解析测试 (test_config_parser.py)

```python
import json
import pytest
from pathlib import Path
from universal_spread.config.config_parser import ConfigParser

class TestConfigParser:
    @pytest.fixture
    def valid_config(self):
        return {
            "MNQ": {
                "symbol": "MNQ",
                "exchange": "CME",
                "multiplier": 2.0,
                "ratio1": 1
            },
            "MYM": {
                "symbol": "MYM",
                "exchange": "CME",
                "multiplier": 0.5,
                "ratio2": 2
            }
        }

    @pytest.fixture
    def invalid_config_missing_field(self):
        return {
            "MNQ": {
                "symbol": "MNQ",
                "exchange": "CME"
                # 缺少 multiplier
            }
        }

    # 测试用例11: 有效配置文件解析
    def test_parse_valid_config(self, valid_config, tmp_path):
        config_file = tmp_path / "test_config.json"
        config_file.write_text(json.dumps(valid_config))
        
        parser = ConfigParser(str(config_file))
        result = parser.parse()
        
        assert "MNQ" in result
        assert "MYM" in result
        assert result["MNQ"]["multiplier"] == 2.0

    # 测试用例12: 缺失必需字段
    def test_parse_config_missing_required_field(self, invalid_config_missing_field, tmp_path):
        config_file = tmp_path / "invalid_config.json"
        config_file.write_text(json.dumps(invalid_config_missing_field))
        
        parser = ConfigParser(str(config_file))
        with pytest.raises(ConfigError):
            parser.parse()

    # 测试用例13: 文件不存在
    def test_parse_config_file_not_found(self):
        parser = ConfigParser("nonexistent_file.json")
        with pytest.raises(FileNotFoundError):
            parser.parse()

    # 测试用例14: JSON 格式错误
    def test_parse_config_invalid_json(self, tmp_path):
        config_file = tmp_path / "invalid.json"
        config_file.write_text("{ invalid json }")
        
        parser = ConfigParser(str(config_file))
        with pytest.raises(json.JSONDecodeError):
            parser.parse()
```

### 3. Feishu 客户端测试 (test_feishu_client.py)

```python
import pytest
import requests
from unittest.mock import Mock, patch
from universal_spread.api.feishu_client import FeishuClient

class TestFeishuClient:
    @pytest.fixture
    def feishu_client(self):
        return FeishuClient(
            app_id="test_app_id",
            app_secret="test_app_secret",
            chat_id="test_chat_id"
        )

    # 测试用例15: 发送文本消息成功
    @patch('requests.post')
    def test_send_text_message_success(self, mock_post, feishu_client):
        # Mock 成功响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "msg": "success"}
        mock_post.return_value = mock_response
        
        result = feishu_client.send_text_message("测试消息")
        
        assert result == True
        mock_post.assert_called_once()
        
        # 验证请求参数
        call_args = mock_post.call_args
        assert "Authorization" in call_args[1]["headers"]
        assert "receive_id_type" in call_args[1]["params"]

    # 测试用例16: API 调用失败
    @patch('requests.post')
    def test_send_text_message_api_error(self, mock_post, feishu_client):
        # Mock 失败响应
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"code": 1001, "msg": "invalid parameters"}
        mock_post.return_value = mock_response
        
        result = feishu_client.send_text_message("测试消息")
        
        assert result == False

    # 测试用例17: 网络异常
    @patch('requests.post')
    def test_send_text_message_network_error(self, mock_post, feishu_client):
        # Mock 网络异常
        mock_post.side_effect = requests.ConnectionError("Network error")
        
        result = feishu_client.send_text_message("测试消息")
        
        assert result == False

    # 测试用例18: 重试机制
    @patch('requests.post')
    @patch('time.sleep')
    def test_send_text_message_with_retry(self, mock_sleep, mock_post, feishu_client):
        # 前两次失败，第三次成功
        mock_response_fail = Mock()
        mock_response_fail.status_code = 500
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {"code": 0, "msg": "success"}
        
        mock_post.side_effect = [mock_response_fail, mock_response_fail, mock_response_success]
        
        result = feishu_client.send_text_message("测试消息", max_retries=3)
        
        assert result == True
        assert mock_post.call_count == 3
        assert mock_sleep.call_count == 2
```

### 4. Webhook 桥接测试 (test_webhook_bridge.py)

```python
import pytest
import json
from unittest.mock import Mock, patch
from universal_spread.api.webhook_bridge import WebhookBridge

class TestWebhookBridge:
    @pytest.fixture
    def webhook_bridge(self):
        return WebhookBridge()

    @pytest.fixture
    def valid_webhook_payload(self):
        return {
            "title": "📈 MNQ-2MYM Long Signal",
            "description": "Spread: $1250\n变化: +$1050",
            "time": "2024-02-06 10:30:00"
        }

    @pytest.fixture
    def invalid_webhook_payload(self):
        return {
            "invalid": "payload"
        }

    # 测试用例19: 有效 payload 处理
    @patch.object(WebhookBridge, 'process_nlp_command')
    def test_process_webhook_valid_payload(self, mock_nlp, webhook_bridge, valid_webhook_payload):
        # Mock NLP 处理结果
        mock_nlp.return_value = {"action": "BUY", "symbol": "MNQ", "quantity": 1}
        
        result = webhook_bridge.process_webhook(valid_webhook_payload)
        
        assert result["status"] == "success"
        mock_nlp.assert_called_once_with(valid_webhook_payload)

    # 测试用例20: 无效 payload 处理
    def test_process_webhook_invalid_payload(self, webhook_bridge, invalid_webhook_payload):
        result = webhook_bridge.process_webhook(invalid_webhook_payload)
        
        assert result["status"] == "error"
        assert "error" in result

    # 测试用例21: 空 payload 处理
    def test_process_webhook_empty_payload(self, webhook_bridge):
        result = webhook_bridge.process_webhook({})
        
        assert result["status"] == "error"
        assert "error" in result

    # 测试用例22: NLP 处理异常
    @patch.object(WebhookBridge, 'process_nlp_command')
    def test_process_webhook_nlp_exception(self, mock_nlp, webhook_bridge, valid_webhook_payload):
        mock_nlp.side_effect = Exception("NLP processing failed")
        
        result = webhook_bridge.process_webhook(valid_webhook_payload)
        
        assert result["status"] == "error"
        assert "NLP processing failed" in result["error"]
```

### 5. NLP 解析测试 (test_nlp_parser.py)

```python
import pytest
from universal_spread.nlp.nlp_parser import NLPParser

class TestNLPParser:
    @pytest.fixture
    def nlp_parser(self):
        return NLPParser()

    # 测试用例23: 简单中文指令解析
    @pytest.mark.parametrize("text,expected", [
        ("买入100股AAPL", {"action": "BUY", "symbol": "AAPL", "quantity": 100}),
        ("卖出50股TSLA", {"action": "SELL", "symbol": "TSLA", "quantity": 50}),
        ("平掉AAPL持仓", {"action": "CLOSE", "symbol": "AAPL", "quantity": None}),
        ("买入1手GC", {"action": "BUY", "symbol": "GC", "quantity": 1}),
    ])
    def test_parse_chinese_commands(self, nlp_parser, text, expected):
        result = nlp_parser.parse_command(text)
        assert result["action"] == expected["action"]
        assert result["symbol"] == expected["symbol"]
        assert result["quantity"] == expected["quantity"]

    # 测试用例24: 英文指令解析
    @pytest.mark.parametrize("text,expected", [
        ("Buy 50 TSLA @ Market", {"action": "BUY", "symbol": "TSLA", "quantity": 50}),
        ("Sell 1 BTC", {"action": "SELL", "symbol": "BTC", "quantity": 1}),
        ("Close AAPL position", {"action": "CLOSE", "symbol": "AAPL", "quantity": None}),
    ])
    def test_parse_english_commands(self, nlp_parser, text, expected):
        result = nlp_parser.parse_command(text)
        assert result["action"] == expected["action"]
        assert result["symbol"] == expected["symbol"]
        assert result["quantity"] == expected["quantity"]

    # 测试用例25: 无效指令处理
    @pytest.mark.parametrize("text", [
        "无效指令",
        "hello world",
        "今天天气不错",
        "",
        None,
    ])
    def test_parse_invalid_commands(self, nlp_parser, text):
        result = nlp_parser.parse_command(text)
        assert result["action"] == "UNKNOWN"

    # 测试用例26: 符号识别测试
    @pytest.mark.parametrize("text,symbol", [
        ("买入苹果", "AAPL"),
        ("买入特斯拉", "TSLA"),
        ("买入比特币", "BTC"),
        ("买入以太坊", "ETH"),
        ("买入黄金", "GC"),
        ("买入微型黄金", "MGC"),
    ])
    def test_symbol_recognition(self, nlp_parser, text, symbol):
        result = nlp_parser.parse_command(text)
        assert result["symbol"] == symbol
```

### 6. CLI 主入口测试 (test_cli_main.py)

```python
import pytest
from unittest.mock import Mock, patch
from click.testing import CliRunner
from universal_spread.cli.main import main

class TestCliMain:
    @pytest.fixture
    def runner(self):
        return CliRunner()

    # 测试用例27: 常规参数解析
    def test_cli_with_valid_args(self, runner):
        result = runner.invoke(main, [
            '--asset1', 'MNQ',
            '--asset2', 'MYM',
            '--monitor'
        ])
        
        assert result.exit_code == 0
        assert 'MNQ' in result.output
        assert 'MYM' in result.output

    # 测试用例28: 缺失必要参数
    def test_cli_missing_required_args(self, runner):
        result = runner.invoke(main, [
            '--asset1', 'MNQ'
            # 缺少 asset2
        ])
        
        assert result.exit_code != 0
        assert 'Missing' in result.output or 'required' in result.output.lower()

    # 测试用例29: 帮助信息
    def test_cli_help(self, runner):
        result = runner.invoke(main, ['--help'])
        
        assert result.exit_code == 0
        assert 'asset1' in result.output
        assert 'asset2' in result.output
        assert 'monitor' in result.output

    # 测试用例30: 版本信息
    def test_cli_version(self, runner):
        result = runner.invoke(main, ['--version'])
        
        assert result.exit_code == 0
```

## 集成测试设计

### 1. NLP 到交易流程测试 (test_flow_nlp_to_trade.py)

```python
import pytest
from unittest.mock import Mock, patch
from universal_spread.integration.trade_flow import TradeFlow

class TestTradeFlow:
    @pytest.fixture
    def trade_flow(self):
        return TradeFlow()

    # 测试用例31: 完整的 NLP 到交易流程
    @patch('universal_spread.integration.trade_flow.execute_trade')
    def test_full_nlp_to_trade_flow(self, mock_trade, trade_flow):
        # Mock 交易执行结果
        mock_trade.return_value = {"status": "success", "order_id": "12345"}
        
        result = trade_flow.process_nlp_command("买入100股AAPL")
        
        assert result["status"] == "success"
        mock_trade.assert_called_once_with({
            "action": "BUY",
            "symbol": "AAPL", 
            "quantity": 100
        })

    # 测试用例32: 交易失败处理
    @patch('universal_spread.integration.trade_flow.execute_trade')
    def test_trade_execution_failure(self, mock_trade, trade_flow):
        mock_trade.return_value = {"status": "error", "error": "Insufficient funds"}
        
        result = trade_flow.process_nlp_command("买入100股AAPL")
        
        assert result["status"] == "error"
        assert "Insufficient funds" in result["error"]
```

## 端到端测试设计

### 1. 完整流程测试 (test_full_flow.py)

```python
import pytest
from unittest.mock import Mock, patch
from universal_spread.e2e.full_flow import FullFlow

class TestFullFlow:
    @pytest.fixture
    def full_flow(self):
        return FullFlow()

    # 测试用例33: 完整的 Webhook 到 Feishu 通知流程
    @patch('universal_spread.e2e.full_flow.WebhookBridge')
    @patch('universal_spread.e2e.full_flow.NLPParser')
    @patch('universal_spread.e2e.full_flow.FeishuClient')
    def test_full_webhook_flow(self, mock_feishu, mock_nlp, mock_webhook, full_flow):
        # Mock 各个组件
        mock_webhook.return_value.process_webhook.return_value = {
            "status": "success",
            "parsed_command": {"action": "BUY", "symbol": "AAPL", "quantity": 100}
        }
        mock_feishu.return_value.send_text_message.return_value = True
        
        result = full_flow.process_webhook_to_feishu({
            "title": "Test Signal",
            "description": "Buy signal"
        })
        
        assert result["status"] == "success"
        mock_webhook.return_value.process_webhook.assert_called_once()
        mock_feishu.return_value.send_text_message.assert_called_once()
```

## 错误处理测试 (test_error_handling.py)

```python
import pytest
from unittest.mock import Mock, patch
from universal_spread.error_handling.error_manager import ErrorManager

class TestErrorHandling:
    @pytest.fixture
    def error_manager(self):
        return ErrorManager()

    # 测试用例34: 网络连接错误
    @patch('requests.post')
    def test_network_connection_error(self, mock_post, error_manager):
        mock_post.side_effect = requests.ConnectionError("Network unreachable")
        
        result = error_manager.handle_network_error()
        
        assert result["retry_count"] > 0
        assert result["error_type"] == "network"

    # 测试用例35: 数据格式错误
    def test_data_format_error(self, error_manager):
        invalid_data = {"invalid": "structure"}
        
        result = error_manager.handle_data_format_error(invalid_data)
        
        assert result["error_type"] == "data_format"
        assert "validation" in result["message"].lower()
```

## 性能测试设计

### 1. 计算性能测试 (test_performance.py)

```python
import pytest
import time
import pandas as pd
from universal_spread.core.spread_engine import HistoricalDeviationDetector

class TestPerformance:
    # 测试用例36: 大量数据处理性能
    def test_large_dataset_processing(self):
        # 创建1000天的数据
        large_data = pd.Series([1.0 + i * 0.001 for i in range(1000)])
        detector = HistoricalDeviationDetector()
        
        start_time = time.time()
        result = detector.detect_opportunity(large_data)
        end_time = time.time()
        
        # 处理时间应该小于1秒
        assert end_time - start_time < 1.0
        assert "signal_type" in result

    # 测试用例37: 并发请求处理
    def test_concurrent_request_handling(self):
        # 测试同时处理多个请求的性能
        pass
```

## 测试数据文件

### test_data/sample_config.json
```json
{
  "MNQ": {
    "symbol": "MNQ",
    "exchange": "CME",
    "multiplier": 2.0,
    "ratio1": 1
  },
  "MYM": {
    "symbol": "MYM",
    "exchange": "CME",
    "multiplier": 0.5,
    "ratio2": 2
  }
}
```

### test_data/nlp_samples.json
```json
{
  "chinese_commands": [
    {
      "input": "买入100股AAPL",
      "expected": {"action": "BUY", "symbol": "AAPL", "quantity": 100}
    },
    {
      "input": "卖出50股TSLA",
      "expected": {"action": "SELL", "symbol": "TSLA", "quantity": 50}
    }
  ],
  "english_commands": [
    {
      "input": "Buy 50 TSLA @ Market",
      "expected": {"action": "BUY", "symbol": "TSLA", "quantity": 50}
    }
  ]
}
```

## pytest 配置 (conftest.py)

```python
import pytest
import pandas as pd
import numpy as np

@pytest.fixture
def mock_price_data():
    """提供模拟价格数据"""
    return pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=100, freq='D'),
        'price1': np.random.normal(100, 10, 100),
        'price2': np.random.normal(50, 5, 100)
    })

@pytest.fixture
def mock_config():
    """提供模拟配置数据"""
    return {
        "MNQ": {"symbol": "MNQ", "exchange": "CME", "multiplier": 2.0, "ratio1": 1},
        "MYM": {"symbol": "MYM", "exchange": "CME", "multiplier": 0.5, "ratio2": 2}
    }

# 设置测试标记
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
```

## 运行测试的命令

```bash
# 运行所有测试
pytest

# 运行单元测试
pytest tests/unit/

# 运行集成测试
pytest tests/integration/

# 运行特定测试文件
pytest tests/unit/test_spread_engine.py

# 运行带覆盖率的测试
pytest --cov=universal_spread --cov-report=html

# 运行特定标记的测试
pytest -m "unit"
pytest -m "integration"
pytest -m "not slow"

# 生成覆盖率报告
pytest --cov=universal_spread --cov-report=term-missing

# 运行并行测试
pytest -n auto
```

## 测试覆盖率目标

- **总体覆盖率**: ≥ 80%
- **核心模块覆盖率**: ≥ 90%
- **关键函数覆盖率**: 100%

## 持续集成配置

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, 3.10, 3.11]
    
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v2
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
    
    - name: Run tests
      run: |
        pytest --cov=universal_spread --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v1
      with:
        file: ./coverage.xml
```

这个详细的测试用例设计提供了：

1. **37个具体测试用例**，涵盖正常场景、边界条件、异常处理
2. **完整的项目结构**，包括单元测试、集成测试、端到端测试
3. **详细的参数化测试**，提高测试效率
4. **Mock 策略**，避免外部依赖
5. **性能测试设计**，确保系统性能
6. **CI/CD 配置**，支持持续集成
7. **测试数据管理**，提供可重复的测试环境

接下来可以直接按照这个设计实现具体的测试代码。