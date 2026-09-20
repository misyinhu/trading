"""md worker 专用：只读 profile 配置装配（settings.yaml + secrets.toml + env）。

与 ctp_client.ctp_worker._load_config 同口径，但**绝不 import thosttraderapi**：
md 进程只能加载 thostmduserapi 一套原生库，trader/md se 库同进程共存会在
开盘回调时原生 abort（2026-09-18 simnow 实测）。
"""
from __future__ import annotations

import os
from pathlib import Path

_PROFILE_FIELDS = {
    "simnow": {
        "block": "simnow",
        "secrets": {"user": "SIMNOW_SIM_USER", "password": "SIMNOW_SIM_PASSWORD",
                    "auth_code": None, "app_id": None, "broker_id": None,
                    "td_server": None, "md_server": None},
        "env": {"user": "SIMNOW_USER", "password": "SIMNOW_PASSWORD"},
    },
    "citic": {
        "block": "citic",
        "secrets": {"user": "CITIC_CTP_USER", "password": "CITIC_CTP_PASSWORD",
                    "auth_code": "CITIC_CTP_AUTH_CODE", "app_id": "CITIC_CTP_APP_ID",
                    "broker_id": "CITIC_CTP_BROKER_ID",
                    "td_server": "CITIC_CTP_TD_SERVER", "md_server": "CITIC_CTP_MD_SERVER"},
        "env": {"user": "CITIC_CTP_USER", "password": "CITIC_CTP_PASSWORD",
                "auth_code": "CITIC_CTP_AUTH_CODE", "app_id": "CITIC_CTP_APP_ID",
                "broker_id": "CITIC_CTP_BROKER_ID",
                "td_server": "CITIC_CTP_TD_SERVER", "md_server": "CITIC_CTP_MD_SERVER"},
    },
    "live": {
        "block": "live",
        "secrets": {"user": "LIVE_CTP_USER", "password": "LIVE_CTP_PASSWORD",
                    "auth_code": "LIVE_CTP_AUTH_CODE", "app_id": "LIVE_CTP_APP_ID",
                    "broker_id": "LIVE_CTP_BROKER_ID",
                    "td_server": "LIVE_CTP_TD_SERVER", "md_server": "LIVE_CTP_MD_SERVER"},
        "env": {"user": "LIVE_CTP_USER", "password": "LIVE_CTP_PASSWORD",
                "auth_code": "LIVE_CTP_AUTH_CODE", "app_id": "LIVE_CTP_APP_ID",
                "broker_id": "LIVE_CTP_BROKER_ID",
                "td_server": "LIVE_CTP_TD_SERVER", "md_server": "LIVE_CTP_MD_SERVER"},
    },
}


def _read_yaml_block(block: str) -> dict:
    root = Path(__file__).resolve().parents[1]
    yaml_path = root / "config" / "settings.yaml"
    out: dict = {}
    if not yaml_path.exists():
        return out
    in_block = False
    for raw in open(yaml_path, encoding="utf-8"):
        body = raw.split("#", 1)[0]
        kv = body.strip()
        if raw.startswith(f"{block}:"):
            in_block = True
            continue
        if in_block:
            if kv and not raw[:1].isspace() and ":" in kv:
                break
            if kv and ":" in kv:
                k, _, v = kv.partition(":")
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_md_config(profile: str = "simnow") -> dict:
    prof = _PROFILE_FIELDS.get(profile, _PROFILE_FIELDS["simnow"])
    blk = _read_yaml_block(prof["block"])
    sec: dict = {}
    secrets_path = Path(__file__).resolve().parents[1] / ".streamlit" / "secrets.toml"
    if secrets_path.exists():
        try:
            import tomllib
            sec = tomllib.load(open(secrets_path, "rb"))
        except Exception:
            sec = {}

    def _val(field: str, default: str = ""):
        env_key = prof["env"].get(field)
        if env_key and os.environ.get(env_key):
            return os.environ[env_key].strip()
        sec_key = prof["secrets"].get(field)
        if sec_key and sec.get(sec_key):
            return str(sec[sec_key]).strip()
        return blk.get(field, default)

    cfg = {
        "profile": profile,
        "md_server": _val("md_server", "tcp://182.254.243.31:30011"),
        "td_server": _val("td_server", "tcp://182.254.243.31:30001"),
        "broker_id": _val("broker_id", "9999"),
        "auth_code": _val("auth_code", "0000000000000000"),
        "app_id": _val("app_id", "simnow_client_test"),
        "user": _val("user", ""),
        "password": _val("password", ""),
        "label": blk.get("label", profile),
    }
    if profile != "simnow":
        for k in ("td_server", "broker_id", "app_id", "auth_code", "user", "password"):
            if not cfg[k] or cfg[k] in ("9999", "simnow_client_test", "0000000000000000"):
                cfg.setdefault("_missing", []).append(k)
    return cfg
