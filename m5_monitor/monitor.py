#!/usr/bin/env python3
"""
M5 背离策略实时监控器

数据源: quant-core (TDX) via SSH tunnel localhost:8005
  - IC 期货: ICL8.CFF (中证500股指期货)
  - 中证500: 399905.SZ

策略参数 (已优化):
  - window=35, peak_order=3, hold_mult=1.0
  - |ic_delta| ≤ 3 时: 持仓缩短为 span × 0.5 (IC与IDX同向3倍幅度差, 高止损率行情)

监控逻辑:
  - 每5分钟轮询一次 (市场交易时段 9:30~15:00)
  - 描述当前行情特征 (价格/波幅/趋势)
  - 检测到新信号时立即推送飞书通知
  - 去重: 同一信号不重复通知
"""

import argparse
import json
import logging
import os
import sys
import time
import threading
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd

warnings.filterwarnings("ignore")

# ============ 路径和常量 ============

BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent
TRADING_NOTIFY = PROJECT_ROOT / "notify"

# quant-core TDX
QUANT_CORE = os.environ.get("QUANT_CORE_URL", "http://100.99.204.126:8005")
IC_SYMBOL = "ICL8.CFF"
IDX_SYMBOL = "399905.SZ"
SCALE_BAR = {"1m": "1m", "5m": "5m", "15m": "15m"}

# 日志
LOG_FILE = BASE_DIR / "logs" / "m5_monitor.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)

# 信号去重状态文件
SIGNAL_STATE_FILE = BASE_DIR / "data" / "m5_signal_state.json"


# ============ TDX 数据获取 (来自 scan_m1_tdx.py) ============


def get_tdx_bars(
    symbol: str,
    bar: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    num: Optional[int] = None,
) -> pd.DataFrame:
    """从 quant-core 拿 TDX K线"""
    params = {"symbol": symbol, "bar": bar}
    if num:
        params["num"] = num
    else:
        if start:
            params["start"] = start
        if end:
            params["end"] = end
    headers = {"X-Client-ID": "2"}
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.get(f"{QUANT_CORE}/api/history", params=params, headers=headers)
            data = r.json()
    except Exception as e:
        logging.error(f"TDX 请求失败 {symbol}: {e}")
        return pd.DataFrame()
    if not data or isinstance(data, dict):
        if isinstance(data, dict) and "detail" in data:
            logging.error(f"TDX 错误 {symbol}: {data['detail']}")
        return pd.DataFrame()
    rows = []
    for r in data:
        ts = pd.to_datetime(r["timestamp"])
        rows.append(
            {
                "datetime": ts,
                "date": ts.strftime("%Y-%m-%d"),
                "time": ts.strftime("%H:%M") if len(str(ts)) > 10 else "",
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r.get("volume", 0)),
            }
        )
    return pd.DataFrame(rows)


def get_tdx_bars_chunked(
    symbol: str, bar: str, start: str, end: str, chunk_days: int = 3
) -> pd.DataFrame:
    """按 chunk_days 分块拉取, 避免 TDX 单次大请求超时"""
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    chunks = []
    cur = start_dt
    while cur <= end_dt:
        chunk_end = min(cur + timedelta(days=chunk_days - 1), end_dt)
        df = get_tdx_bars(
            symbol,
            bar,
            start=cur.strftime("%Y-%m-%d"),
            end=chunk_end.strftime("%Y-%m-%d"),
        )
        if not df.empty:
            chunks.append(df)
        cur = chunk_end + timedelta(days=1)
    if not chunks:
        return pd.DataFrame()
    return (
        pd.concat(chunks, ignore_index=True)
        .drop_duplicates("datetime")
        .sort_values("datetime")
        .reset_index(drop=True)
    )


def get_data(period: str = "1m", days: int = 5) -> pd.DataFrame:
    """获取最近 N 天对齐的 IC + IDX K线"""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    bar = SCALE_BAR.get(period, "1m")

    ic = get_tdx_bars_chunked(IC_SYMBOL, bar, start=start, end=end)
    if ic.empty:
        logging.error("IC 数据为空")
        return pd.DataFrame()

    idx = get_tdx_bars_chunked(IDX_SYMBOL, bar, start=start, end=end)
    if idx.empty:
        logging.error("指数数据为空")
        return pd.DataFrame()

    merged = (
        pd.merge(
            ic[["datetime", "high", "low", "close"]].rename(
                columns={"high": "ic_high", "low": "ic_low", "close": "ic_close"}
            ),
            idx[["datetime", "high", "low", "close"]].rename(
                columns={"high": "idx_high", "low": "idx_low", "close": "idx_close"}
            ),
            on="datetime",
            how="inner",
        )
        .sort_values("datetime")
        .reset_index(drop=True)
    )
    merged["ma60"] = merged["ic_close"].rolling(60).mean()
    logging.info(
        f"数据: {len(merged)} 行, {merged['datetime'].min()} ~ {merged['datetime'].max()}"
    )
    return merged


