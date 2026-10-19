#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CTP 常驻交易 daemon（per-profile 单进程）。

替代旧的"每个请求拉起一次性 ctp_worker 子进程"模式：登录+认证+结算确认只做
一次，之后通过 localhost TCP 接收命令（query/depth/trades/instruments/order/
cancel/...），串行投递给同一个已登录会话，毫秒级返回。断线自动重连；命令执行
线程与 CTP 回调线程通过共享 state + 完成标志协作。

协议（单连接，一命令一响应）：
  行 JSON 请求: {"id": "...", "action": "depth", "order": {...}, "timeout": 8}
  行 JSON 响应: {"id": "...", "ok": true, ...}

用法:
  python ctp_daemon.py --profile citic --port 5012
健康检查:
  python ctp_daemon.py --profile citic --ping --port 5012
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import socketserver
import sys
import threading
import time
try:
    import msvcrt  # Windows
except ImportError:  # POSIX（dev/mac 测试可导入运行）
    msvcrt = None
    import fcntl
from pathlib import Path

# ctp_worker 在模块导入时即按 CTP_PROFILE 选择 SWIG 绑定目录（中信 CP 柜台必须
# 加载 6.5.1CP 绑定，否则握手 4040 decode err），故 import 前先解析 profile。
for _i, _a in enumerate(sys.argv):
    if _a == "--profile" and _i + 1 < len(sys.argv):
        os.environ["CTP_PROFILE"] = sys.argv[_i + 1]

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ctp_worker as W  # noqa: E402


class _Session:
    """持有单个 profile 的长期 api/spi，并负责串行执行命令。"""

    def __init__(self, profile: str):
        self.profile = profile
        self.cfg = W._load_config(profile)
        self.api = None
        self.spi = None
        self.state: dict = {}
        self.lock = threading.Lock()
        self.alive = True
        if self.cfg.get("_missing"):
            raise RuntimeError(f"profile={profile} 缺少配置: {', '.join(self.cfg['_missing'])}")
        threading.Thread(target=self._connect, daemon=True).start()

    def _connect(self):
        while self.alive:
            try:
                state = W._init_state(self.profile, self.cfg.get("label", self.profile))
                state["daemon_mode"] = True
                api = W.T.CThostFtdcTraderApi.CreateFtdcTraderApi("")
                spi = W.TraderSpi(api, self.cfg, state, action="query", order={})
                W._API, W._SPI = api, spi
                api.RegisterSpi(spi)
                api.SubscribePrivateTopic(2)
                api.SubscribePublicTopic(2)
                api.RegisterFront(self.cfg["td_server"])
                api.Init()
                self.api, self.spi, self.state = api, spi, state
                # 2026-10-16 8h 抽风根因修复：登录 30s 未就绪时不再 Release+重建。
                # 前置机抖动期 Release 与 CTP 回调线程竞争会原生 abort，进程被杀 →
                # 桥再拉新 daemon → 再 30s 超时 → 再 abort，形成 18-20s 死循环。
                # 正确做法与 md worker 一致：会话只建一次，断线靠 CTP 原生自动重连，
                # 这里无限期等 ready（每 60s 打一条等待日志），显式 login error 才退。
                deadline = time.time() + 30
                last_wait_log = 0.0
                while not state.get("ready"):
                    if state.get("phase") == "error":
                        # 显式错误（如认证失败）不会自愈：直接退进程（不 Release，
                        # 避免退出路径再触发原生 abort），由桥带 backoff 重启。
                        W._log(f"[daemon {self.profile}] login error: "
                               f"{state.get('error', 'unknown')}，退出待重启")
                        os._exit(2)
                    now = time.time()
                    if now >= deadline and now - last_wait_log >= 60:
                        last_wait_log = now
                        W._log(f"[daemon {self.profile}] 等待 CTP 登录就绪中"
                               f"（{int(now - deadline) + 30}s，靠原生重连）")
                    time.sleep(0.5)
                W._log(f"[daemon {self.profile}] session ready")
                # 断线不退出、不重建：CTP 原生会 OnFrontDisconnected→自动重连→
                # OnFrontConnected→重认证→重登录，全程复用同一 api 实例。
                # 但查询挂死触发的 _force_reconnect 只摘标记——若 TCP 层未真断，
                # 原生重连不会触发，会话会永久 wedge（09:28 开盘事故实测）。
                # 兜底：持续 not_ready 超过 120s 且原生重连没把 phase 推回
                # connected 流程，则退进程让桥带 backoff 重启，恢复自愈闭环。
                not_ready_since = time.time()
                while self.alive:
                    time.sleep(1.0)
                    if getattr(self.spi, "daemon_session_ready", False):
                        not_ready_since = time.time()
                    elif state.get("phase") not in ("disconnected",):
                        # 原生重连已启动（authenticating/logging_in），重置计时
                        not_ready_since = time.time()
                    elif time.time() - not_ready_since > 120:
                        W._log(f"[daemon {self.profile}] not_ready 持续 120s "
                               f"且原生重连未启动，退出待桥重启（自愈）")
                        os._exit(3)
            except Exception as e:  # noqa: BLE001
                W._log(f"[daemon {self.profile}] connect error: {type(e).__name__}: {e}")
            time.sleep(3.0)

    def execute(self, action: str, order: dict, timeout: float) -> dict:
        with self.lock:
            if self.api is None or not getattr(self.spi, "daemon_session_ready", False):
                return {"ok": False, "status": "not_ready", "profile": self.profile,
                        "error": "CTP 会话未就绪（登录/重连中）"}
            try:
                # reset 在主线程执行；_dispatch_action 的 Req* 调用通常线程安全
                W._log(f"[daemon {self.profile}] execute {action} begin")
                self.spi.reset_for_command(action, order)
                self.spi._dispatch_action()
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "status": "submit_error", "profile": self.profile,
                        "error": f"{type(e).__name__}: {e}"}
            action_deadline = time.time() + 8.0 if action in ("order", "cancel") else None
            # 查询类硬上限 9s：柜台连接静默断开时回调永不返回，不能让串行锁
            # 被一条死命令长期霸占（否则后续所有命令排队，表现为整柜卡死）。
            # 例外：instruments/main_contract/main_board 需全市场合约查询 +
            # 串行行情查询（~1s/合约），本身就要几十秒，给足 timeout。
            if action in ("order", "cancel", "instruments", "main_contract", "main_board"):
                cap = timeout
            else:
                cap = min(timeout, 9.0)
            deadline = time.time() + cap
            completed = False
            while time.time() < deadline:
                if W._action_finished(self.state, self.spi, action, action_deadline):
                    completed = True
                    break
                time.sleep(0.05)
            if not completed:
                if action == "depth":
                    # 只读行情查询：柜台对摘牌/流控合约可能 ret=0 但永不回调
                    # （au2610 实测）。绝不能为此 force_reconnect——那会拖死
                    # 整条会话（下单/持仓全 not_ready，2026-10-19 14:59 事故）。
                    return {"ok": False, "status": "no_quote", "profile": self.profile,
                            "error": f"行情查询{cap:.0f}s无回调（合约摘牌/流控），不影响交易会话"}
                self._force_reconnect()
                return {"ok": False, "status": "not_ready", "profile": self.profile,
                        "error": f"柜台{action}无响应（{cap:.0f}s），已判定断连并重登，请稍后自动重试"}
            try:
                return W._build_result(self.state, self.cfg, action, order or {})
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "status": "result_error",
                        "error": f"{type(e).__name__}: {e}"}

    def _force_reconnect(self):
        """查询无响应：立即摘掉 ready 标记。不再 Release api——跨线程 Release
        会原生 abort（2026-10-16 抽风根因），CTP 原生心跳发现断线后自动重登。"""
        try:
            self.spi.daemon_session_ready = False
        except Exception:  # noqa: BLE001
            pass
        try:
            self.state["phase"] = "disconnected"
        except Exception:  # noqa: BLE001
            pass
        W._log(f"[daemon {self.profile}] force_reconnect: 命令超时，摘除 ready 标记"
               f"（等原生重连；120s 未恢复将退进程自愈）")

    def health(self) -> dict:
        return {"ok": bool(getattr(self.spi, "daemon_session_ready", False)),
                "profile": self.profile,
                "phase": self.state.get("phase", "init"),
                "trading_day": self.state.get("trading_day", ""),
                "investor": self.state.get("investor", "")}


