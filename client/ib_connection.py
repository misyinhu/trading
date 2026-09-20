#!/usr/bin/env python3
"""IB Connection Manager - 请求队列方案

核心设计：
1. 不用 loop.run_forever()（避免与 run_until_complete 冲突）
2. IB 线程用 queue.Queue() 等待请求
3. 每个请求用 ib.xxx() → util.run() → run_until_complete() 处理
4. run_until_complete() 在执行期间会处理 socket 事件，所以请求能正常完成

这个方案解决了核心矛盾：
- 之前：run_forever() 与 run_until_complete() 冲突
- 现在：不用 run_forever()，每次请求用 run_until_complete() 完成后循环继续等待下一个请求
"""

import os, sys, threading, logging, asyncio, queue
from typing import Optional, Callable, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ib_insync import IB
from config import load_config, get_ibkr_host, get_ibkr_port, get_ibkr_client_id

load_config()
logger = logging.getLogger(__name__)


class IBConnectionManager:
    """IB 连接管理器 - 请求队列方案"""
    
    _instance: Optional["IBConnectionManager"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        self._ib: Optional[IB] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._host = get_ibkr_host()
        self._port = get_ibkr_port()
        # 固定下单 clientId（默认 2），不在 2-99 间扫描漂移
        self._client_id: int = get_ibkr_client_id()
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._error: Optional[Exception] = None
        self._request_queue: queue.Queue = queue.Queue()
        self._running = False
    
    @classmethod
    def get_instance(cls) -> "IBConnectionManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _reclaim_client_id(self) -> None:
        """对固定 clientId 做一次抢占式清理。

        进程崩溃/被 kill 后，Gateway 可能短暂保留同 clientId 的僵尸会话，
        立刻重连会报 326「客户号码已被使用」。新建一个 IB 用同一 id 连一下再断，
        逼退残留会话；失败不阻断主连接（_run_loop 会再试并由重连逻辑兜底）。
        """
        probe = IB()
        try:
            probe.connect(self._host, self._port, clientId=self._client_id, timeout=3)
            probe.disconnect()
            logger.info(f"[IB] reclaimed fixed clientId={self._client_id}")
        except Exception as e:  # noqa: BLE001
            logger.info(f"[IB] reclaim clientId={self._client_id} skipped: {e}")
    
    def start(self, timeout: float = 5.0) -> IB:
        """启动 IB 连接（在后台线程中）"""
        if self._thread is not None and self._thread.is_alive():
            if self._ib and self._ib.isConnected():
                return self._ib
            if self._ready.wait(timeout=0.1):
                if self._ib and self._ib.isConnected():
                    return self._ib
        
        # 新建连接前先逼退可能残留的同 clientId 僵尸会话
        self._reclaim_client_id()
        self._ready.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="IB-Worker")
        self._thread.start()
        
        if not self._ready.wait(timeout=timeout):
            raise TimeoutError(f"IB 连接超时 ({timeout}s)")
        if self._error:
            raise self._error
        if not self._ib or not self._ib.isConnected():
            raise RuntimeError("IB 连接失败")
        return self._ib
    
    def _run_loop(self):
        """IB 工作线程 - 处理请求队列"""
        try:
            # 创建事件循环
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            
            # 创建 IB 实例并连接
            self._ib = IB()
            self._ib.connect(self._host, self._port, clientId=self._client_id, timeout=10)
            
            if not self._ib.isConnected():
                self._error = RuntimeError("IB 连接失败")
                self._ready.set()
                return
            
            logger.info(f"[IB] Connected (clientId={self._client_id})")
            self._ready.set()
            self._running = True
            
            # 主循环：从队列获取请求并执行
            while self._running:
                try:
                    # 等待请求（最多等待 1 秒，然后检查 _running 标志）
                    request = self._request_queue.get(timeout=1.0)
                except queue.Empty:
                    # 事件泵：空闲时 pump 事件循环，让 execDetails 等回调能触发
                    try:
                        if self._loop and not self._loop.is_closed():
                            self._loop.run_until_complete(asyncio.sleep(0))
                    except Exception:
                        pass
                    continue
                
                if request is None:  # 停止信号
                    break
                
                fn, result_queue = request['fn'], request['result_queue']
                try:
                    # 在此线程中执行 fn()（会调用 util.run() → run_until_complete()）
                    # run_until_complete() 会处理 socket 事件，所以请求能正常完成
                    result = fn()
                    result_queue.put(('ok', result))
                except Exception as e:
                    logger.error(f"[IB] Request error: {e}")
                    result_queue.put(('error', e))
            
            # 清理
            if self._ib and self._ib.isConnected():
                try:
                    self._ib.disconnect()
                    logger.info("[IB] Disconnected")
                except:
                    pass
                    
        except Exception as e:
            self._error = e
            self._ready.set()
            logger.error(f"[IB] Error: {e}")
    
    def get_connection(self) -> IB:
        """获取 IB 连接"""
        return self.start()
    
    def run_sync(self, fn: Callable[..., Any], timeout: float = 30.0) -> Any:
        """
        在 IB 线程中执行同步函数。
        
        Args:
            fn: 要执行的函数（如 lambda: ib.reqContractDetails(contract)）
            timeout: 超时时间（秒）
        
        Returns:
            fn() 的返回值
        
        Raises:
            TimeoutError: 超时
            Exception: fn() 抛出的异常
        """
        if not self._running:
            raise RuntimeError("IB 线程未运行")
        
        result_queue = queue.Queue()
        self._request_queue.put({'fn': fn, 'result_queue': result_queue})
        
        try:
            status, value = result_queue.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(f"IB 操作超时 ({timeout}s)")
        
        if status == 'error':
            raise value
        return value
    
    def is_connected(self) -> bool:
        return self._ib is not None and self._ib.isConnected()
    
    def disconnect(self):
        """断开 IB 连接"""
        self._running = False
        self._request_queue.put(None)  # 发送停止信号
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)