# ============ 背离检测 (来自 scan_m1_tdx.py 已更新版) ============


def find_peaks(series: pd.Series, order: int = 3):
    highs, lows = [], []
    vals = series.values
    n = len(vals)
    for i in range(order, n - order):
        w = vals[i - order : i + order + 1]
        if vals[i] == w.max():
            highs.append(i)
        if vals[i] == w.min():
            lows.append(i)
    return highs, lows


def _closest(peaks, target, tol):
    if not peaks:
        return None
    best = min(peaks, key=lambda p: abs(p - target))
    return best if abs(best - target) <= tol else None


def detect_divergences(
    df: pd.DataFrame,
    window_bars: int = 35,
    peak_order: int = 3,
    tol: int = 3,
    ma60_tol: float = 2.0,
    no_intermediate_extreme: bool = True,
    hold_mult: float = 1.0,
    low_icd_hold_mult: float = 0.5,
    low_icd_threshold: float = 3.0,
) -> List[dict]:
    if len(df) < 10:
        return []

    ic_highs, _ = find_peaks(df["ic_high"], order=peak_order)
    _, ic_lows = find_peaks(df["ic_low"], order=peak_order)
    idx_highs, _ = find_peaks(df["idx_high"], order=peak_order)
    _, idx_lows = find_peaks(df["idx_low"], order=peak_order)
    has_ma60 = "ma60" in df.columns

    def span_between(p1, p2):
        return (df["datetime"].iloc[p2] - df["datetime"].iloc[p1]).total_seconds() / 60

    def mk_sig(p1, p2, ic_v1, ic_v2, idx_v1, idx_v2, kind, span, hm):
        t1 = df["datetime"].iloc[p1]
        t2 = df["datetime"].iloc[p2]
        return {
            "type": kind,
            "action": "做空 SHORT" if kind == "top" else "做多 LONG",
            "p1_time": t1,
            "p2_time": t2,
            "p1_ic": float(ic_v1),
            "p2_ic": float(ic_v2),
            "p1_idx": float(idx_v1),
            "p2_idx": float(idx_v2),
            "span_bars": round(span, 1),
            "hold_bars": round(span * hm, 1),
            "hold_until": t2 + timedelta(minutes=span * hm),
            "ic_delta": round(float(ic_v2) - float(ic_v1), 2),
            "idx_delta": round(float(idx_v2) - float(idx_v1), 2),
            "span_unit": "min",
        }

    top_sigs, bot_sigs = [], []

    # 顶背离 (做空)
    for i, p1 in enumerate(ic_highs):
        for p2 in ic_highs[i + 1 :]:
            span = span_between(p1, p2)
            if not (1 <= span <= window_bars):
                continue
            ic_v1, ic_v2 = df["ic_high"].iloc[p1], df["ic_high"].iloc[p2]
            if ic_v2 >= ic_v1:
                continue
            ic_delta = float(ic_v2) - float(ic_v1)
            hm = low_icd_hold_mult if abs(ic_delta) <= low_icd_threshold else hold_mult
            new_ext = None
            if no_intermediate_extreme and p2 > p1 + 1:
                mid_max = df["ic_high"].iloc[p1 + 1 : p2].max()
                if mid_max > ic_v1:
                    new_ext = mid_max
            idx_p1 = _closest(idx_highs, p1, tol)
            idx_p2 = _closest(idx_highs, p2, tol)
            if idx_p1 is None or idx_p2 is None:
                continue
            idx_v1, idx_v2 = df["idx_high"].iloc[idx_p1], df["idx_high"].iloc[idx_p2]
            if idx_v2 <= idx_v1:
                continue
            if has_ma60 and ma60_tol < 9999:
                m60 = df["ma60"].iloc[p2]
                if pd.notna(m60) and df["ic_close"].iloc[p2] < m60 - ma60_tol:
                    continue
            top_sigs.append(
                (
                    p1,
                    p2,
                    mk_sig(p1, p2, ic_v1, ic_v2, idx_v1, idx_v2, "top", span, hm),
                    new_ext,
                )
            )

    # 底背离 (做多)
    for i, p1 in enumerate(ic_lows):
        for p2 in ic_lows[i + 1 :]:
            span = span_between(p1, p2)
            if not (1 <= span <= window_bars):
                continue
            ic_v1, ic_v2 = df["ic_low"].iloc[p1], df["ic_low"].iloc[p2]
            if ic_v2 <= ic_v1:
                continue
            ic_delta = float(ic_v2) - float(ic_v1)
            hm = low_icd_hold_mult if abs(ic_delta) <= low_icd_threshold else hold_mult
            new_ext = None
            if no_intermediate_extreme and p2 > p1 + 1:
                mid_min = df["ic_low"].iloc[p1 + 1 : p2].min()
                if mid_min < ic_v1:
                    new_ext = mid_min
            idx_p1 = _closest(idx_lows, p1, tol)
            idx_p2 = _closest(idx_lows, p2, tol)
            if idx_p1 is None or idx_p2 is None:
                continue
            idx_v1, idx_v2 = df["idx_low"].iloc[idx_p1], df["idx_low"].iloc[idx_p2]
            if idx_v2 >= idx_v1:
                continue
            if has_ma60 and ma60_tol < 9999:
                m60 = df["ma60"].iloc[p2]
                if pd.notna(m60) and df["ic_close"].iloc[p2] > m60 + ma60_tol:
                    continue
            bot_sigs.append(
                (
                    p1,
                    p2,
                    mk_sig(p1, p2, ic_v1, ic_v2, idx_v1, idx_v2, "bottom", span, hm),
                    new_ext,
                )
            )

    def dedup(pairs):
        best_p1 = {}
        for p1, p2, sig, ne in pairs:
            cur = best_p1.get(p1)
            if cur is None or sig["span_bars"] > cur[1]["span_bars"]:
                best_p1[p1] = (p2, sig, ne)
        best_p2 = {}
        for p1, (_, sig, ne) in best_p1.items():
            cur = best_p2.get(sig["p2_time"])
            if cur is None or sig["span_bars"] > cur[0]["span_bars"]:
                best_p2[sig["p2_time"]] = (sig, ne)
        return [
            (sig, ne)
            for sig, ne in sorted(best_p2.values(), key=lambda x: x[0]["p1_time"])
        ]

    deduped = dedup(top_sigs) + dedup(bot_sigs)
    deduped.sort(key=lambda x: x[0]["p2_time"])

    signals, last_exit = [], None
    for sig, new_ext in deduped:
        if new_ext is not None and last_exit is not None:
            if abs(new_ext - last_exit) >= 0:
                pass  # exit_proximity=0 跳过
        signals.append(sig)
        target_ts = sig["p2_time"] + timedelta(minutes=sig["span_bars"] * hold_mult)
        future = df[df["datetime"] >= target_ts]
        last_exit = (
            float(future.iloc[0]["ic_close"])
            if not future.empty
            else float(df.iloc[-1]["ic_close"])
        )
    return signals


