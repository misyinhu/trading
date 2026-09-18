"""每 profile 订阅集持久化（JSON state 文件），重启/重连后自动恢复。"""
from __future__ import annotations

import json
import threading
from pathlib import Path


class SubscriptionStore:
    def __init__(self, state_path: str | Path) -> None:
        self.path = Path(state_path)
        self._lock = threading.RLock()
        self._sets: dict[str, set[str]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for profile, iids in (raw.get("profiles") or {}).items():
                self._sets[profile] = set(iids)
        except (ValueError, OSError):
            # 损坏文件不阻断启动，按空订阅启动
            self._sets = {}

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"profiles": {p: sorted(s) for p, s in self._sets.items()}}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, profile: str) -> set[str]:
        with self._lock:
            return set(self._sets.get(profile, set()))

    def update(self, profile: str, add: list[str] | None = None,
               remove: list[str] | None = None) -> set[str]:
        """幂等增删，返回变更后订阅集；实际有变化才落盘。"""
        with self._lock:
            cur = self._sets.setdefault(profile, set())
            before = set(cur)
            if add:
                cur.update(i.strip() for i in add if i and i.strip())
            if remove:
                cur.difference_update(i.strip() for i in remove if i and i.strip())
            if cur != before:
                self._flush()
            return set(cur)
