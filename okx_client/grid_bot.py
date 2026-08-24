#!/usr/bin/env python3
"""
DOGE/ETH 比率网格交易机器人 - 实际下单版
"""
import os
import sys
import time
import statistics
import yaml
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from okx_client import OKXTrader


def load_config():
    """从 config.yaml 加载配置"""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)
    
    return {
        "DEMO": True,  # 强制模拟盘
        "THRESHOLD": 0.015,
        "HOLDING_PERIOD": 7200,
        "CHECK_INTERVAL": 15,
        "MARGIN": 400,
        "LEVERAGE": 10,
        "DOGE": "DOGE-USDT",
        "ETH": "ETH-USDT",
        "API_KEY": data['okx']['sim']['apikey'],
        "API_SECRET": data['okx']['sim']['secretkey'],
        "PASSPHRASE": data['okx']['sim']['passphrase'],
        "FLAG": data['okx']['flag']
    }


CONFIG = load_config()


class GridBot:
    def __init__(self):
        # 设置环境变量
        os.environ['OKX_API_KEY'] = CONFIG['API_KEY']
        os.environ['OKX_API_SECRET'] = CONFIG['API_SECRET']
        os.environ['OKX_PASSPHRASE'] = CONFIG['PASSPHRASE']
        
        # 初始化 OKX 客户端
        self.client = OKXTrader(CONFIG["FLAG"])
        
        self.mean_ratio = 0
        self.position = None   # None, "long", "short"
        self.entry_time = 0
        self.entry_ratio = 0
        
    def get_price(self, inst_id):
        """获取当前价格"""
        try:
            data = self.client.get_ticker(inst_id)
            if data.get("code") == "0" and data.get("data"):
                return float(data["data"][0]["last"])
        except Exception as e:
            print(f"获取价格失败: {e}")
        return None
    
    def get_candles(self, inst_id, bar="1H", limit=100):
        """获取K线数据"""
        try:
            data = self.client.get_kline(inst_id, bar=bar, limit=limit)
            if data.get("code") == "0" and data.get("data"):
                return [float(c[4]) for c in data["data"]]
        except Exception as e:
            print(f"获取K线失败: {e}")
        return []
    
    def get_candles_with_history(self, inst_id, bar="1m", target_count=360):
        """获取历史K线数据（通过分页获取足够的历史数据）"""
        all_data = []
        
        # 获取第一批
        try:
            data = self.client.get_history_kline(inst_id, bar=bar, limit=300)
            if data.get("code") == "0" and data.get("data"):
                all_data.extend(data["data"])
        except Exception as e:
            print(f"获取K线失败: {e}")
            return [float(c[4]) for c in all_data]
        
        # 如果需要更多，分页获取
        while len(all_data) < target_count and len(all_data) > 0:
            try:
                earliest_ts = all_data[-1][0]
                more = self.client.get_history_kline(inst_id, bar=bar, limit=300, before=earliest_ts)
                if more.get("code") != "0" or not more.get("data"):
                    break
                new_data = more["data"]
                if not new_data:
                    break
                all_data.extend(new_data)
            except Exception as e:
                print(f"获取K线失败: {e}")
                break
        
        return [float(c[4]) for c in all_data]
    
    def place_order(self, inst_id, side, size):
        """下单"""
        from orders.risk_gate import RiskGate, OrderContext, GateMode
        _risk_gate = RiskGate()
        _risk_ctx = OrderContext(
            symbol=inst_id, action="BUY" if side == "buy" else "SELL",
            quantity=float(size), exchange="OKX",
        )
        _risk_result = _risk_gate.final_check(_risk_ctx, mode=GateMode.STRICT)
        if not _risk_result.allowed:
            print(f"  [RISK BLOCKED] {_risk_result.reason}")
            return False

        try:
            result = self.client.place_order(inst_id, side, str(size), ord_type="market")
            if result.get("code") == "0":
                print(f"  下单成功: {inst_id} {side} {size}")
                return True
            else:
                print(f"  下单失败: {result.get('msg', '未知错误')}")
                return False
        except Exception as e:
            print(f"  下单异常: {e}")
            return False
    
    def init_mean(self):
        """初始化均值"""
        print("获取历史数据 (分页获取360根)...")
        doge_c = self.get_candles_with_history(CONFIG["DOGE"], bar="1m", target_count=360)
        eth_c = self.get_candles_with_history(CONFIG["ETH"], bar="1m", target_count=360)
        
        min_len = min(len(doge_c), len(eth_c))
        
        if min_len >= 100:
            base_doge = doge_c[0]
            base_eth = eth_c[0]
            self.mean_ratio = base_doge / base_eth
            print(f"基准价格({min_len}根K线前): {self.mean_ratio:.8f}")
        else:
            ratios = [doge_c[i]/eth_c[i] for i in range(min_len)]
            self.mean_ratio = statistics.mean(ratios)
            print(f"均值({min_len}根): {self.mean_ratio:.8f}")
    
    def check_signal(self):
        """检查信号"""
        doge = self.get_price(CONFIG["DOGE"])
        eth = self.get_price(CONFIG["ETH"])
        if not doge or not eth:
            print("获取价格失败")
            return
        
        ratio = doge/eth
        dev = (ratio-self.mean_ratio)/self.mean_ratio*100
        
        # 计算信号方向
        signal = None
        if dev < -1.5:
            signal = "long"   # 比率低，做多DOGE + 做空ETH
        elif dev > 1.5:
            signal = "short"  # 比率高，做空DOGE + 做多ETH
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] "
              f"DOGE:${doge:.5f} ETH:${eth:.2f} 比率:{ratio:.8f} 偏离:{dev:+.2f}% "
              f"持仓:{self.position if self.position else '无'}")
        
        # ====== 持仓管理逻辑 ======
        
        # 情况1: 无持仓，有信号 -> 入场
        if not self.position and signal:
            self.enter(signal, ratio)
        
        # 情况2: 有持仓，无信号 -> 检查出场
        elif self.position and not signal:
            self.check_exit(ratio, dev)
        
        # 情况3: 有持仓，有信号 -> 检查是否需要换仓
        elif self.position and signal:
            if self.position == signal:
                # 方向一致，保留持仓
                self.check_exit(ratio, dev)
            else:
                # 方向不一致，先平仓再入场
                print(f"\n[换仓] 持仓方向: {self.position} -> 新信号: {signal}")
                print("先平仓...")
                self.exit(ratio, reason="换仓")
                print("再入场...")
                self.enter(signal, ratio)
    
    def check_exit(self, ratio, dev):
        """检查是否出场"""
        elapsed = time.time() - self.entry_time
        
        # 出场条件: 时间到 或 回归均值
        time_up = elapsed >= CONFIG["HOLDING_PERIOD"]
        back_to_mean = False
        
        if self.position == "long" and dev >= -0.2:
            back_to_mean = True  # 比率回升
        elif self.position == "short" and dev <= 0.2:
            back_to_mean = True  # 比率回落
        
        if time_up:
            self.exit(ratio, reason="时间到期")
        elif back_to_mean:
            self.exit(ratio, reason="回归均值")
    
    def enter(self, pos, ratio):
        """入场"""
        print(f"\n{'='*50}")
        print(f"[入场] {pos} 比率:{ratio:.8f}")
        print(f"{'='*50}")
        
        doge = self.get_price(CONFIG["DOGE"])
        eth = self.get_price(CONFIG["ETH"])
        
        each = CONFIG["MARGIN"] * CONFIG["LEVERAGE"] / 2
        
        # 计算数量
        doge_qty = each / doge
        eth_qty = each / eth
        
        # 调整数量精度
        doge_qty = int(doge_qty)  # DOGE 整数
        eth_qty = round(eth_qty, 4)  # ETH 4位小数
        
        if pos == "long":
            # 做多DOGE + 做空ETH
            print(f"做多DOGE: {doge_qty} ≈ ${each}")
            print(f"做空ETH: {eth_qty} ≈ ${each}")
            
            # 实际下单
            print("执行下单...")
            self.place_order(CONFIG["DOGE"], "buy", doge_qty)
            self.place_order(CONFIG["ETH"], "sell", eth_qty)
        else:
            # 做空DOGE + 做多ETH
            print(f"做空DOGE: {doge_qty} ≈ ${each}")
            print(f"做多ETH: {eth_qty} ≈ ${each}")
            
            # 实际下单
            print("执行下单...")
            self.place_order(CONFIG["DOGE"], "sell", doge_qty)
            self.place_order(CONFIG["ETH"], "buy", eth_qty)
        
        self.position = pos
        self.entry_time = time.time()
        self.entry_ratio = ratio
    
    def exit(self, ratio, reason="出场"):
        """出场"""
        if self.position == "long":
            profit = (ratio - self.entry_ratio) / self.entry_ratio * 100
        else:
            profit = (self.entry_ratio - ratio) / self.entry_ratio * 100
        
        print(f"\n{'='*50}")
        print(f"[{reason}] 比率:{ratio:.8f} 盈亏:{profit:+.2f}%")
        print(f"{'='*50}\n")
        
        # TODO: 实际平仓逻辑（按持仓数量平仓）
        # 目前先打印信息，实际环境中需要记录持仓数量
        
        self.position = None
        self.entry_time = 0
        self.entry_ratio = 0
    
    def run(self):
        print("="*50 + " DOGE/ETH 网格交易机器人 " + "="*50)
        print(f"模式: {'模拟盘' if CONFIG['DEMO'] else '实盘'}")
        print(f"入场阈值: ±{CONFIG['THRESHOLD']*100}%")
        print(f"持仓时间: {CONFIG['HOLDING_PERIOD']/60}分钟")
        print(f"保证金: ${CONFIG['MARGIN']} x {CONFIG['LEVERAGE']}x")
        print("="*50)
        
        self.init_mean()
        print("\n开始监控 (按Ctrl+C停止)...\n")
        
        while True:
            try:
                self.check_signal()
                time.sleep(CONFIG["CHECK_INTERVAL"])
            except KeyboardInterrupt:
                print("\n机器人停止")
                break
            except Exception as e:
                print(f"错误: {e}")
                time.sleep(CONFIG["CHECK_INTERVAL"])


if __name__ == "__main__":
    GridBot().run()
