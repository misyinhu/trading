# Kanban 测试策略文档

> 量化交易系统的自动化测试框架

---

## 目录

- [测试架构](#测试架构)
- [快速开始](#快速开始)
- [测试结构](#测试结构)
- [Fixture 说明](#fixture-说明)
- [测试分类](#测试分类)
- [编写测试](#编写测试)
- [覆盖率要求](#覆盖率要求)

---

## 测试架构

```
测试金字塔:

     E2E Tests (少量)
    /                    < 5% - 完整交易流程
   Integration Tests     < 15% - 组件交互
  /                       
 Component Tests         < 30% - 页面/模块测试
/                           
Unit Tests (大量)          > 50% - 业务逻辑
```

**推荐分布**:
| 类型 | 占比 | 执行时间 | 覆盖率目标 |
|------|------|---------|-----------|
| Unit | 50-60% | <1s | 关键模块 >90% |
| Component | 25-30% | 1-5s | 核心逻辑 100% |
| Integration | 10-15% | 5-30s | 关键路径全覆盖 |
| E2E | 1-5% | 30-60s | 核心场景 |

---

## 快速开始

### 安装测试依赖

```bash
pip install pytest pytest-cov pytest-mock pytest-asyncio pytest-xdist pytest-randomly pytest-timeout
```

### 运行所有测试

```bash
# 在 kanban 目录下
pytest tests/ -v
```

### 按标记运行

```bash
# 只运行单元测试 (快速)
pytest tests/ -m "unit" -v

# 运行集成测试
pytest tests/ -m "integration" -v

# 跳过慢速测试
pytest tests/ -m "not slow" -v

# 并行执行
pytest tests/ -n auto
```

### 生成覆盖率报告

```bash
pytest tests/ --cov=src --cov-report=term-missing --cov-report=html
# 打开 htmlcov/index.html 查看详细报告
```

---

## 测试结构

```
tests/
├── __init__.py
├── conftest.py              # 共享 fixtures 和配置
├── helpers/
│   └── mock_ibkr.py         # IBKR Mock 实现
├── component/
│   ├── streamlit/           # Streamlit 页面测试
│   │   ├── __init__.py
│   │   └── test_news_center.py
│   └── webhook/             # Webhook 服务测试
│       ├── __init__.py
│       └── test_nl_parser.py
└── unit/                    # 单元测试
    ├── indicators/
    │   ├── test_resonance.py
    │   ├── test_zscore.py
    │   └── test_rsi.py
    └── services/
        └── test_signal_processor.py
```

---

## Fixture 说明

### conftest.py 提供的 Fixtures

| Fixture | 说明 |
|---------|------|
| `sample_ohlcv_bars` | 标准 OHLCV K线数据 (50条) |
| `sample_directions_up` | 全上涨方向列表 |
| `sample_directions_down` | 全下跌方向列表 |
| `sample_directions_mixed` | 混合方向列表 |
| `sample_directions_conflict` | 矛盾方向列表 |
| `sample_timeframe_data` | 多周期时间框架数据 |
| `sample_spread_data` | 套利数据 |
| `sample_order_params` | 标准订单参数 |
| `sample_trade_signal` | 样本交易信号 |
| `mock_ib_connection` | Mock IBKR 连接 |
| `mock_tv_datafeed` | Mock TradingView 数据源 |
| `clear_streamlit_cache` | 自动清除 Streamlit 缓存 |

### helpers/mock_ibkr.py 提供的 Fixtures

| Fixture | 说明 |
|---------|------|
| `mock_ibkr` | 完整 IBKR Mock |
| `mock_ibkr_low_balance` | 资金不足的 Mock |

---

## 测试分类

### 标记 (Markers)

```python
@pytest.mark.unit        # 单元测试 - 快速 isolated
@pytest.mark.integration # 集成测试 - 组件交互
@pytest.mark.e2e         # 端到端测试
@pytest.mark.slow        # 慢速测试 - 通常 >30s
@pytest.mark.ibkr        # 需要 IBKR 连接或 Mock
@pytest.mark.trading     # 真实交易逻辑
```

### 配置标记 (pytest.ini)

```ini
[pytest]
markers =
    unit: Unit tests - fast, isolated tests (<1s)
    integration: Integration tests - component interaction (1-30s)
    e2e: End-to-end tests - full workflow testing
    slow: Slow running tests - typically >30s
    ibkr: Requires IBKR connection or mock
    trading: Real trading logic tests
```

---

## 编写测试

### 示例 1: 单元测试

```python
# tests/unit/indicators/test_resonance.py
import pytest
from app import calculate_resonance_en

class TestResonanceCalculation:
    """共振分数计算测试"""
    
    def test_all_up(self, sample_directions_up):
        """全上涨 - 应得高分"""
        result = calculate_resonance_en(sample_directions_up)
        
        assert result["score"] >= 70
        assert result["level"] == "高"
        assert result["distribution"]["up"] == 5
    
    def test_empty_directions(self):
        """空输入"""
        result = calculate_resonance_en([])
        
        assert result["score"] == 0
```

### 示例 2: 组件测试 (Streamlit)

```python
# tests/component/streamlit/test_news_center.py
import pytest
from unittest.mock import patch

class TestNewsCenterFiltering:
    def test_category_filtering_logic(self):
        """测试分类筛选逻辑"""
        news_list = [
            {"category": "技术分析", "title": "新闻1"},
            {"category": "基本面", "title": "新闻2"},
        ]
        
        selected_categories = ["技术分析"]
        filtered = [
            n for n in news_list
            if n["category"] in selected_categories
        ]
        
        assert len(filtered) == 1
```

### 示例 3: Webhook 测试

```python
# tests/component/webhook/test_nl_parser.py
import pytest
from notify.nl_parser import parse_trading_command

class TestNLParserPatterns:
    @pytest.mark.parametrize("command,expected_action", [
        ("买入1手GC", "BUY"),
        ("卖出1手GC", "SELL"),
        ("平仓GC", "CLOSE"),
    ])
    def test_trading_patterns(self, command, expected_action):
        """测试交易指令解析"""
        result = parse_trading_command(command)
        assert result["action"] == expected_action
```

### 示例 4: 异步 IBKR 测试

```python
# tests/integration/test_ibkr_order.py
import pytest
from helpers.mock_ibkr import MockIBKRClient, MockContract, MockOrder

@pytest.mark.asyncio
async def test_full_order_flow():
    """完整订单流程测试"""
    ibkr = MockIBKRClient()
    
    # 1. 连接
    await ibkr.connectAsync('127.0.0.1', 7497, clientId=1)
    assert ibkr.is_connected
    
    # 2. 下单
    order_id = await ibkr.placeOrderAsync(
        order_id="TEST001",
        contract=MockContract(symbol="GC"),
        order=MockOrder(action="BUY", total_quantity=1)
    )
    
    # 3. 模拟成交
    ibkr.simulate_fill(order_id, fill_price=2350.0)
    
    # 4. 验证状态
    assert ibkr.get_order_status(order_id) == OrderStatus.FILLED
```

---

## 覆盖率要求

### 目标

| 模块 | 行覆盖率 | 分支覆盖率 |
|------|---------|-----------|
| `src.analysis` | >90% | >85% |
| `src.three_filter` | >85% | >80% |
| `src.data` | >80% | >75% |
| `notify.nl_parser` | >90% | >85% |

### 强制要求

- ❌ 不要用 `# pragma: no cover` 排除业务逻辑
- ✅ 边界条件、错误处理必须测试
- ✅ 测试状态机所有转换
- ✅ 测试空输入、极端值

### 查看覆盖率

```bash
# 终端输出
pytest tests/ --cov=src --cov-report=term-missing

# HTML 报告
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html
```

---

## CI/CD 配置

GitHub Actions 配置见 `.github/workflows/test.yml`:

1. **Push/PR** → 运行 unit + component tests
2. **每日凌晨** → 运行完整测试套件
3. **失败阻断** → coverage < 80% 阻断合并

---

## 最佳实践

1. **测试命名**: `test_{功能}_{场景}_{预期结果}`
2. **单一职责**: 每个测试只验证一个行为
3. **独立运行**: 测试之间无依赖
4. **清晰断言**: 断言消息描述预期行为
5. **可重现**: 使用 fixtures 保证数据一致性

---

## 故障排除

### 导入错误

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

### Streamlit 缓存问题

```python
@pytest.fixture(autouse=True)
def clear_streamlit_cache():
    yield
    import streamlit as st
    st.cache_data.clear()
    st.cache_resource.clear()
```

### 异步测试警告

```bash
# 在 pyproject.toml 中配置
[tool.pytest.ini_options]
asyncio_mode = "auto"
```
