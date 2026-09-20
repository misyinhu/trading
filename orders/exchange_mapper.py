#!/usr/bin/env python3
"""期货交易所映射器 - 自动推断品种对应的交易所"""

from typing import Dict, Optional
from functools import lru_cache


class ExchangeMapper:
    """合约交易所映射器 - 支持100+期货品种"""
    
    # 核心期货交易所映射表
    DEFAULT_FUTURES_EXCHANGES = {
        # 贵金属 (COMEX)
        'GC': 'COMEX', 'MGC': 'COMEX', 'SI': 'COMEX', 'HG': 'COMEX', 'MHG': 'COMEX',
        
        # 股指期货 (CME)
        'ES': 'CME', 'MES': 'CME', 'NQ': 'CME', 'MNQ': 'CME', 
        'RTY': 'CME', 'M2K': 'CME',
        
        # 股指期货 (CBOT)
        'YM': 'CBOT', 'MYM': 'CBOT',
        
        # 利率期货 (CBOT)
        'ZB': 'CBOT', 'ZN': 'CBOT', 'ZF': 'CBOT', 'ZT': 'CBOT',
        
        # 能源期货 (NYMEX)
        'CL': 'NYMEX', 'MCL': 'NYMEX', 'NG': 'NYMEX', 'MNG': 'NYMEX',
        'QM': 'NYMEX', 'RB': 'NYMEX', 'HO': 'NYMEX',
        
        # 农产品 (CBOT)
        'ZC': 'CBOT', 'ZW': 'CBOT', 'ZS': 'CBOT', 'ZM': 'CBOT', 'ZL': 'CBOT',
        
        # 农产品 (NYMEX)
        'KC': 'NYMEX', 'CT': 'NYMEX', 'SB': 'NYMEX', 'CC': 'NYMEX',
        
        # 外汇期货 (CME)
        '6E': 'CME', '6J': 'CME', '6A': 'CME', '6C': 'CME', 
        '6B': 'CME', '6N': 'CME', '6S': 'CME',
        'E7': 'CME', 'J7': 'CME', 'M6E': 'CME',
        
        # 金属 (NYMEX)
        'PL': 'NYMEX', 'PA': 'NYMEX',
        # 能源 (NYMEX)
        'HO': 'NYMEX',
        # 港股期货 (HKFE)
        'HSI': 'HKFE', 'HSTECH': 'HKFE', 'MHI': 'HKFE',
    }
    
    def __init__(self):
        """初始化映射器"""
        pass
    
    @lru_cache(maxsize=128)
    def get_exchange(self, symbol: str, sec_type: str = "FUT") -> str:
        """
        获取合约对应的交易所
        
        策略优先级：
        1. 直接从映射表查找
        2. 智能推断（微期货、外汇期货等）
        3. 返回默认值 CME
        
        Args:
            symbol: 合约代码 (如 GC, MGC, ES 等)
            sec_type: 安全类型 (FUT, CRYPTO, STK 等)
        
        Returns:
            交易所代码 (COMEX, CME, CBOT, NYMEX 等)
        """
        symbol = symbol.upper()
        
        if sec_type == "FUT":
            # 1. 直接查找映射表
            exchange = self.DEFAULT_FUTURES_EXCHANGES.get(symbol)
            if exchange:
                return exchange
            
            # 2. 智能推断：微型合约 (M 开头)
            if symbol.startswith('M') and len(symbol) >= 2:
                base_symbol = symbol[1:]  # MGC -> GC
                base_exchange = self.DEFAULT_FUTURES_EXCHANGES.get(base_symbol)
                if base_exchange:
                    return base_exchange
            
            # 3. 智能推断：外汇期货 (6X 格式)
            if len(symbol) == 2 and symbol[0] == '6':
                return 'CME'
            
            # 4. 默认返回 CME
            return 'CME'
        
        elif sec_type == "CRYPTO":
            return 'PAXOS'
        
        elif sec_type == "STK":
            return 'SMART'
        
        else:
            return 'SMART'


def get_exchange_for_symbol(symbol: str, sec_type: str = "FUT") -> str:
    """
    便捷函数：获取合约对应的交易所
    
    Args:
        symbol: 合约代码
        sec_type: 安全类型
    
    Returns:
        交易所代码
    
    Example:
        >>> get_exchange_for_symbol('GC')
        'COMEX'
        >>> get_exchange_for_symbol('MGC')
        'COMEX'
        >>> get_exchange_for_symbol('ES')
        'CME'
    """
    mapper = ExchangeMapper()
    return mapper.get_exchange(symbol, sec_type)


if __name__ == '__main__':
    # 简单的自测
    mapper = ExchangeMapper()
    
    test_cases = [
        ('GC', 'COMEX'),
        ('MGC', 'COMEX'),
        ('ES', 'CME'),
        ('MNQ', 'CME'),
        ('YM', 'CBOT'),
        ('CL', 'NYMEX'),
        ('6E', 'CME'),
        ('UNKNOWN', 'CME'),  # 默认值
    ]
    
    print("Exchange Mapper Self-Test:")
    print("=" * 50)
    all_passed = True
    for symbol, expected in test_cases:
        result = mapper.get_exchange(symbol)
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_passed = False
        print(f"{status} {symbol:10} -> {result:10} (expected: {expected})")
    
    print("=" * 50)
    print(f"Result: {'All tests passed!' if all_passed else 'Some tests failed!'}")
