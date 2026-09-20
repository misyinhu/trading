#!/usr/bin/env python3
"""
测试期货交易所自动映射系统
TDD - 先写测试，看测试失败，再实现功能
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import unittest
from orders.exchange_mapper import ExchangeMapper


class TestExchangeMapper(unittest.TestCase):
    """测试交易所映射器"""
    
    def setUp(self):
        """每个测试前初始化"""
        self.mapper = ExchangeMapper()
    
    # ==================== 贵金属期货 (COMEX) ====================
    def test_gc_maps_to_comex(self):
        """GC (黄金) 应该映射到 COMEX"""
        self.assertEqual(self.mapper.get_exchange('GC'), 'COMEX')
    
    def test_mgc_maps_to_comex(self):
        """MGC (微型黄金) 应该映射到 COMEX"""
        self.assertEqual(self.mapper.get_exchange('MGC'), 'COMEX')
    
    def test_si_maps_to_comex(self):
        """SI (白银) 应该映射到 COMEX"""
        self.assertEqual(self.mapper.get_exchange('SI'), 'COMEX')
    
    def test_hg_maps_to_comex(self):
        """HG (铜) 应该映射到 COMEX"""
        self.assertEqual(self.mapper.get_exchange('HG'), 'COMEX')
    
    def test_mhg_maps_to_comex(self):
        """MHG (微型铜) 应该映射到 COMEX"""
        self.assertEqual(self.mapper.get_exchange('MHG'), 'COMEX')
    
    # ==================== 股指期货 (CME) ====================
    def test_es_maps_to_cme(self):
        """ES (标普500) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('ES'), 'CME')
    
    def test_mes_maps_to_cme(self):
        """MES (微型标普) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('MES'), 'CME')
    
    def test_nq_maps_to_cme(self):
        """NQ (纳斯达克) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('NQ'), 'CME')
    
    def test_mnq_maps_to_cme(self):
        """MNQ (微型纳斯达克) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('MNQ'), 'CME')
    
    def test_rty_maps_to_cme(self):
        """RTY (罗素2000) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('RTY'), 'CME')
    
    def test_m2k_maps_to_cme(self):
        """M2K (微型罗素) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('M2K'), 'CME')
    
    # ==================== 股指期货 (CBOT) ====================
    def test_ym_maps_to_cbot(self):
        """YM (道琼斯) 应该映射到 CBOT"""
        self.assertEqual(self.mapper.get_exchange('YM'), 'CBOT')
    
    def test_mym_maps_to_cbot(self):
        """MYM (微型道琼斯) 应该映射到 CBOT"""
        self.assertEqual(self.mapper.get_exchange('MYM'), 'CBOT')
    
    # ==================== 利率期货 (CBOT) ====================
    def test_zb_maps_to_cbot(self):
        """ZB (30年国债) 应该映射到 CBOT"""
        self.assertEqual(self.mapper.get_exchange('ZB'), 'CBOT')
    
    def test_zn_maps_to_cbot(self):
        """ZN (10年国债) 应该映射到 CBOT"""
        self.assertEqual(self.mapper.get_exchange('ZN'), 'CBOT')
    
    def test_zf_maps_to_cbot(self):
        """ZF (5年国债) 应该映射到 CBOT"""
        self.assertEqual(self.mapper.get_exchange('ZF'), 'CBOT')
    
    def test_zt_maps_to_cbot(self):
        """ZT (2年国债) 应该映射到 CBOT"""
        self.assertEqual(self.mapper.get_exchange('ZT'), 'CBOT')
    
    # ==================== 能源期货 (NYMEX) ====================
    def test_cl_maps_to_nymex(self):
        """CL (原油) 应该映射到 NYMEX"""
        self.assertEqual(self.mapper.get_exchange('CL'), 'NYMEX')
    
    def test_mcl_maps_to_nymex(self):
        """MCL (微型原油) 应该映射到 NYMEX"""
        self.assertEqual(self.mapper.get_exchange('MCL'), 'NYMEX')
    
    def test_ng_maps_to_nymex(self):
        """NG (天然气) 应该映射到 NYMEX"""
        self.assertEqual(self.mapper.get_exchange('NG'), 'NYMEX')
    
    def test_mng_maps_to_nymex(self):
        """MNG (微型天然气) 应该映射到 NYMEX"""
        self.assertEqual(self.mapper.get_exchange('MNG'), 'NYMEX')
    
    def test_qm_maps_to_nymex(self):
        """QM (轻质原油) 应该映射到 NYMEX"""
        self.assertEqual(self.mapper.get_exchange('QM'), 'NYMEX')
    
    def test_rb_maps_to_nymex(self):
        """RB (汽油) 应该映射到 NYMEX"""
        self.assertEqual(self.mapper.get_exchange('RB'), 'NYMEX')
    
    def test_ho_maps_to_nymex(self):
        """HO (取暖油) 应该映射到 NYMEX"""
        self.assertEqual(self.mapper.get_exchange('HO'), 'NYMEX')
    
    # ==================== 外汇期货 (CME) ====================
    def test_6e_maps_to_cme(self):
        """6E (欧元) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('6E'), 'CME')
    
    def test_6j_maps_to_cme(self):
        """6J (日元) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('6J'), 'CME')
    
    def test_6a_maps_to_cme(self):
        """6A (澳元) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('6A'), 'CME')
    
    def test_6c_maps_to_cme(self):
        """6C (加元) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('6C'), 'CME')
    
    def test_6b_maps_to_cme(self):
        """6B (英镑) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('6B'), 'CME')
    
    def test_6n_maps_to_cme(self):
        """6N (纽元) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('6N'), 'CME')
    
    def test_6s_maps_to_cme(self):
        """6S (瑞郎) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('6S'), 'CME')
    
    def test_e7_maps_to_cme(self):
        """E7 (迷你欧元) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('E7'), 'CME')
    
    def test_j7_maps_to_cme(self):
        """J7 (迷你日元) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('J7'), 'CME')
    
    def test_m6e_maps_to_cme(self):
        """M6E (微型欧元) 应该映射到 CME"""
        self.assertEqual(self.mapper.get_exchange('M6E'), 'CME')
    
    # ==================== 农产品期货 (CBOT) ====================
    def test_zc_maps_to_cbot(self):
        """ZC (玉米) 应该映射到 CBOT"""
        self.assertEqual(self.mapper.get_exchange('ZC'), 'CBOT')
    
    def test_zw_maps_to_cbot(self):
        """ZW (小麦) 应该映射到 CBOT"""
        self.assertEqual(self.mapper.get_exchange('ZW'), 'CBOT')
    
    def test_zs_maps_to_cbot(self):
        """ZS (大豆) 应该映射到 CBOT"""
        self.assertEqual(self.mapper.get_exchange('ZS'), 'CBOT')
    
    def test_zm_maps_to_cbot(self):
        """ZM (豆粕) 应该映射到 CBOT"""
        self.assertEqual(self.mapper.get_exchange('ZM'), 'CBOT')
    
    def test_zl_maps_to_cbot(self):
        """ZL (豆油) 应该映射到 CBOT"""
        self.assertEqual(self.mapper.get_exchange('ZL'), 'CBOT')
    
    # ==================== 金属期货 (NYMEX) ====================
    def test_pl_maps_to_nymex(self):
        """PL (铂金) 应该映射到 NYMEX"""
        self.assertEqual(self.mapper.get_exchange('PL'), 'NYMEX')
    
    def test_pa_maps_to_nymex(self):
        """PA (钯金) 应该映射到 NYMEX"""
        self.assertEqual(self.mapper.get_exchange('PA'), 'NYMEX')
    
    # ==================== 未知品种的默认行为 ====================
    def test_unknown_symbol_defaults_to_cme(self):
        """未知品种默认应该返回 CME"""
        self.assertEqual(self.mapper.get_exchange('UNKNOWN'), 'CME')
    
    def test_case_insensitive(self):
        """测试不区分大小写"""
        self.assertEqual(self.mapper.get_exchange('gc'), 'COMEX')
        self.assertEqual(self.mapper.get_exchange('Gc'), 'COMEX')
        self.assertEqual(self.mapper.get_exchange('gC'), 'COMEX')
    
    # ==================== 加密货币 ====================
    def test_btc_maps_to_paxos(self):
        """BTC 应该映射到 PAXOS"""
        self.assertEqual(self.mapper.get_exchange('BTC', 'CRYPTO'), 'PAXOS')
    
    def test_eth_maps_to_paxos(self):
        """ETH 应该映射到 PAXOS"""
        self.assertEqual(self.mapper.get_exchange('ETH', 'CRYPTO'), 'PAXOS')


class TestExchangeMapperSmartDetection(unittest.TestCase):
    """测试智能推断功能"""
    
    def setUp(self):
        self.mapper = ExchangeMapper()
    
    def test_micro_contract_inference(self):
        """测试微型合约推断：M + 基础合约"""
        # MGC -> GC 的交易所
        self.assertEqual(self.mapper.get_exchange('MGC'), 'COMEX')
        # MNQ -> NQ 的交易所  
        self.assertEqual(self.mapper.get_exchange('MNQ'), 'CME')
        # MCL -> CL 的交易所
        self.assertEqual(self.mapper.get_exchange('MCL'), 'NYMEX')
    
    def test_fx_futures_inference(self):
        """测试外汇期货推断：6X 格式"""
        # 所有 6E, 6J, 6A 等都应该映射到 CME
        self.assertEqual(self.mapper.get_exchange('6E'), 'CME')
        self.assertEqual(self.mapper.get_exchange('6J'), 'CME')
        self.assertEqual(self.mapper.get_exchange('6A'), 'CME')


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
