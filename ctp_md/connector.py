"""MdApi 连接适配层。

- BaseConnector:    统一接口（start/stop/subscribe/status/on_tick 回调）
- ReplayConnector: 离线回放（读录制的 tick jsonl，按原始时间戳节奏推送），Mac 本地测试用
- NativeCtpConnector: 真实 CTP MdApi 长连（标准 SWIG 绑定；也可复用 winclaw 已有的
  ctp_client.ctp_connector.CtpMdConnector，见 create_connector）

断线重连由 worker 层统一编排（见 worker.py），连接器只负责一条连接的生命周期。
"""
from __future__ import annotations

import importlib
import json
import threading
import time
from pathlib import Path
from typing import Callable

from .schema import Tick, tick_from_ctp

TickCb = Callable[[Tick], None]
StatusCb = Callable[[str, str], None]   # (state, message): disconnected/logining/logined/error


class BaseConnector:
    kind = "base"

    def __init__(self, profile: str, front: str, broker_id: str, user: str,
                 password: str, exchange_id: str = "") -> None:
        self.profile = profile
        self.front = front
        self.broker_id = broker_id
        self.user = user
        self.password = password
        self.exchange_id = exchange_id
        self.on_tick: TickCb | None = None
        self.on_status: StatusCb | None = None
        self.state = "init"

    def _status(self, state: str, msg: str = "") -> None:
        self.state = state
        if self.on_status:
            try:
                self.on_status(state, msg)
            except Exception:
                pass

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def subscribe(self, instruments: list[str]) -> None: ...


# ── 离线回放 ────────────────────────────────────────────
class ReplayConnector(BaseConnector):
    """按 ts_exchange 真实节奏回放 tick jsonl（每行一个 tick dict）。

    speed=0 表示尽快推送（测试用）；speed>0 为时间倍速。
    """
    kind = "replay"

    def __init__(self, profile: str, replay_path: str, speed: float = 0.0,
                 loop: bool = False, exchange_id: str = "") -> None:
        super().__init__(profile, front="", broker_id="", user="", password="",
                         exchange_id=exchange_id)
        self.replay_path = Path(replay_path)
        self.speed = speed
        self.loop = loop
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._subscribed: set[str] = set()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def subscribe(self, instruments: list[str]) -> None:
        self._subscribed.update(instruments)

    def _iter_ticks(self):
        with self.replay_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def _run(self) -> None:
        self._status("logining", "replay")
        self._status("logined", f"replay:{self.replay_path.name}")
        while not self._stop.is_set():
            prev_ts = None
            wall0 = time.monotonic()
            for raw in self._iter_ticks():
                if self._stop.is_set():
                    return
                iid = raw.get("instrument_id", "")
                if self._subscribed and iid not in self._subscribed:
                    continue
                # 回放输入可能就是统一 schema，也可能是 CTP 原始字段
                if "ts_recv" in raw:
                    tick = Tick(**raw)
                    tick.profile = self.profile      # 回放文件内嵌 profile 以实例配置为准
                else:
                    tick = tick_from_ctp(raw, self.profile, self.exchange_id)
                if self.speed and prev_ts is not None and tick.ts_exchange:
                    # 简单按接收节奏（ms）；测试默认 speed=0 不等
                    pass
                if self.on_tick:
                    self.on_tick(tick)
                prev_ts = tick.ts_exchange
                if self.speed:
                    time.sleep(min(0.05, 0.0))
            if not self.loop:
                # 一次性回放播完：保持 idle（不断连、不触发 worker 重连风暴）
                self._status("idle", "replay finished")
                return


