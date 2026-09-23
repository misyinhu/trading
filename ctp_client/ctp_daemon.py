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
import msvcrt
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
                deadline = time.time() + 30
                while time.time() < deadline and not state.get("ready"):
                    if state.get("phase") == "error":
                        raise RuntimeError(state.get("error", "login error"))
                    time.sleep(0.1)
                if not state.get("ready"):
                    raise RuntimeError("login timeout")
                W._log(f"[daemon {self.profile}] session ready")
                while self.alive and state.get("phase") != "disconnected":
                    time.sleep(1.0)
            except Exception as e:  # noqa: BLE001
                W._log(f"[daemon {self.profile}] connect error: {type(e).__name__}: {e}")
            try:
                if self.api is not None:
                    self.api.Release()
            except Exception:  # noqa: BLE001
                pass
            self.api = None
            time.sleep(3.0)

    def execute(self, action: str, order: dict, timeout: float) -> dict:
        with self.lock:
            if self.api is None or not getattr(self.spi, "daemon_session_ready", False):
                return {"ok": False, "status": "not_ready", "profile": self.profile,
                        "error": "CTP 会话未就绪（登录/重连中）"}
            try:
                # reset 在主线程执行；_dispatch_action 的 Req* 调用通常线程安全
                self.spi.reset_for_command(action, order)
                self.spi._dispatch_action()
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "status": "submit_error", "profile": self.profile,
                        "error": f"{type(e).__name__}: {e}"}
            action_deadline = time.time() + 8.0 if action in ("order", "cancel") else None
            # 查询类硬上限 9s：柜台连接静默断开时回调永不返回，不能让串行锁
            # 被一条死命令长期霸占（否则后续所有命令排队，表现为整柜卡死）。
            cap = timeout if action in ("order", "cancel") else min(timeout, 9.0)
            deadline = time.time() + cap
            completed = False
            while time.time() < deadline:
                if W._action_finished(self.state, self.spi, action, action_deadline):
                    completed = True
                    break
                time.sleep(0.05)
            if not completed:
                self._force_reconnect()
                return {"ok": False, "status": "not_ready", "profile": self.profile,
                        "error": f"柜台{action}无响应（{cap:.0f}s），已判定断连并重登，请稍后自动重试"}
            try:
                return W._build_result(self.state, self.cfg, action, order or {})
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "status": "result_error",
                        "error": f"{type(e).__name__}: {e}"}

    def _force_reconnect(self):
        """查询无响应：立即摘掉 ready 标记并释放连接，_connect 线程会自动重登。"""
        try:
            self.spi.daemon_session_ready = False
        except Exception:  # noqa: BLE001
            pass
        try:
            self.state["phase"] = "disconnected"
        except Exception:  # noqa: BLE001
            pass
        api = self.api

        def _release():
            try:
                if api is not None:
                    api.Release()
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=_release, daemon=True).start()

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
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
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
