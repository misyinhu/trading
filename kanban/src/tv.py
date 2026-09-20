"""TradingView CDP integration."""

import json
import subprocess
import time
import http.client
from pathlib import Path

_TV_CLI = (
    Path(__file__).parent.parent.parent.parent
    / "tradingview-mcp"
    / "src"
    / "cli"
    / "index.js"
)
_MULTI_WINDOW_SCRIPT = (
    Path(__file__).parent.parent.parent.parent
    / "tradingview-mcp"
    / "get_window_data.cjs"
)

# Windows 路径修正：winclaw 上 tradingview-mcp 在 C:\projects\tradingview-mcp
import platform as _platform
if _platform.system() == "Windows":
    _TV_MCP_ROOT_WIN = r"C:\projects\tradingview-mcp"
    _TV_CLI = Path(r"C:\projects\tradingview-mcp\src\cli\index.js")
    _MULTI_WINDOW_SCRIPT = Path(r"C:\projects\tradingview-mcp\get_window_data.cjs")

_config_paths = [
    Path(__file__).parent.parent.parent / "config" / "settings.yaml",
    Path("../config/settings.yaml"),
    Path("../../config/settings.yaml"),
]
_config_path = next((p for p in _config_paths if p.exists()), _config_paths[0])

import yaml

try:
    with open(_config_path, "r", encoding="utf-8") as f:
        _cfg = yaml.safe_load(f) or {}
except:
    _cfg = {}

_tv_cdp = _cfg.get("tv_cdp", {})
_tv_url = _tv_cdp.get("url", "http://localhost")
_tv_port = _tv_cdp.get("port", 9224)
import re

_match = re.match(r"https?://([^:/]+)", _tv_url)
TV_HOST = _match.group(1) if _match else "localhost"
TV_PORT = str(_tv_port)


def _normalize_studies(studies):
    """Convert get_window_data.cjs fullArray format → 1_alerts.py values dict.

    get_window_data.cjs returns: {name, fullArray: [t, v0, v1, ...], last5: [...]}
    1_alerts.py expects:        {name, values: {key: value}}

    Also merges any existing study.values dict for backward compatibility.
    """
    normalized = []
    for study in studies:
        name = study.get("name", "") or ""
        if not name or name == "Overlay":
            continue

        entry = {"name": name, "values": {}}

        # Parse fullArray → values dict
        full = study.get("fullArray") or study.get("last") or []
        if isinstance(full, list) and len(full) >= 2:
            if "Z-Score" in name or "Spread" in name or "z-score" in name.lower():
                entry["values"]["Z-Score"] = (
                    str(full[1]) if isinstance(full[1], (int, float)) else None
                )
                if len(full) > 2:
                    entry["values"]["Z-Score_Signal"] = str(full[2])
                if len(full) > 3:
                    entry["values"]["Z-Score_Upper"] = str(full[3])
                if len(full) > 4:
                    entry["values"]["Z-Score_Lower"] = str(full[4])
                if len(full) > 5:
                    entry["values"]["Spread"] = (
                        str(full[5]) if isinstance(full[5], (int, float)) else None
                    )
            if "劈叉" in name or "corr" in name.lower():
                entry["values"]["相关性"] = (
                    str(full[1]) if len(full) > 1 and isinstance(full[1], (int, float)) else None
                )

        # Merge legacy dict values (winclaw webhook path uses this)
        legacy = study.get("values", {})
        if isinstance(legacy, dict):
            for k, v in legacy.items():
                if k not in entry["values"]:
                    entry["values"][k] = v

        normalized.append(entry)

    return normalized


def run_tv_cmd(cmd_args, wait=0.5):
    import os, sys, platform

    node_env = os.environ.copy()
    node_env["TV_HOST"] = TV_HOST
    node_env["TV_PORT"] = TV_PORT

    # Windows: tradingview-mcp 在 C:\projects\tradingview-mcp（不在 C:\projects\trading\ 下）
    # 必须在 cwd=tradingview-mcp 下执行，否则 node 找不到 node_modules
    if platform.system() == "Windows":
        cli_path = r"C:\projects\tradingview-mcp\src\cli\index.js"
        mcp_root = r"C:\projects\tradingview-mcp"
        # 直接传 env dict，避免 shell=True + set 的超时问题（Windows cwd 继承不稳定）
        node_cmd = ["node", cli_path] + list(cmd_args)
        result = subprocess.run(
            node_cmd,
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
            env=node_env,
            cwd=mcp_root,
        )
    else:
        cli_path = str(_TV_CLI)
        node_cmd = ["node", cli_path] + cmd_args
        result = subprocess.run(
            node_cmd,
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
            env=node_env,
        )
    if wait > 0:
        time.sleep(wait)
    if result.returncode == 0 and result.stdout:
        try:
            return json.loads(result.stdout)
        except:
            return None
    return None


