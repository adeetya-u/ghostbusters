"""In-memory HydraDB activity log for connector stdout and UI."""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any

logger = logging.getLogger("ghostbusters.hydradb")

_log_lock = Lock()
_recent_logs: deque[dict[str, Any]] = deque(maxlen=50)


def recent_hydra_logs(limit: int = 20) -> list[dict[str, Any]]:
    with _log_lock:
        return list(_recent_logs)[-limit:]


def record_hydra_log(event: str, **fields: Any) -> None:
    entry = {
        "at": datetime.now(tz=timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    with _log_lock:
        _recent_logs.append(entry)
    logger.info("[hydradb] %s %s", event, " ".join(f"{k}={v!r}" for k, v in fields.items()))
