from __future__ import annotations

from datetime import datetime, timezone
from collections import deque
from pathlib import Path
from typing import Any
import json
import os
import re
import threading
import uuid


AUDIT_LOG_NAME = ".lan-transfer-audit.jsonl"
DEFAULT_AUDIT_LIMIT = 100
MAX_AUDIT_LIMIT = 500
REDACTED = "[redacted]"
SENSITIVE_FIELD_NAMES = {
    "authorization",
    "cookie",
    "current_password",
    "new_password",
    "password",
    "secret",
    "session",
    "session_token",
    "token",
    "x_admin_session",
    "x_user_session",
}
SENSITIVE_FIELD_PARTS = {"authorization", "cookie", "password", "secret", "session", "token"}


def _normalized_key(key: object) -> str:
    text = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", str(key))
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _is_sensitive_key(key: object) -> bool:
    normalized = _normalized_key(key)
    parts = set(normalized.split("_"))
    return (
        normalized in SENSITIVE_FIELD_NAMES
        or bool(parts.intersection(SENSITIVE_FIELD_PARTS))
        or normalized.endswith("_password")
        or normalized.endswith("_secret")
        or normalized.endswith("_token")
    )


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_sensitive_key(key) else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_sensitive(item) for item in value]
    return value


class AuditManager:
    def __init__(self, save_dir: Path):
        self.save_dir = save_dir
        self.path = self.save_dir / AUDIT_LOG_NAME
        self._lock = threading.RLock()

    def record(
        self,
        *,
        action: str,
        actor: str,
        role: str,
        client_ip: str,
        target_type: str,
        target_id: str | None = None,
        target_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "id": uuid.uuid4().hex,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "actor": actor,
            "role": role,
            "client_ip": client_ip,
            "target_type": target_type,
            "target_id": target_id,
            "target_name": target_name,
            "metadata": redact_sensitive(metadata or {}),
        }
        with self._lock:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
        return dict(event)

    def recent(self, limit: int = DEFAULT_AUDIT_LIMIT) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or DEFAULT_AUDIT_LIMIT), MAX_AUDIT_LIMIT))
        if not self.path.exists():
            return []

        events: deque[dict[str, Any]] = deque(maxlen=limit)
        with self._lock:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(event, dict):
                        events.append(event)
        return list(reversed(events))

    def size_bytes(self) -> int:
        try:
            return os.path.getsize(self.path)
        except FileNotFoundError:
            return 0