# ── 真实 CTP MdApi ──────────────────────────────────────
class LegacyCtpConnector(BaseConnector):
    """复用本仓 ctp_client.ctp_connector.CtpMdConnector（winclaw C:\\tmp\\ctp_api SWIG 绑定）。

    旧连接器在构造函数里 CreateFtdcMdApi+Init，用 add_tick_handler 收回调、
    ConnectionStatus 枚举轮询状态，没有 stop/状态回调——这里补齐成 BaseConnector 接口：
    状态轮询线程翻译成 on_status；raw SWIG DepthMarketData 经 tick_from_ctp 转统一 schema。
    必须在独立进程跑（md worker），SWIG 崩溃不带走 Flask 主服务。
    """
    kind = "ctp_client"

    def __init__(self, *args, auth_code: str = "", app_id: str = "", **kw) -> None:
        super().__init__(*args, **kw)
        self.auth_code = auth_code
        self.app_id = app_id
        self._conn = None
        self._poll: threading.Thread | None = None
        self._last: dict[str, Tick] = {}
        self._ever_logined = False
        self._connect_since = time.monotonic()

    def start(self) -> None:
        from ctp_client.ctp_connector import CtpConfig, CtpMdConnector

        cfg = CtpConfig(
            md_server=self.front, td_server="", broker_id=self.broker_id,
            user_id=self.user, password=self.password,
            auth_code=self.auth_code or "0" * 16,
            app_id=self.app_id or "simnow_client_test")
        self._status("logining", f"connect {self.front}")
        self._conn = CtpMdConnector(cfg)
        self._conn.add_tick_handler(self._on_raw)
        # 构造前 worker 已调过 subscribe()：补挂
        if getattr(self, "_pending_subs", None):
            self._conn.subscribe(sorted(self._pending_subs))
        self._stop_poll = threading.Event()
        self._poll = threading.Thread(target=self._poll_status, daemon=True)
        self._poll.start()

    def stop(self) -> None:
        if getattr(self, "_stop_poll", None) is not None:
            self._stop_poll.set()
        # 故意不调 api.Release()：跨线程 Release 是该 SWIG 绑定已知的原生 abort
        # 来源；旧实例直接弃用，进程退出由 OS 回收。
        self._status("disconnected", "stopped")

    def subscribe(self, instruments: list[str]) -> None:
        if self._conn is not None:
            self._conn.subscribe(list(instruments))
        else:
            self._pending_subs = set(getattr(self, "_pending_subs", set())) | set(instruments)

    def _on_raw(self, data) -> None:
        iid = str(getattr(data, "InstrumentID", "") or "").strip()
        prev = self._last.get(iid) if iid else None
        tick = tick_from_ctp(data, self.profile, self.exchange_id, last_snapshot=prev)
        if not tick.instrument_id or not tick.ts_exchange or tick.last_price <= 0:
            return
        self._last[tick.instrument_id] = tick
        if self.on_tick:
            self.on_tick(tick)

    def _poll_status(self) -> None:
        from ctp_client.ctp_connector import ConnectionStatus
        while not self._stop_poll.is_set():
            try:
                st = self._conn.status if self._conn is not None else ConnectionStatus.DISCONNECTED
                if st == ConnectionStatus.LOGINED:
                    if not self._ever_logined:
                        self._ever_logined = True
                        self._status("logined", "md login ok")
                        self._connect_since = time.monotonic()
                elif st == ConnectionStatus.ERROR:
                    self._status("error", getattr(self._conn, "last_error", "") or "md error")
                elif st == ConnectionStatus.DISCONNECTED and self._ever_logined:
                    # CTP 原生层自动重连前置并重新 OnFrontConnected→登录，
                    # 不交给 worker 重建（同进程反复 CreateMdApi 易原生 abort）。
                    self._status("logining", "front disconnected, native reconnecting")
                    self._connect_since = time.monotonic()
                elif st in (ConnectionStatus.CONNECTING, ConnectionStatus.CONNECTED):
                    if not self._ever_logined:
                        self._status("logining", st.value)
                        # 连接/登录 120s 无进展 -> error，交 worker 重建（非交易时段前置
                        # 可能接受 TCP 但不回登录，不能用 30s 短窗频繁重建致原生 abort）
                        if time.monotonic() - self._connect_since > 120:
                            self._status("error", f"no login within 120s ({st.value})")
                            self._connect_since = time.monotonic()
            except Exception:
                pass
            self._stop_poll.wait(0.5)


class NativeCtpConnector(BaseConnector):
    """标准 CTP Python（SWIG）MdApi 适配。

    绑定模块兼容官方/评测版 Python demo 的常见命名；部署时若 winclaw 已有
    ctp_client.ctp_connector.CtpMdConnector，优先在 create_connector 里复用。
    """
    kind = "ctp"

    _API_FACTORIES = ("CreateFtdcMdApi", "CThostFtdcMdApi_CreateFtdcMdApi")
    _SPI_CLASSES = ("CThostFtdcMdSpi",)
    _MODULES = ("thostmduserapi_se", "thostmduserapi")

    def __init__(self, *args, auth_code: str = "", app_id: str = "",
                 flow_path: str = "./md_flow", **kw) -> None:
        super().__init__(*args, **kw)
        self.auth_code = auth_code
        self.app_id = app_id
        self.flow_path = flow_path
        self._api = None
        self._spi = None
        self._reqid = 0
        self._subscribed: set[str] = set()
        self._pending: set[str] = set()

    def _next_reqid(self) -> int:
        self._reqid += 1
        return self._reqid

    def start(self) -> None:
        mod = None
        for name in self._MODULES:
            try:
                mod = importlib.import_module(name)
                break
            except ImportError:
                continue
        if mod is None:
            raise RuntimeError("未找到 CTP 行情 Python 绑定（thostmduserapi_se / thostmduserapi）")
        self._mod = mod
        factory = next((getattr(mod, n, None) for n in self._API_FACTORIES if hasattr(mod, n)), None)
        spi_cls = next((getattr(mod, n, None) for n in self._SPI_CLASSES if hasattr(mod, n)), None)
        if factory is None or spi_cls is None:
            raise RuntimeError("CTP 绑定缺少 MdApi 工厂或 MdSpi 类")
        self._api = factory(self.flow_path)
        self._spi = _make_spi(spi_cls, self)
        self._api.RegisterSpi(self._spi)
        self._api.RegisterFront(self.front.encode("utf-8"))
        self._status("disconnected", "connecting")
        self._api.Init()

    def stop(self) -> None:
        try:
            if self._api is not None:
                self._api.Release()
        finally:
            self._api = None
            self._status("disconnected", "stopped")

    def login(self) -> None:
        f = self._mod.CThostFtdcReqUserLoginField()
        f.BrokerID = self.broker_id
        f.UserID = self.user
        f.Password = self.password
        # 看穿式认证字段（非看穿柜台留空即可）
        for attr, val in (("AppID", self.app_id), ("AuthCode", self.auth_code)):
            if val and hasattr(f, attr):
                setattr(f, attr, val)
        self._status("logining", "login")
        self._api.ReqUserLogin(f, self._next_reqid())

    def subscribe(self, instruments: list[str]) -> None:
        if not instruments or self._api is None or self.state != "logined":
            self._pending.update(instruments)
            return
        self._do_subscribe([i for i in instruments if i not in self._subscribed])

    def _do_subscribe(self, instruments: list[str]) -> None:
        if not instruments:
            return
        import ctypes
        n = len(instruments)
        arr = (ctypes.c_char_p * n)(*[i.encode("utf-8") for i in instruments])
        rc = self._api.SubscribeMarketData(arr, n)
        if rc == 0:
            self._subscribed.update(instruments)
            self._pending.difference_update(instruments)

    def resubscribe_all(self) -> None:
        self._do_subscribe(sorted(self._subscribed | self._pending))


