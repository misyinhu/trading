#!/usr/bin/env python3
"""
自然语言命令解析测试

测试飞书自然语言指令解析功能
"""

import pytest
import sys
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from notify.nl_parser import (
    parse_trading_command,
    FOREX_SYMBOLS,
    CMDTY_SYMBOLS,
)


class TestNLParserPatterns:
    """自然语言解析 Pattern 测试"""
    
    # ============ 买入指令测试 ============
    
    @pytest.mark.parametrize("command,expected_action", [
        ("买入1手GC", "BUY"),
        ("买入1手GC", "BUY"),
        ("做多1手GC", "BUY"),
        ("买1手GC", "BUY"),
        ("买入GC", "BUY"),
        ("做多GC", "BUY"),
        ("买GC", "BUY"),
    ])
    def test_buy_patterns(self, command, expected_action):
        """测试买入指令匹配"""
        result = parse_trading_command(command)
        assert result["action"] == expected_action
    
    # ============ 卖出指令测试 ============
    
    @pytest.mark.parametrize("command,expected_action", [
        ("卖出1手GC", "SELL"),
        ("卖空1手GC", "SELL"),
        ("做空1手GC", "SELL"),
        ("平仓GC", "CLOSE"),
        ("平掉GC", "CLOSE"),
        ("清仓", "CLOSE"),
    ])
    def test_sell_close_patterns(self, command, expected_action):
        """测试卖出/平仓指令匹配"""
        result = parse_trading_command(command)
        assert result["action"] == expected_action
    
    # ============ 查询指令测试 ============
    
    @pytest.mark.parametrize("command", [
        "查看持仓",
        "查看账户",
        "查看订单",
        "查看成交",
        "账户余额",
        "当前持仓",
    ])
    def test_query_patterns(self, command):
        """测试查询指令匹配"""
        result = parse_trading_command(command)
        assert result["action"] == "QUERY"
    
    # ============ 符号识别测试 ============
    
    def test_forex_symbols_recognition(self):
        """测试外汇符号识别"""
        # EURUSD 应该在符号列表中
        assert "EURUSD" in FOREX_SYMBOLS
        assert "GBPUSD" in FOREX_SYMBOLS
        assert "USDJPY" in FOREX_SYMBOLS
    
    def test_cmdty_symbols_recognition(self):
        """测试商品符号识别"""
        assert "XAUUSD" in CMDTY_SYMBOLS  # 黄金
        assert "XAGUSD" in CMDTY_SYMBOLS  # 白银


class TestNLParserQuantityExtraction:
    """数量提取测试"""
    
    def test_extract_arabic_quantity(self):
        """测试阿拉伯数字数量提取"""
        result = parse_trading_command("买入1手GC")
        assert result["action"] == "BUY"
        assert result["quantity"] == 1
    
    def test_extract_chinese_quantity(self):
        """测试中文数字数量提取"""
        result = parse_trading_command("买入一手GC")
        assert result["action"] == "BUY"
        assert result["quantity"] == 1
    
    def test_extract_quantity_from_amount(self):
        """测试从美元金额提取数量"""
        result = parse_trading_command("买入1000美元EURUSD")
        assert result["action"] == "BUY"
        assert result["usd_amount"] == 1000


class TestNLParserEdgeCases:
    """边界情况测试"""
    
    def test_empty_command(self):
        """测试空指令"""
        result = parse_trading_command("")
        # 空指令应该返回原样或默认值
        assert result is not None
    
    def test_unrecognized_command(self):
        """测试无法识别的指令"""
        result = parse_trading_command("这是一个无法识别的指令")
        # 应该返回 None 或带有错误的结构
        assert result is not None
    
    def test_partial_match(self):
        """测试部分匹配"""
        result = parse_trading_command("买入GC")  # 无数量
        assert result["action"] == "BUY"
        assert "symbol" in result


class TestNLParserSymbolExtraction:
    """符号提取测试"""
    
    def test_gc_symbol_extraction(self):
        """测试 GC (黄金期货) 符号提取"""
        result = parse_trading_command("买入1手GC")
        assert result["symbol"] == "GC"
    
    def test_forex_symbol_extraction(self):
        """测试外汇符号提取"""
        result = parse_trading_command("买入1手EURUSD")
        assert result["symbol"] == "EURUSD"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
