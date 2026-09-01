#!/usr/bin/env python3
"""配置加载模块"""

import os
import yaml
from typing import Any, Dict

_config: Dict[str, Any] = {}
_query_only: bool = True


def load_config(config_path: str = None) -> Dict[str, Any]:
    """加载配置文件"""
    global _config

    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "settings.yaml")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f) or {}
            # 从配置加载 query_only
            global _query_only
            _query_only = _config.get("query_only", _query_only)
            return _config
    except Exception as e:
        print(f"加载配置失败: {e}")
        return {}


def get(key: str, default: Any = None) -> Any:
    """获取配置值"""
    if not _config:
        load_config()

    keys = key.split(".")
    value = _config
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return default
    
    if value is not None:
        return value
    
    # 回退：从 environments 当前环境获取
    env_config = _config.get("environments", {}).get(_config.get("current", "local"), {})
    if "feishu" in key:
        feishu_config = env_config.get("feishu", {})
        sub_key = key.replace("feishu.", "")
        return feishu_config.get(sub_key, default)
    
    return default


def get_ibkr_host() -> str:
    """获取 IBKR 主机"""
    return get("ibkr.host", "127.0.0.1")


def get_ibkr_port() -> int:
    """获取 IB Gateway 端口"""
    # 优先从 environments 配置获取（支持本地/远程切换）
    env_config = get("environments", {}).get(get("current", "local"), {})
    if "ib_port" in env_config:
        return int(env_config["ib_port"])
    # 回退到 ibkr.port 配置
    return int(get("ibkr.port", 4001))


def _get_from_env(key: str, default: Any = None) -> Any:
    """从当前环境配置中获取值"""
    env_config = get("environments", {}).get(get("current", "local"), {})
    if key in env_config:
        return env_config[key]
    return default



# ── 密钥外置：环境变量 > .streamlit/secrets.toml > settings.yaml ──
# secrets.toml 已被 .gitignore；明文密钥不再写入受版本控制的 settings.yaml。
_SECRETS_CACHE: Dict[str, Any] | None = None


def _secrets_path() -> str:
    return os.path.join(os.path.dirname(__file__), "..", ".streamlit", "secrets.toml")


def _load_secrets() -> Dict[str, Any]:
    global _SECRETS_CACHE
    if _SECRETS_CACHE is not None:
        return _SECRETS_CACHE
    data: Dict[str, Any] = {}
    path = _secrets_path()
    try:
        import tomllib
        with open(path, "rb") as f:
            data = tomllib.load(f) or {}
    except Exception:
        data = {}
    _SECRETS_CACHE = data
    return data


def _secret(*names: str, default: str = "") -> str:
    """按优先级取密钥：环境变量 → secrets.toml → default。"""
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    sec = _load_secrets()
    for n in names:
        v = sec.get(n)
        if v:
            return str(v)
    return default


def get_feishu_app_id() -> str:
    """获取飞书 App ID（优先环境变量/secrets，回退 settings.yaml）。"""
    return _secret("FEISHU_APP_ID",
                   default=_get_from_env("feishu", {}).get("app_id", get("feishu.app_id", "")))


def get_feishu_app_secret() -> str:
    """获取飞书 App Secret（仅从环境变量/secrets.toml 读取，不依赖 settings.yaml 明文）。"""
    return _secret("FEISHU_APP_SECRET",
                   default=_get_from_env("feishu", {}).get("app_secret")
                   if not _is_placeholder(_get_from_env("feishu", {}).get("app_secret"))
                   else "")


def _is_placeholder(v: Any) -> bool:
    if not v:
        return True
    return str(v).strip().startswith("__") and str(v).strip().endswith("__")


def get_feishu_chat_id() -> str:
    """获取飞书 Chat ID"""
    return _get_from_env("feishu", {}).get("chat_id", get("feishu.chat_id", ""))


def is_query_only() -> bool:
    """是否仅查询模式"""
    global _query_only
    return _query_only


def set_query_only(mode: bool):
    """设置仅查询模式"""
    global _query_only
    _query_only = mode


def get_webhook_port() -> int:
    """获取 Webhook 端口"""
    return int(get("webhook.port", 5002))


def get_project_root() -> str:
    """获取项目根目录（根据当前环境配置）"""
    project_root = _get_from_env("project_root")
    if project_root:
        return str(project_root)
    return os.path.dirname(os.path.dirname(__file__))


def get_volcengine_config() -> Dict[str, Any]:
    """获取火山引擎配置"""
    return {
        "api_key": get("volcengine.api_key", ""),
        "base_url": get("volcengine.base_url", "https://ark.cn-beijing.volces.com/api/coding/v3"),
        "model": get("volcengine.model", "doubao-seed-2.0-code"),
        "enabled": get("volcengine.enabled", False),
    }


def is_volcengine_enabled() -> bool:
    """检查火山引擎是否启用"""
    return get("volcengine.enabled", False)


# ─── SimNow / CTP 配置 ──────────────────────────────────────────

def get_simnow_flag() -> str:
    """获取 SimNow 模式: sim / live"""
    return get("simnow.flag", "sim")


def get_simnow_md_server() -> str:
    return get("simnow.md_server", "tcp://218.80.240.6:20002")


def get_simnow_td_server() -> str:
    return get("simnow.td_server", "tcp://218.80.240.6:20003")


def get_simnow_broker_id() -> str:
    return get("simnow.broker_id", "9999")


def get_simnow_auth_code() -> str:
    return get("simnow.auth_code", "0000000000")