def get_chart_targets():
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect((TV_HOST, int(TV_PORT)))
    request = f"GET /json/list HTTP/1.1\r\nHost: {TV_HOST}:{TV_PORT}\r\n\r\n".encode()
    sock.send(request)
    response = b""
    while True:
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
            if len(response) > 20000:
                break
        except socket.timeout:
            break
    sock.close()
    text = response.decode("utf-8", errors="replace")
    parts = text.split("\r\n\r\n", 1)
    body = parts[1].strip() if len(parts) > 1 else text.strip()
    targets = json.loads(body)
    result = []
    for t in targets:
        if t.get("type") == "page" and "tradingview.com/chart" in t.get("url", ""):
            ws_url = t.get("webSocketDebuggerUrl", "")
            if ws_url:
                ws_url = ws_url.replace(
                    "ws://127.0.0.1:9224/", f"ws://{TV_HOST}:{TV_PORT}/"
                )
                ws_url = ws_url.replace("ws://127.0.0.1/", f"ws://{TV_HOST}:{TV_PORT}/")
                t["webSocketDebuggerUrl"] = ws_url
            result.append(t)
    return result


# CDP connection for active chart detection (lazy, reused across calls)
_cdp_client = None
_active_ws_url = None


def _get_active_chart_ws_url():
    """通过 TradingViewApi._activeChartWidgetWV 找到真正活跃 chart tab 的 WS URL。"""
    import subprocess, os

    targets = get_chart_targets()
    if not targets:
        return None

    node_env = os.environ.copy()
    node_env["TV_HOST"] = TV_HOST
    node_env["TV_PORT"] = TV_PORT

    for t in targets:
        ws_url = t.get("webSocketDebuggerUrl", "")
        if not ws_url:
            continue
        # 探测脚本：尝试从任意 tab 读取 _activeChartWidgetWV
        probe_script = Path(__file__).parent.parent.parent / "tradingview-mcp" / "src" / "probe_active.cjs"
        if not probe_script.exists():
            continue
        cmd = ["node", str(probe_script), ws_url]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=8,
                cwd=str(probe_script.parent.parent),
                env=node_env,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0 and result.stdout.strip():
                try:
                    info = json.loads(result.stdout.strip())
                    if info.get("hasActive"):
                        return ws_url
                except:
                    pass
        except Exception:
            pass

    # Fallback: 返回第一个 chart tab
    return targets[0].get("webSocketDebuggerUrl")


def get_all_tv_indicators(timeframe="5"):
    tf_map = {
        "1m": "1",
        "5m": "5",
        "15s": "15",
        "15m": "15",
        "30m": "30",
        "1h": "60",
        "3h": "180",
        "4h": "240",
        "1d": "1D",
    }
    tf_code = tf_map.get(timeframe, "5")

    try:
        import os  # for os.environ
        # Fast path: detect current chart timeframe (1.8s)
        # If it matches target, skip multi-window script entirely
        current_tf = None
        try:
            sym_data = run_tv_cmd(["symbol"])
            if sym_data and sym_data.get("success"):
                current_tf = sym_data.get("resolution", "")
        except:
            pass

        targets = get_chart_targets()
        targets = list(reversed(targets))  # 反转以匹配 TV 窗口实际顺序

        # If current TF matches target OR only 1 tab, use get_window_data.cjs
        # (NOT get_single_tab_data which uses dataWindowView() → null for studies)
        if (current_tf and current_tf == tf_code) or len(targets) <= 1:
            return get_single_tab_data_via_cdp(timeframe)

        results = []
        seen_symbols = set()

        # Multi-window path: parallel execution with ThreadPoolExecutor
        # 3 workers: 5 tabs / 3 = ~2 batches, total ~6-8s instead of 16s
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if _platform.system() == "Windows":
            mw_script = Path(r"C:\projects\tradingview-mcp\get_window_data.cjs")
            mcp_root = r"C:\projects\tradingview-mcp"
        else:
            mw_script = _MULTI_WINDOW_SCRIPT
            mcp_root = str(Path(__file__).parent.parent.parent.parent / "tradingview-mcp")

        node_env = os.environ.copy()
        node_env["TV_HOST"] = TV_HOST
        node_env["TV_PORT"] = TV_PORT

        def fetch_tab(idx_target):
            idx, target = idx_target
            ws_url = target.get("webSocketDebuggerUrl", "")
            if not ws_url:
                return None
            mw_cmd = ["node", str(mw_script), ws_url, tf_code]
            r = subprocess.run(
                mw_cmd,
                capture_output=True,
                text=True,
                timeout=25,
                cwd=mcp_root,
                encoding="utf-8",
                errors="replace",
                env=node_env,
            )
            if r.returncode == 0 and r.stdout.strip():
                try:
                    data = json.loads(r.stdout.strip())
                    return (idx, data)
                except json.JSONDecodeError:
                    return None
            return None

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(fetch_tab, (idx, t)): idx for idx, t in enumerate(targets)}
            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res:
                        idx, data = res
                        symbol = data.get("symbol", "N/A")
                        if symbol in seen_symbols:
                            continue
                        seen_symbols.add(symbol)
                        results.append({
                            "symbol": symbol,
                            "tab_index": idx,
                            "exchange": data.get("exchange", ""),
                            "description": data.get("description", ""),
                            "timeframe": data.get("timeframe", tf_code),
                            "quote": data.get("quote", {}),
                            "studies": _normalize_studies(data.get("studies", [])),
                        })
                except Exception:
                    pass

        if results:
            return {
                "tabs": results,
                "tab_count": len(results),
                "mode": "multi_window",
                "timeframe": timeframe,
            }

        return get_single_tab_data(timeframe)

    except Exception as e:
        import traceback, sys
        print(f"get_all_tv_indicators error: {e}", flush=True)
        try:
            traceback.print_exc()
        except Exception:
            pass
        return get_single_tab_data(timeframe)