# ============ 飞书通知 ============


def load_feishu_notifier():
    """加载 trading 项目的飞书通知器"""
    try:
        sys.path.insert(0, str(TRADING_NOTIFY.parent))
        from notify.feishu import FeishuNotifier

        return FeishuNotifier()
    except Exception as e:
        logging.error(f"加载飞书通知器失败: {e}")
        return None


def send_signal_alert(notifier, signal: dict, market: dict):
    """发送背离信号飞书通知"""
    if notifier is None:
        return

    emoji = "📉" if signal["type"] == "top" else "📈"
    icd = signal["ic_delta"]
    idxd = signal["idx_delta"]
    div_ratio = abs(idxd) / max(abs(icd), 0.5)
    low_icd_tag = " ⚠️|ic_d|≤3 持仓×0.5" if abs(icd) <= 3.0 else ""

    # 行情描述
    market_lines = []
    if market:
        market_lines = [
            f"IC最新: {market.get('ic_last', 'N/A'):.2f}",
            f"IDX最新: {market.get('idx_last', 'N/A'):.2f}",
            f"今日IC波幅: {market.get('ic_daily_range', 'N/A'):.2f}%",
            f"MA60乖离: {market.get('ma60_dev', 'N/A'):.2f}%",
            f"信号密度: {market.get('signal_density', 'N/A')}信号/5min",
        ]

    message = f"""{emoji} M5 背离信号

方向: {signal["action"]}
入场时间: {signal["p2_time"].strftime("%H:%M")}
IC背离: {signal["ic_delta"]:+.2f} | IDX变动: {signal["idx_delta"]:+.2f}
div_ratio: {div_ratio:.2f} | 窗口跨度: {signal["span_bars"]:.0f}分钟{low_icd_tag}
持仓: {signal["hold_bars"]:.0f}分钟 → {signal["hold_until"].strftime("%H:%M")}止

行情状态:
{chr(10).join(market_lines)}

时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"""

    notifier.send_message(message)
    logging.info(f"飞书通知已发送: {signal['action']} @ {signal['p2_time']}")


