#!/usr/bin/env python3
"""Signal API 集成测试 — Flask test client"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest
from notify.webhook_bridge import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_submit_signal_reviewed(client):
    """提交正常信号返回 reviewed 状态"""
    resp = client.post("/api/signals", json={
        "source": "quant-agent",
        "symbol": "FUL8.SHF",
        "direction": "long",
        "quantity": 1,
        "zscore": 2.1,
        "reason": "Z-Score突破上轨",
        "strategy": "fu-lu-spread",
    })
    assert resp.status_code == 201
    data = json.loads(resp.data)
    assert "signal_id" in data
    assert data["status"] == "reviewed"
    assert data["risk"]["allowed"] is True


def test_submit_signal_rejected(client):
    """风控拦截的信号返回 rejected"""
    resp = client.post("/api/signals", json={
        "source": "quant-agent",
        "symbol": "FUL8.SHF",
        "direction": "long",
        "quantity": 1,
        "zscore": 10.0,
        "reason": "异常信号",
    })
    data = json.loads(resp.data)
    assert data["status"] == "rejected"


def test_get_signal_404(client):
    """查询不存在的信号返回 404"""
    resp = client.get("/api/signals/nonexistent")
    assert resp.status_code == 404


def test_get_signal_exists(client):
    """查询已提交的信号"""
    resp = client.post("/api/signals", json={
        "source": "test",
        "symbol": "GC",
        "direction": "long",
        "quantity": 1,
        "reason": "测试查询",
    })
    data = json.loads(resp.data)
    sid = data["signal_id"]

    resp2 = client.get(f"/api/signals/{sid}")
    assert resp2.status_code == 200
    data2 = json.loads(resp2.data)
    assert data2["status"] == "reviewed"


def test_confirm_unknown_signal(client):
    """确认不存在的信号返回 400"""
    resp = client.post("/api/signals/unknown/confirm", json={"action": "confirm"})
    assert resp.status_code == 400


def test_submit_invalid_json(client):
    """提交非法 JSON 返回 400"""
    resp = client.post("/api/signals", data="not json",
                       content_type="application/json")
    assert resp.status_code == 400