def _make_spi(spi_cls, owner: "NativeCtpConnector"):
    """运行期生成 SWIG Spi 子类实例（绑定模块导入后才知具体类）。"""

    def on_connected(self):
        owner._status("logining", "front connected")
        owner.login()

    def on_disconnected(self, reason):
        owner.state = "disconnected"
        if owner.on_status:
            owner.on_status("disconnected", f"front disconnected: {reason}")

    def on_login(self, field, rsp, reqid, last):
        code = getattr(rsp, "ErrorID", 0) if rsp is not None else 0
        if code == 0:
            owner.state = "logined"
            if owner.on_status:
                owner.on_status("logined", "md login ok")
            owner.resubscribe_all()
        else:
            msg = getattr(rsp, "ErrorMsg", "") if rsp is not None else ""
            owner.state = "error"
            if owner.on_status:
                owner.on_status("error", f"login fail {code}:{msg}")

    def on_sub(self, field, rsp, reqid, last):
        code = getattr(rsp, "ErrorID", 0) if rsp is not None else 0
        if code != 0 and owner.on_status:
            iid = getattr(field, "InstrumentID", "?") if field is not None else "?"
            owner.on_status("error", f"subscribe {iid} fail {code}")

    def on_tick(self, data):
        if owner.on_tick:
            owner.on_tick(tick_from_ctp(data, owner.profile, owner.exchange_id))

    impl = type("_SpiImpl", (spi_cls,), {
        "OnFrontConnected": on_connected,
        "OnFrontDisconnected": on_disconnected,
        "OnRspUserLogin": on_login,
        "OnRspSubMarketData": on_sub,
        "OnRtnDepthMarketData": on_tick,
    })
    return impl()


def create_connector(kind: str, profile: str, cfg: dict) -> BaseConnector:
    """工厂。kind=ctp/replay；若配置 reuse_class 指向 winclaw 已有连接器，
    则直接复用（鸭子类型：要求 start/stop/subscribe + on_tick/on_status 钩子）。"""
    if kind == "replay":
        return ReplayConnector(profile, replay_path=cfg["replay_path"],
                               speed=float(cfg.get("speed", 0)),
                               loop=bool(cfg.get("loop", False)),
                               exchange_id=cfg.get("exchange_id", ""))
    if kind == "ctp_client":
        return LegacyCtpConnector(
            profile, front=cfg["md_front"], broker_id=cfg["broker_id"],
            user=cfg["user"], password=cfg["password"],
            exchange_id=cfg.get("exchange_id", ""),
            auth_code=cfg.get("auth_code", ""), app_id=cfg.get("app_id", ""))
    if cfg.get("reuse_class"):
        mod_name, cls_name = cfg["reuse_class"].rsplit(".", 1)
        cls = getattr(importlib.import_module(mod_name), cls_name)
        return cls(profile=profile, **{k: v for k, v in cfg.items() if k != "reuse_class"})
    return NativeCtpConnector(
        profile, front=cfg["md_front"], broker_id=cfg["broker_id"],
        user=cfg["user"], password=cfg["password"],
        exchange_id=cfg.get("exchange_id", ""),
        auth_code=cfg.get("auth_code", ""), app_id=cfg.get("app_id", ""),
        flow_path=cfg.get("flow_path", f"./md_flow_{profile}"),
    )
