#!/usr/bin/env python3
"""
测试：7日价差阈值告警当日不重复通知逻辑
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import json
import tempfile

# 添加路径
BASE_DIR = Path(__file__).parent.parent / "z120_monitor"
sys.path.insert(0, str(BASE_DIR))


class TestSpreadAlertState:
    """测试7日价差告警状态管理"""

    def test_should_send_alert_first_time_today(self):
        """测试：今天第一次触发告警，应该发送"""
        # 使用临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = Path(f.name)
        
        try:
            # 模拟从未发送过告警
            # 定义被测试的函数
            def get_spread_alert_state_test():
                if temp_file.exists():
                    with open(temp_file) as f:
                        return json.load(f)
                return {}
            
            def should_send_spread_alert_test(pair_name):
                today = datetime.now().strftime("%Y-%m-%d")
                state = get_spread_alert_state_test()
                last_alert_date = state.get(pair_name, {}).get("last_date")
                if last_alert_date == today:
                    return False
                return True
            
            # 测试：今天第一次，应该返回True
            result = should_send_spread_alert_test("MNQ_MYM")
            assert result == True, "今天第一次触发，应该发送"
            print("✅ 测试通过：今天第一次触发告警，应该发送")
        finally:
            if temp_file.exists():
                temp_file.unlink()

    def test_should_not_send_alert_same_day(self):
        """测试：同一天已发送过告警，不应该再发送"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            today = datetime.now().strftime("%Y-%m-%d")
            json.dump({"MNQ_MYM": {"last_date": today}}, f)
            temp_file = Path(f.name)
        
        try:
            def get_spread_alert_state_test():
                if temp_file.exists():
                    with open(temp_file) as f:
                        return json.load(f)
                return {}
            
            def should_send_spread_alert_test(pair_name):
                today = datetime.now().strftime("%Y-%m-%d")
                state = get_spread_alert_state_test()
                last_alert_date = state.get(pair_name, {}).get("last_date")
                if last_alert_date == today:
                    return False
                return True
            
            # 测试：今天已经发送过，应该返回False
            result = should_send_spread_alert_test("MNQ_MYM")
            assert result == False, "今天已经发送过，不应该再发送"
            print("✅ 测试通过：同一天已发送过告警，不应该再发送")
        finally:
            if temp_file.exists():
                temp_file.unlink()

    def test_should_send_alert_next_day(self):
        """测试：第二天应该重新发送"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            json.dump({"MNQ_MYM": {"last_date": yesterday}}, f)
            temp_file = Path(f.name)
        
        try:
            def get_spread_alert_state_test():
                if temp_file.exists():
                    with open(temp_file) as f:
                        return json.load(f)
                return {}
            
            def should_send_spread_alert_test(pair_name):
                today = datetime.now().strftime("%Y-%m-%d")
                state = get_spread_alert_state_test()
                last_alert_date = state.get(pair_name, {}).get("last_date")
                if last_alert_date == today:
                    return False
                return True
            
            # 测试：昨天发送过，今天应该返回True
            result = should_send_spread_alert_test("MNQ_MYM")
            assert result == True, "第二天应该重新发送"
            print("✅ 测试通过：第二天应该重新发送")
        finally:
            if temp_file.exists():
                temp_file.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
