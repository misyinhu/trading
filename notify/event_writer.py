"""
trading → quant-agent 事件回写适配器。

trading 调用此模块将 ORDER_PLACED/ORDER_FILLED/TRIGGER_FIRED
事件写入 JSONL，quant-agent 的 event_bus 轮询读取。

文件路径由环境变量 EVENT_WRITE_PATH 控制，
默认写到 trading 本地，quant-agent 轮询或通过 HTTP 回写端点。

H8 / signal-callback-writeback 交付物。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

EVENT_WRITE_PATH = os.environ.get(
    "EVENT_WRITE_PATH",
    str(Path(__file__).parent.parent / "logs" / "trading_events.jsonl")
)

SEQ_FILE = os.environ.get(
    "EVENT_SEQ_FILE",
    str(Path(__file__).parent.parent / "logs" / "trading_events.seq")
)

Path(EVENT_WRITE_PATH).parent.mkdir(parents=True, exist_ok=True)


def _next_seq() -> int:
    """原子递增 seq。"""
    seq_file = Path(SEQ_FILE)
    if seq_file.exists():
        seq = int(seq_file.read_text().strip() or "0") + 1
    else:
        seq = 1
    seq_file.write_text(str(seq))
    return seq


def write_event(
    signal_id: str,
    event_type: str,
    data: dict,
    agent: str = "trading",
) -> dict:
    """
    写事件到 trading_events.jsonl（幂等：同 signal_id + event_type 只记一次）。

    Returns:
      {"recorded": True, "already_recorded": False, "event_id": "...", "seq": N}
    """
    path = Path(EVENT_WRITE_PATH)
    seq = _next_seq()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    event = {
        "seq": seq,
        "ts": ts,
        "agent": agent,
        "type": event_type,
        "data": {
            "signal_id": signal_id,
            **data,
        },
    }

    # 幂等检查：同 signal_id + event_type 是否已存在
    already_recorded = False
    if path.exists():
        with open(path) as f:
            for line in f:
                try:
                    existing = json.loads(line.strip())
                    if (existing.get("data", {}).get("signal_id") == signal_id
                            and existing.get("type") == event_type):
                        already_recorded = True
                        break
                except Exception:
                    pass

    if not already_recorded:
        with open(path, "a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    return {
        "recorded": not already_recorded,
        "already_recorded": already_recorded,
        "event_id": f"{signal_id}_{event_type}",
        "seq": seq,
    }


# ─── HTTP 回调到 quant-agent ─────────────────────────────────

import os
import requests

def _http_callback(signal_id: str, event_type: str, data: dict, agent: str = "trading") -> None:
    """
    可选：POST 到 quant-agent Flask 的 /api/signals/<id>/events 回调端点。
    由环境变量 QUANT_AGENT_CALLBACK_URL 控制（如 http://localhost:5001）。
    """
    callback_url = os.environ.get("QUANT_AGENT_CALLBACK_URL")
    if not callback_url:
        return

    type_map = {
        "ORDER_PLACED":  "ORDER_PLACED",
        "ORDER_FILLED":  "ORDER_FILLED",
        "TRIGGER_FIRED": "TRIGGER_FIRED",
        "RISK_REJECTED": "RISK_REJECTED",
    }

    payload = {
        "event_type": type_map.get(event_type, event_type),
        "signal_id": signal_id,
        **data,
    }

    try:
        resp = requests.post(
            f"{callback_url}/api/signals/{signal_id}/events",
            json=payload,
            timeout=5,
        )
        if resp.status_code in (200, 201):
            pass  # 幂等，成功不报错
    except requests.RequestException as e:
        # 回调失败不影响本地写盘
        import logging
        logging.getLogger("event_writer").warning(
            "quant-agent 回调失败 %s: %s", signal_id, e
        )


def write_event_callback(
    signal_id: str,
    event_type: str,
    data: dict,
    agent: str = "trading",
) -> dict:
    """
    增强版 write_event：本地写盘 + HTTP 回调 quant-agent。
    幂等：同 signal_id+event_type 只记录/回调一次。
    """
    result = write_event(signal_id, event_type, data, agent)
    # 仅在首次写入时回调（避免幂等冲突）
    if result.get("recorded"):
        _http_callback(signal_id, event_type, data, agent)
    return result
