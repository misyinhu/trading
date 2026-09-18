"""Flask 蓝图：snapshot / stream(SSE) / subscribe / unsubscribe / health。

可挂进现有 trading 服务（register_blueprint），也可独立 run_worker.py 起服务。
"""
from __future__ import annotations

import json
import time

from flask import Blueprint, Response, jsonify, request


def create_blueprint(manager, store) -> Blueprint:
    bp = Blueprint("ctp_md", __name__)

    def _profiles():
        p = request.args.get("profile") or (request.get_json(silent=True) or {}).get("profile")
        return p

    @bp.get("/api/ctp/md/snapshot")
    def snapshot():
        profile = request.args.get("profile", "")
        instrument = request.args.get("instrument", "")
        if not profile or not instrument:
            return jsonify({"ok": False, "error": "profile/instrument 必填"}), 400
        if profile not in manager.profiles():
            return jsonify({"ok": False, "error": f"unknown profile: {profile}"}), 404
        tick = store.snapshot(profile, instrument)
        if tick is None:
            return jsonify({"ok": False, "error": "未订阅或尚无 tick",
                            "subscribed": instrument in manager.subs.get(profile)}), 404
        return jsonify({"ok": True, "tick": tick.to_dict()})

    @bp.get("/api/ctp/md/latest")
    def latest():
        profile = request.args.get("profile", "")
        if profile not in manager.profiles():
            return jsonify({"ok": False, "error": f"unknown profile: {profile}"}), 404
        iids = request.args.getlist("instrument") or None
        return jsonify({"ok": True, "ticks": store.latest(profile, iids)})

    @bp.get("/api/ctp/md/stream")
    def stream():
        profile = request.args.get("profile", "")
        iids = set(x for x in request.args.get("instruments", "").split(",") if x)
        if profile not in manager.profiles():
            return jsonify({"ok": False, "error": f"unknown profile: {profile}"}), 404
        wanted = {(profile, i) for i in iids} if iids else None

        def gen():
            q = store.subscribe()
            try:
                yield ": connected\n\n"
                # 连接建立先补发环形缓冲近期 tick（错过突发不漏根；客户端按 ts 去重）
                for t in store.catch_up(wanted):
                    yield f"data: {json.dumps(t.to_dict(), ensure_ascii=False)}\n\n"
                while True:
                    batch = store.drain(q, wanted, timeout=15.0)
                    if not batch:
                        yield ": keepalive\n\n"
                        continue
                    for t in batch:
                        yield f"data: {json.dumps(t.to_dict(), ensure_ascii=False)}\n\n"
            finally:
                store.unsubscribe(q)

        return Response(gen(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @bp.post("/api/ctp/md/subscribe")
    def subscribe():
        body = request.get_json(force=True, silent=True) or {}
        profile = body.get("profile", "")
        instruments = body.get("instruments") or []
        if profile not in manager.profiles() or not instruments:
            return jsonify({"ok": False, "error": "profile 不存在或 instruments 为空"}), 400
        cur = manager.subscribe(profile, instruments)
        return jsonify({"ok": True, "profile": profile, "subscriptions": sorted(cur)})

    @bp.post("/api/ctp/md/unsubscribe")
    def unsubscribe():
        body = request.get_json(force=True, silent=True) or {}
        profile = body.get("profile", "")
        instruments = body.get("instruments") or []
        if profile not in manager.profiles():
            return jsonify({"ok": False, "error": f"unknown profile: {profile}"}), 404
        cur = manager.unsubscribe(profile, instruments)
        return jsonify({"ok": True, "profile": profile, "subscriptions": sorted(cur)})

    @bp.get("/api/ctp/md/health")
    def md_health():
        h = manager.health()
        all_ok = all(v["state"] in ("logined", "idle") for v in h.values())
        return jsonify({"ok": all_ok, "profiles": h, "store": store.stats()})

    return bp


def health_components(manager) -> dict:
    """供 trading 主服务 /health 聚合：ctp_md_simnow / ctp_md_citic。"""
    out = {}
    for profile, h in manager.health().items():
        out[f"ctp_md_{profile}"] = {
            "ok": h["state"] in ("logined", "idle"),
            "state": h["state"],
            "message": h["message"],
            "subscriptions": h["subscriptions"],
            "tick_count": h["tick_count"],
            "last_tick_at": h["last_tick_at"],
        }
    return out