_manager: Optional[IBConnectionManager] = None


def get_ib_connection() -> IB:
    """获取 IB 连接（单例）"""
    global _manager
    if _manager is None:
        _manager = IBConnectionManager.get_instance()
    return _manager.get_connection()


def get_ib_manager() -> IBConnectionManager:
    """获取 IB 管理器（单例）"""
    global _manager
    if _manager is None:
        _manager = IBConnectionManager.get_instance()
    return _manager


if __name__ == "__main__":
    print("=" * 60)
    print("Testing IB Connection Manager (Queue-based)")
    print("=" * 60)
    
    manager = get_ib_manager()
    ib = manager.get_connection()
    print(f"[OK] Connected: {ib.isConnected()}")
    
    from ib_insync import Future
    
    # Test 1: reqContractDetails
    print("\nTest 1: ib.reqContractDetails()")
    contract = Future("GC", exchange="COMEX", currency="USD")
    t0 = __import__('time').time()
    result = manager.run_sync(lambda: ib.reqContractDetails(contract), timeout=10)
    print(f"   [OK] Got {len(result)} contracts ({__import__('time').time()-t0:.2f}s)")
    
    # Test 2: positions
    print("\nTest 2: ib.positions()")
    t0 = __import__('time').time()
    positions = manager.run_sync(lambda: ib.positions(), timeout=10)
    print(f"   [OK] Got {len(positions)} positions ({__import__('time').time()-t0:.2f}s)")
    for pos in positions[:3]:
        print(f"      - {pos.contract.symbol}: {pos.position}")
    
    # Test 3: cross-thread call
    print("\nTest 3: Cross-thread call")
    def worker():
        t0 = __import__('time').time()
        result = manager.run_sync(lambda: ib.reqContractDetails(contract), timeout=10)
        print(f"   [OK] [Worker] Got {len(result)} contracts ({__import__('time').time()-t0:.2f}s)")
    
    import threading
    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=15)
    
    print("\n" + "=" * 60)
    print("[OK] All tests passed!")
    print("=" * 60)
    
    manager.disconnect()