# ============ 行情特征分析 ============


def describe_market(merged: pd.DataFrame, signals: List[dict]) -> dict:
    """描述当前行情特征"""
    if merged.empty or len(merged) < 60:
        return {}

    now = datetime.now()
    # 最近60根M1 (约1小时)
    recent = merged.tail(60).copy()
    ic_last = float(recent["ic_close"].iloc[-1])
    idx_last = float(recent["idx_close"].iloc[-1])

    # 今日数据
    today = now.strftime("%Y-%m-%d")
    today_data = merged[merged["datetime"].dt.strftime("%Y-%m-%d") == today]
    if len(today_data) > 0:
        ic_today_open = float(today_data["ic_close"].iloc[0])
        ic_today_high = float(today_data["ic_high"].max())
        ic_today_low = float(today_data["ic_low"].min())
        ic_daily_range = (ic_today_high - ic_today_low) / ic_today_open * 100
    else:
        ic_daily_range = 0.0

    # MA60 乖离
    ma60 = recent["ma60"].iloc[-1]
    ma60_dev = (ic_last - ma60) / ma60 * 100 if pd.notna(ma60) and ma60 != 0 else 0.0

    # 最近5分钟信号数量 (反映市场热度)
    last_5min = now - timedelta(minutes=5)
    sig_density = sum(1 for s in signals if s["p2_time"] >= last_5min)

    # 最近信号方向
    active_signals = [s for s in signals if s["hold_until"] > now]
    top_count = sum(1 for s in active_signals if s["type"] == "top")
    bot_count = sum(1 for s in active_signals if s["type"] == "bottom")

    # 近期IC趋势 (最近20根M1)
    recent_20 = merged.tail(20)
    ic_trend = (
        (float(recent_20["ic_close"].iloc[-1]) - float(recent_20["ic_close"].iloc[0]))
        / float(recent_20["ic_close"].iloc[0])
        * 100
    )

    return {
        "ic_last": ic_last,
        "idx_last": idx_last,
        "ic_daily_range": round(ic_daily_range, 2),
        "ma60_dev": round(ma60_dev, 2),
        "signal_density": sig_density,
        "active_short": top_count,
        "active_long": bot_count,
        "ic_trend_20m": round(ic_trend, 3),
    }


def format_market_report(market: dict) -> str:
    """格式化行情报告 (控制台输出)"""
    if not market:
        return "  行情数据不足"

    lines = [
        f"  IC: {market.get('ic_last', 0):.2f}  |  IDX: {market.get('idx_last', 0):.2f}",
        f"  今日IC波幅: {market.get('ic_daily_range', 0):.2f}%  |  MA60乖离: {market.get('ma60_dev', 0):+.2f}%",
        f"  IC趋势(20min): {market.get('ic_trend_20m', 0):+.3f}%  |  信号密度: {market.get('signal_density', 0)}信号/5min",
        f"  持仓中: 做空{market.get('active_short', 0)}笔 做多{market.get('active_long', 0)}笔",
    ]
    return "\n".join(lines)


# ============ 信号状态管理 ============


def get_signal_state() -> Dict[str, Any]:
    """读取已通知信号状态"""
    SIGNAL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SIGNAL_STATE_FILE.exists():
        try:
            with open(SIGNAL_STATE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"notified": []}


def save_signal_state(state: Dict[str, Any]):
    """保存信号状态"""
    SIGNAL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SIGNAL_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def is_new_signal(signal: dict, state: Dict[str, Any]) -> bool:
    """判断是否为新信号 (未通知过)"""
    sig_key = f"{signal['type']}_{signal['p2_time'].isoformat()}_{signal['ic_delta']}"
    return sig_key not in state.get("notified", [])


def mark_signal_notified(signal: dict, state: Dict[str, Any]):
    """标记信号已通知"""
    sig_key = f"{signal['type']}_{signal['p2_time'].isoformat()}_{signal['ic_delta']}"
    state.setdefault("notified", []).append(sig_key)
    # 只保留最近100条
    if len(state["notified"]) > 100:
        state["notified"] = state["notified"][-100:]


# ============ 监控核心 ============


