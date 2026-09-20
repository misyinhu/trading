"""Configuration module."""

import os
import yaml
from pathlib import Path


def _get_config_path() -> str:
    candidates = [
        Path(__file__).parent.parent.parent / "config" / "settings.yaml",
        Path("D:/projects/trading/config/settings.yaml"),
        Path("/Users/wang/.opencode/workspace/trading/config/settings.yaml"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return str(candidates[0])


_SHARED_CONFIG_PATH = _get_config_path()

TIMEFRAMES = ["1m", "5m", "30m", "4h", "1D"]
TIMEFRAME_LABELS = {
    "1m": "1分钟",
    "5m": "5分钟",
    "30m": "30分钟",
    "4h": "4小时",
    "1D": "日线",
}
TREND_EMOJI = {"up": "📈", "down": "📉", "neutral": "➡️"}
TREND_CN = {"up": "上涨", "down": "下跌", "neutral": "震荡"}
BIAS_CN = {"UP": "偏多", "DOWN": "偏空", "NEUTRAL": "中性"}


def load_shared_config() -> dict:
    try:
        if os.path.exists(_SHARED_CONFIG_PATH):
            with open(_SHARED_CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
    except:
        pass
    return {}


config = load_shared_config()
QUANT_CORE_URL = config.get("quant_core", {}).get("url", "http://100.82.238.11:8005")
CLIENT_ID = config.get("quant_core", {}).get("client_id", "10")

# ─── RiskGate Z-Score 阈值 ───────────────────────────────────────────
_risk_gate = config.get("risk_gate", {})

def get_zscore_alert_threshold() -> float:
    """警报触发阈值（对应规则入场 ±1.0）"""
    return _risk_gate.get("zscore_alert", 1.0)

def get_zscore_exit_threshold() -> float:
    """止损阈值（对应规则回归 ±0.5）"""
    return _risk_gate.get("zscore_exit", 0.5)

def get_zscore_warn() -> float:
    return _risk_gate.get("zscore_warn", 3.0)

def get_zscore_critical() -> float:
    return _risk_gate.get("zscore_critical", 4.0)

# 套利分析参数（Z-Score 阈值已迁移到 risk_gate.zscore_alert）
ARBITRAGE_DEFAULTS = {
    "correlation_threshold": 0.8,  # 相关性触发阈值
    "rsi_divergence_threshold": 20,  # RSI 背离阈值
    "correlation_window": 20,  # 滚动相关性窗口
}


def get_secrets():
    """从 streamlit secrets 读取敏感配置，fallback 到环境变量"""
    try:
        import streamlit as st
        return st.secrets
    except Exception:
        pass
    
    # fallback 到环境变量
    class EnvSecrets:
        def get(self, key, default=""):
            return os.getenv(key, default)
    return EnvSecrets()


def _get_okx_creds() -> tuple:
    """根据 flag 返回对应的 OKX 凭证"""
    flag = get_okx_flag()
    prefix = "OKX_SIM" if flag == "sim" else "OKX_LIVE"
    secrets = get_secrets()
    return (
        secrets.get(f"{prefix}_API_KEY", ""),
        secrets.get(f"{prefix}_SECRET_KEY", ""),
        secrets.get(f"{prefix}_PASSPHRASE", ""),
    )

def get_okx_api_key() -> str:
    return _get_okx_creds()[0]

def get_okx_secret_key() -> str:
    return _get_okx_creds()[1]

def get_okx_passphrase() -> str:
    return _get_okx_creds()[2]

def get_okx_flag() -> str:
    """获取 OKX 交易模式: sim 或 live"""
    return config.get("okx", {}).get("flag", "sim")

def get_okx_pairs() -> list:
    """获取 OKX 交易对配置"""
    return config.get("okx", {}).get("pairs", [])


# ─── SimNow / CTP 配置 ───────────────────────────────────────────

def get_simnow_flag() -> str:
    """获取 SimNow 交易模式: sim 或 live"""
    return config.get("simnow", {}).get("flag", "sim")


def get_simnow_md_server() -> str:
    return config.get("simnow", {}).get("md_server", "tcp://218.80.240.6:20002")


def get_simnow_td_server() -> str:
    return config.get("simnow", {}).get("td_server", "tcp://218.80.240.6:20003")


def get_simnow_broker_id() -> str:
    return config.get("simnow", {}).get("broker_id", "9999")


def get_simnow_auth_code() -> str:
    return config.get("simnow", {}).get("auth_code", "0000000000")


def get_simnow_user() -> str:
    prefix = "SIMNOW_SIM" if get_simnow_flag() == "sim" else "SIMNOW_LIVE"
    secrets = get_secrets()
    return secrets.get(f"{prefix}_USER", "")


def get_simnow_password() -> str:
    prefix = "SIMNOW_SIM" if get_simnow_flag() == "sim" else "SIMNOW_LIVE"
    secrets = get_secrets()
    return secrets.get(f"{prefix}_PASSWORD", "")
