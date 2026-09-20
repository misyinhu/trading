#!/usr/bin/env python3
"""StrategyRegistry 单元测试"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from orders.strategy_registry import StrategyRegistry, get_registry


def test_registry_loaded():
    """默认注册表包含已知策略"""
    r = get_registry()
    names = r.list_strategies()
    assert "fu-lu-spread" in names
    assert "doge-grid" in names
    assert "crypto-divergence" in names
    assert "z120-spread" in names


def test_validate_unknown_strategy():
    """未知策略被拒绝"""
    r = get_registry()
    result = r.validate("random-strategy", {"direction": "long"})
    assert not result.valid
    assert any("unknown strategy" in e for e in result.errors)


def test_validate_missing_required():
    """缺少必填参数被拒绝"""
    r = get_registry()
    # fu-lu-spread requires zscore
    result = r.validate("fu-lu-spread", {"direction": "long"})
    assert not result.valid
    assert any("missing required param" in e for e in result.errors)


def test_validate_zscore_out_of_range():
    """zscore 超出范围被拒绝"""
    r = get_registry()
    result = r.validate("fu-lu-spread", {
        "direction": "long",
        "zscore": 5.0,  # > 4.0
    })
    assert not result.valid
    assert any("zscore" in e for e in result.errors)


def test_validate_ok():
    """完整参数通过校验"""
    r = get_registry()
    result = r.validate("fu-lu-spread", {
        "direction": "long",
        "zscore": 2.1,
        "correlation": 0.82,
        "hedge_ratio": 0.68,
        "fu_symbol": "FUL8.SHF",
        "lu_symbol": "LUL8.INE",
    })
    assert result.valid
    assert len(result.errors) == 0


def test_build_single_leg():
    """单腿策略生成一个 OrderContext"""
    r = get_registry()
    contexts, exchange = r.build_order_contexts("doge-grid", {
        "symbol": "DOGE-USDT",
        "direction": "long",
        "quantity": 100,
        "zscore": 1.5,
    })
    assert len(contexts) == 1
    assert contexts[0]["symbol"] == "DOGE-USDT"
    assert contexts[0]["action"] == "BUY"
    assert contexts[0]["quantity"] == 100
    assert exchange == "OKX"


def test_build_fu_lu_spread_long():
    """FU-LU spread 做多价差生成两个 OrderContext"""
    r = get_registry()
    contexts, exchange = r.build_order_contexts("fu-lu-spread", {
        "direction": "long",
        "zscore": 2.1,
        "correlation": 0.82,
        "hedge_ratio": 0.68,
        "quantity": 1,
        "fu_symbol": "FUL8.SHF",
        "lu_symbol": "LUL8.INE",
    })
    assert len(contexts) == 2
    # 做多价差 = 买FU + 卖LU
    assert contexts[0]["symbol"] == "FUL8.SHF"
    assert contexts[0]["action"] == "BUY"
    assert contexts[1]["symbol"] == "LUL8.INE"
    assert contexts[1]["action"] == "SELL"
    # LU 数量 = 1 * 0.68
    assert contexts[1]["quantity"] == 0.68
    assert exchange == "IB"


def test_build_fu_lu_spread_short():
    """FU-LU spread 做空价差生成两个 OrderContext"""
    r = get_registry()
    contexts, exchange = r.build_order_contexts("fu-lu-spread", {
        "direction": "short",
        "zscore": -2.1,
        "hedge_ratio": 0.68,
        "quantity": 1,
        "fu_symbol": "FUL8.SHF",
        "lu_symbol": "LUL8.INE",
    })
    assert len(contexts) == 2
    # 做空价差 = 卖FU + 买LU
    assert contexts[0]["action"] == "SELL"
    assert contexts[1]["action"] == "BUY"
    assert exchange == "IB"


def test_validate_correlation_out_of_range():
    """correlation 低于阈值被拒绝"""
    r = get_registry()
    result = r.validate("fu-lu-spread", {
        "direction": "long",
        "zscore": 1.0,
        "correlation": 0.55,  # < 0.7
    })
    assert not result.valid
    assert any("correlation" in e for e in result.errors)


def test_register_custom_strategy():
    """可注册自定义策略"""
    from orders.strategy_registry import StrategySpec
    r = StrategyRegistry()
    r.register(StrategySpec(
        name="my-strategy",
        exchange="IB",
        required_params=["zscore"],
        param_constraints={"zscore": (-5.0, 5.0)},
    ))
    assert "my-strategy" in r.list_strategies()
    result = r.validate("my-strategy", {"zscore": 3.0, "direction": "long"})
    assert result.valid


# ─── ApprovedStrategyCache tests ──────────────────────────────────────────────

def test_approved_cache_defaults_empty():
    """缓存初始化时默认空集（quant-agent 端点未配置时）"""
    from orders.strategy_registry import ApprovedStrategyCache
    cache = ApprovedStrategyCache(agent_base_url=None)
    assert cache.is_approved("any-strategy") is False
    assert cache.get_approved() == set()


def test_approved_cache_set_approved():
    """手动注入批准策略"""
    from orders.strategy_registry import ApprovedStrategyCache
    cache = ApprovedStrategyCache(agent_base_url=None)
    cache.set_approved({"pl-pa-ratio", "fu-lu-spread"})
    assert cache.is_approved("pl-pa-ratio") is True
    assert cache.is_approved("fu-lu-spread") is True
    assert cache.is_approved("unknown-strategy") is False


def test_approved_cache_clear():
    """清空缓存"""
    from orders.strategy_registry import ApprovedStrategyCache
    cache = ApprovedStrategyCache(agent_base_url=None)
    cache.set_approved({"pl-pa-ratio"})
    cache.clear()
    assert cache.is_approved("pl-pa-ratio") is False
    assert cache.get_approved() == set()


def test_approved_cache_get_approved_returns_set():
    """get_approved() 返回 set 类型"""
    from orders.strategy_registry import ApprovedStrategyCache
    cache = ApprovedStrategyCache(agent_base_url=None)
    cache.set_approved({"a", "b"})
    result = cache.get_approved()
    assert isinstance(result, set)
    assert result == {"a", "b"}


def test_approved_cache_none_url_skips_poll(monkeypatch):
    """agent_base_url=None 时不发起 HTTP 请求"""
    from orders.strategy_registry import ApprovedStrategyCache
    cache = ApprovedStrategyCache(agent_base_url=None)

    called = []
    def _fake_get(*args, **kwargs):
        called.append(True)
        return []

    # patch should not be called since url is None
    # just verify no exception is raised on refresh
    cache.refresh()  # should be no-op when url=None
    assert called == []
    assert cache.get_approved() == set()


def test_approved_cache_get_approved_strategy_ids(monkeypatch):
    """refresh() 从 quant-agent 解析 strategy_id 列表"""
    import requests

    class FakeResp:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return [
                {"strategy_id": "strat-001", "name": "PL_PA_ratio", "status": "APPROVED"},
                {"strategy_id": "strat-002", "name": "FU_LU_spread", "status": "APPROVED"},
                {"strategy_id": "strat-003", "name": "RB_CL_crack", "status": "REJECTED"},
            ]

    monkeypatch.setattr(requests, "get", lambda *a, **kw: FakeResp())

    from orders.strategy_registry import ApprovedStrategyCache
    cache = ApprovedStrategyCache(agent_base_url="http://quant-agent:8005")
    cache.refresh()

    approved = cache.get_approved()
    assert "strat-001" in approved
    assert "strat-002" in approved
    assert "strat-003" not in approved  # REJECTED → not approved


def test_approved_cache_http_error_graceful(monkeypatch):
    """HTTP 错误时缓存保持上一次状态，不抛异常"""
    import requests

    class FakeResp:
        status_code = 503
        def raise_for_status(self):
            raise requests.HTTPError("Service unavailable")

    call_count = [0]
    original_get = requests.get

    def _fake_get(url, *a, **kw):
        call_count[0] += 1
        return FakeResp()

    monkeypatch.setattr(requests, "get", _fake_get)

    from orders.strategy_registry import ApprovedStrategyCache
    cache = ApprovedStrategyCache(agent_base_url="http://quant-agent:8005")
    cache.set_approved({"pre-existing-strategy"})

    # refresh should not raise
    cache.refresh()

    # cache still has pre-existing value
    assert cache.is_approved("pre-existing-strategy") is True


def test_approved_cache_get_approved_strategy_ids_returns_set(monkeypatch):
    """refresh() 后 get_approved() 返回 set"""
    class FakeResp:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return [{"strategy_id": "s1", "name": "n1", "status": "APPROVED"}]

    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **kw: FakeResp())

    from orders.strategy_registry import ApprovedStrategyCache
    cache = ApprovedStrategyCache(agent_base_url="http://localhost:9000")
    cache.refresh()
    result = cache.get_approved()
    assert isinstance(result, set)
    assert "s1" in result