class M5Monitor:
    """M5 背离监控器"""

    def __init__(self, interval_seconds: int = 300):
        self.interval = interval_seconds
        self.notifier = load_feishu_notifier()
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self.signal_state = get_signal_state()

        # 策略参数 (已优化)
        self.window = 35
        self.order = 3
        self.hold_mult = 1.0
        self.low_icd_hold_mult = 0.5
        self.low_icd_threshold = 3.0

    def _is_market_open(self) -> bool:
        """检查当前是否在交易时段 (9:30 ~ 15:00)"""
        now = datetime.now()
        if now.weekday() >= 5:  # 周末
            return False
        h, m = now.hour, now.minute
        total_min = h * 60 + m
        open_min = 9 * 60 + 30
        close_min = 15 * 60
        return open_min <= total_min <= close_min

    def _get_data_fresh(self, days: int = 3) -> pd.DataFrame:
        """获取最新数据"""
        try:
            return get_data("1m", days=days)
        except Exception as e:
            logging.error(f"获取数据失败: {e}")
            return pd.DataFrame()

    def _run_once(self):
        """执行一次监控"""
        now = datetime.now()
        print(f"\n{'=' * 60}")
        print(f"🕐 M5 背离监控 - {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 60}")

        if not self._is_market_open():
            print("  ⏭️ 非交易时段，跳过")
            return

        # 1. 获取数据
        merged = self._get_data_fresh(days=3)
        if merged.empty:
            logging.warning("无数据")
            return

        # 2. 检测信号
        signals = detect_divergences(
            merged,
            window_bars=self.window,
            peak_order=self.order,
            ma60_tol=2.0,
            no_intermediate_extreme=True,
            hold_mult=self.hold_mult,
            low_icd_hold_mult=self.low_icd_hold_mult,
            low_icd_threshold=self.low_icd_threshold,
        )
        print(f"  📊 检测到 {len(signals)} 条历史信号")

        # 3. 过滤出当前持仓中且未到期的信号
        active = [s for s in signals if s["hold_until"] > now]
        print(
            f"  📌 当前持仓中: {len(active)} 笔 (做空{sum(1 for s in active if s['type'] == 'top')} 做多{sum(1 for s in active if s['type'] == 'bottom')})"
        )

        # 4. 描述行情
        market = describe_market(merged, signals)
        print(format_market_report(market))

        # 5. 检测新信号并通知
        new_signals = [s for s in signals if is_new_signal(s, self.signal_state)]
        if new_signals:
            print(f"  🆕 新信号 {len(new_signals)} 条:")
            for sig in new_signals:
                div_ratio = abs(sig["idx_delta"]) / max(abs(sig["ic_delta"]), 0.5)
                low_tag = (
                    " ⚠️|ic_d|≤3"
                    if abs(sig["ic_delta"]) <= self.low_icd_threshold
                    else ""
                )
                print(
                    f"    {sig['action']} @ {sig['p2_time'].strftime('%H:%M')}  IC{sig['ic_delta']:+.1f} Idx{sig['idx_delta']:+.1f} ratio={div_ratio:.1f}{low_tag}"
                )
                send_signal_alert(self.notifier, sig, market)
                mark_signal_notified(sig, self.signal_state)
        else:
            print(f"  ⏭️ 无新信号")

        save_signal_state(self.signal_state)
        logging.info(
            f"监控完成: {len(signals)}信号, {len(active)}持仓中, {len(new_signals)}新信号"
        )

    def start(self):
        """启动定时监控"""
        if self.running:
            print("监控已在运行中")
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("✅ M5 背离监控已启动 (每5分钟轮询)")

    def _run_loop(self):
        while self.running:
            try:
                self._run_once()
            except Exception as e:
                logging.error(f"监控异常: {e}")
            time.sleep(self.interval)

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        print("🛑 M5 背离监控已停止")


# ============ CLI ============


def main():
    parser = argparse.ArgumentParser(description="M5 背离策略实时监控")
    parser.add_argument("--once", action="store_true", help="只运行一次")
    parser.add_argument(
        "--interval", type=int, default=300, help="轮询间隔秒数 (默认300)"
    )
    parser.add_argument("--window", type=int, default=35, help="窗口大小 (默认35)")
    parser.add_argument("--order", type=int, default=3, help="peak_order (默认3)")
    args = parser.parse_args()

    monitor = M5Monitor(interval_seconds=args.interval)
    monitor.window = args.window
    monitor.order = args.order

    if args.once:
        monitor._run_once()
    else:
        monitor.start()
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            monitor.stop()


if __name__ == "__main__":
    main()