def get_single_tab_data(timeframe="5"):
    try:
        symbol_data = run_tv_cmd(["symbol"])
        quote_data = run_tv_cmd(["quote"])
        values_data = run_tv_cmd(["values"])
        if not symbol_data or not symbol_data.get("success"):
            return None
        all_data = [
            {
                "symbol": symbol_data.get("symbol", "N/A"),
                "description": symbol_data.get("description", ""),
                "exchange": quote_data.get("exchange", "") if quote_data else "",
                "timeframe": timeframe,
                "quote": {
                    "open": quote_data.get("open") if quote_data else None,
                    "high": quote_data.get("high") if quote_data else None,
                    "low": quote_data.get("low") if quote_data else None,
                    "close": quote_data.get("close") if quote_data else None,
                    "volume": quote_data.get("volume") if quote_data else None,
                }
                if quote_data
                else {},
                "studies": values_data.get("studies", []) if values_data else [],
            }
        ]
        return {"tabs": all_data, "tab_count": len(all_data), "timeframe": timeframe}
    except Exception as e:
        print(f"get_single_tab_data error: {e}")
        return None


def get_single_tab_data_via_cdp(timeframe="5"):
    """用 get_window_data.cjs 读取真正活跃的 chart tab 数据。

    走 _data._items 路径，能读到 Pine Script study 数据。
    """
    try:
        ws_url = _get_active_chart_ws_url()
        if not ws_url:
            return None

        tf_map = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60", "4h": "240", "1d": "1D"}
        tf_code = tf_map.get(timeframe, "5")

        if _platform.system() == "Windows":
            mw_script = Path(r"C:\projects\tradingview-mcp\get_window_data.cjs")
            mcp_root = r"C:\projects\tradingview-mcp"
        else:
            mw_script = _MULTI_WINDOW_SCRIPT
            mcp_root = str(Path(__file__).parent.parent.parent.parent / "tradingview-mcp")

        import os as _os
        node_env = _os.environ.copy()
        node_env["TV_HOST"] = TV_HOST
        node_env["TV_PORT"] = TV_PORT

        cmd = ["node", str(mw_script), ws_url, tf_code]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20,
            cwd=mcp_root,
            encoding="utf-8",
            errors="replace",
            env=node_env,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        data = json.loads(result.stdout.strip())
        tab = {
            "symbol": data.get("symbol", "N/A"),
            "exchange": data.get("exchange", ""),
            "description": data.get("description", ""),
            "timeframe": data.get("resolution", tf_code),
            "quote": data.get("quote", {}),
            "studies": _normalize_studies(data.get("studies", [])),
            "tab_index": 0,
        }
        return {"tabs": [tab], "tab_count": 1, "timeframe": timeframe, "mode": "single_via_cdp"}
    except Exception as e:
        print(f"get_single_tab_data_via_cdp error: {e}")
        import traceback
        traceback.print_exc()
        return None
