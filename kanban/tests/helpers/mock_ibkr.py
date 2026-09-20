"""
IBKR Mock 实现 - 用于测试交易订单逻辑

提供完整的订单状态机模拟，无需真实 IBKR Gateway 连接。
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import asyncio


class OrderStatus(Enum):
    """订单状态枚举"""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


class OrderSide(Enum):
    """订单方向"""
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class MockContract:
    """Mock IBKR Contract"""
    symbol: str = "AAPL"
    sec_type: str = "STK"
    exchange: str = "SMART"
    currency: str = "USD"
    con_id: int = 0


@dataclass
class MockOrder:
    """Mock IBKR Order"""
    action: str = "BUY"
    total_quantity: float = 100
    order_type: str = "MKT"
    transmit: bool = True


@dataclass
class OrderRecord:
    """订单记录"""
    order_id: str
    symbol: str
    action: str
    quantity: float
    status: OrderStatus
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    submitted_time: datetime = field(default_factory=datetime.now)
    filled_time: Optional[datetime] = None
    error_message: Optional[str] = None


class MockIBKRClient:
    """
    生产级 IBKR Mock - 完整实现交易流程
    
    用于测试完整订单生命周期:
    1. connectAsync() - 连接
    2. placeOrderAsync() - 下单
    3. simulate_fill() - 模拟成交
    4. 状态查询和更新
    """
    
    def __init__(self, initial_balance: float = 1000000.0):
        self._connected = False
        self._orders: Dict[str, OrderRecord] = {}
        self._account_balance = initial_balance
        self._buying_power = initial_balance * 4  # 4x margin
        self._order_id_counter = 1000
        
    # ============ 连接管理 ============
    
    async def connectAsync(self, host: str, port: int, client_id: int) -> bool:
        """模拟连接"""
        await asyncio.sleep(0.01)  # 模拟网络延迟
        self._connected = True
        return True
    
    def disconnect(self):
        """断开连接"""
        self._connected = False
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    # ============ 合约查询 ============
    
    async def reqContractDetailsAsync(self, contract: MockContract) -> List[Dict]:
        """返回模拟合约详情"""
        return [{
            "contract": contract,
            "symbol": contract.symbol,
            "sec_type": contract.sec_type,
            "exchange": contract.exchange,
            "currency": contract.currency,
            "long_name": f"{contract.symbol} Inc.",
            "primary_exchange": "NASDAQ",
            "con_id": 100 + len(contract.symbol),
        }]
    
    # ============ 订单管理 ============
    
    async def placeOrderAsync(
        self,
        order_id: str,
        contract: MockContract,
        order: MockOrder
    ) -> str:
        """
        模拟下单 - 核心方法
        
        Args:
            order_id: 订单 ID
            contract: 合约对象
            order: 订单对象
        
        Returns:
            实际使用的 order_id
        """
        if not self._connected:
            raise ConnectionError("Not connected to IBKR")
        
        actual_order_id = order_id or f"ORD{self._order_id_counter}"
        self._order_id_counter += 1
        
        # 检查资金
        estimated_cost = order.total_quantity * 100  # 简化估算
        if order.action == "BUY" and estimated_cost > self._buying_power:
            record = OrderRecord(
                order_id=actual_order_id,
                symbol=contract.symbol,
                action=order.action,
                quantity=order.total_quantity,
                status=OrderStatus.REJECTED,
                error_message="Insufficient buying power"
            )
            self._orders[actual_order_id] = record
            raise ValueError(f"Order rejected: Insufficient buying power")
        
        record = OrderRecord(
            order_id=actual_order_id,
            symbol=contract.symbol,
            action=order.action,
            quantity=order.total_quantity,
            status=OrderStatus.SUBMITTED,
        )
        self._orders[actual_order_id] = record
        
        return actual_order_id
    
    async def cancelOrderAsync(self, order_id: str) -> bool:
        """取消订单"""
        if order_id not in self._orders:
            return False
        
        record = self._orders[order_id]
        if record.status in [OrderStatus.FILLED, OrderStatus.CANCELLED]:
            return False
        
        record.status = OrderStatus.CANCELLED
        return True
    
    async def reqOpenOrdersAsync(self) -> List[OrderRecord]:
        """查询所有未完成订单"""
        return [
            r for r in self._orders.values()
            if r.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED]
        ]
    
    async def reqAccountSummaryAsync(self) -> Dict[str, Any]:
        """查询账户摘要"""
        return {
            "NetLiquidation": self._account_balance,
            "BuyingPower": self._buying_power,
            "Cash": self._account_balance,
        }
    
    # ============ 测试辅助方法 ============
    
    def simulate_fill(
        self,
        order_id: str,
        fill_price: float,
        fill_qty: Optional[float] = None
    ) -> bool:
        """
        模拟订单成交 - 用于测试
        
        Args:
            order_id: 订单 ID
            fill_price: 成交价格
            fill_qty: 成交数量，默认使用订单全部数量
        
        Returns:
            是否成功模拟成交
        """
        if order_id not in self._orders:
            return False
        
        record = self._orders[order_id]
        
        if fill_qty is None:
            fill_qty = record.quantity
        
        record.filled_qty = fill_qty
        record.avg_fill_price = fill_price
        record.filled_time = datetime.now()
        
        if fill_qty >= record.quantity:
            record.status = OrderStatus.FILLED
        else:
            record.status = OrderStatus.PARTIALLY_FILLED
        
        return True
    
    def simulate_reject(self, order_id: str, error_message: str) -> bool:
        """模拟订单拒绝"""
        if order_id not in self._orders:
            return False
        
        record = self._orders[order_id]
        record.status = OrderStatus.REJECTED
        record.error_message = error_message
        return True
    
    def get_order_status(self, order_id: str) -> Optional[OrderStatus]:
        """获取订单状态"""
        if order_id not in self._orders:
            return None
        return self._orders[order_id].status
    
    def set_balance(self, balance: float):
        """设置账户余额 - 用于测试边界情况"""
        self._account_balance = balance
        self._buying_power = balance * 4


# ============ Pytest Fixture ============

@pytest.fixture
def mock_ibkr():
    """IBKR Mock fixture for all tests"""
    return MockIBKRClient()


@pytest.fixture
def mock_ibkr_low_balance():
    """资金不足的 Mock IBKR - 用于测试拒绝场景"""
    return MockIBKRClient(initial_balance=100.0)