_SINGLE_LOCK = None


def _acquire_single_lock(profile: str) -> bool:
    """Windows 单实例文件锁：锁已被占用说明已有 daemon 在跑，本实例立即退出。
    文件句柄全程保持强引用，进程退出时 OS 自动释放。"""
    global _SINGLE_LOCK
    lock_path = Path(__file__).resolve().parent.parent / "logs" / f"ctp_daemon_{profile}.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        f = open(lock_path, "a+b")
        if msvcrt is not None:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        f.seek(0)
        f.truncate()
        f.write(str(os.getpid()).encode())
        f.flush()
        _SINGLE_LOCK = f
        return True
    except OSError:
        return False


_SESSION: _Session | None = None
_SESSION_LOCK = threading.Lock()


def _get_session(profile: str) -> _Session:
    global _SESSION
    with _SESSION_LOCK:
        if _SESSION is None:
            _SESSION = _Session(profile)
        return _SESSION


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        for raw in self.rfile:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except Exception as e:  # noqa: BLE001
                resp = {"ok": False, "status": "bad_json", "error": str(e)}
                self.wfile.write((json.dumps(resp, ensure_ascii=False) + "\n").encode())
                self.wfile.flush()
                continue
            rid = req.get("id")
            if req.get("action") == "ping":
                resp = _get_session(req.get("profile", "citic")).health()
            else:
                resp = _get_session(req.get("profile", "citic")).execute(
                    req.get("action", "query"), req.get("order") or {},
                    float(req.get("timeout", 10)))
            resp["id"] = rid
            self.wfile.write((json.dumps(resp, ensure_ascii=False) + "\n").encode())
            self.wfile.flush()


class _Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _send(port: int, payload: dict, timeout: float = 35.0) -> dict:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        s.settimeout(timeout)
        f = s.makefile("rwb")
        f.write((json.dumps(payload) + "\n").encode())
        f.flush()
        return json.loads(f.readline().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="citic")
    ap.add_argument("--port", type=int, default=5012)
    ap.add_argument("--ping", action="store_true")
    args = ap.parse_args()
    if args.ping:
        print(json.dumps(_send(args.port, {"action": "ping", "profile": args.profile}, 8),
                         ensure_ascii=False))
        return
    if not _acquire_single_lock(args.profile):
        print("another daemon for this profile is already running; exiting", flush=True)
        sys.exit(0)
    sess = _get_session(args.profile)
    srv = _Server(("127.0.0.1", args.port), _Handler)
    W._log(f"[daemon {args.profile}] listening 127.0.0.1:{args.port}")
    try:
        srv.serve_forever()
    finally:
        sess.alive = False


if __name__ == "__main__":
    main()
