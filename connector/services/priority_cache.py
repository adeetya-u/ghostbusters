"""In-memory cache for Nebius-generated priorities with background refresh."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from imessage.reader import IMessageReader

from services.priorities import (
    ResponsePriority,
    SuggestionGenerationError,
    build_fast_priorities,
    get_top_priorities,
)

CACHE_TTL_SECONDS = int(__import__("os").environ.get("PRIORITY_CACHE_TTL", "300"))


@dataclass
class _CacheEntry:
    items: list[ResponsePriority]
    fetched_at: datetime
    refresh_in_progress: bool = False


_lock = threading.Lock()
_cache: dict[str, _CacheEntry] = {}


def _cache_key(limit: int) -> str:
    return f"top:{limit}"


def _is_fresh(entry: _CacheEntry) -> bool:
    age = (datetime.now(tz=timezone.utc) - entry.fetched_at).total_seconds()
    return age < CACHE_TTL_SECONDS


def get_cached_top_priorities(
    reader: IMessageReader,
    limit: int = 3,
    *,
    refresh: bool = False,
) -> tuple[list[ResponsePriority], bool]:
    """
    Return priorities without blocking on Nebius/Hydra generation.
    Serves cached/full results when ready; otherwise returns ranked placeholders
    and refreshes in the background.
    """
    key = _cache_key(limit)

    with _lock:
        entry = _cache.get(key)

        if entry and entry.items and not refresh:
            if not _is_fresh(entry) and not entry.refresh_in_progress:
                entry.refresh_in_progress = True
                threading.Thread(
                    target=_refresh_top,
                    args=(reader, limit, key),
                    daemon=True,
                ).start()
            return entry.items, True

        if entry and entry.items and refresh:
            if not entry.refresh_in_progress:
                entry.refresh_in_progress = True
                threading.Thread(
                    target=_refresh_top,
                    args=(reader, limit, key),
                    daemon=True,
                ).start()
            return entry.items, True

        if entry and entry.refresh_in_progress:
            pass
        else:
            _cache[key] = _CacheEntry(
                items=entry.items if entry else [],
                fetched_at=entry.fetched_at if entry else datetime.min.replace(tzinfo=timezone.utc),
                refresh_in_progress=True,
            )
            threading.Thread(
                target=_refresh_top,
                args=(reader, limit, key),
                daemon=True,
            ).start()

    return build_fast_priorities(reader, limit=limit), False


def prefetch_top_priorities(reader: IMessageReader, limit: int = 3) -> None:
    """Warm the cache in a background thread (no-op if already fresh)."""
    key = _cache_key(limit)
    with _lock:
        entry = _cache.get(key)
        if entry and entry.items and _is_fresh(entry):
            return
        if entry and entry.refresh_in_progress:
            return
        if entry:
            entry.refresh_in_progress = True
        else:
            _cache[key] = _CacheEntry(
                items=[],
                fetched_at=datetime.min.replace(tzinfo=timezone.utc),
                refresh_in_progress=True,
            )

    threading.Thread(target=_refresh_top, args=(reader, limit, key), daemon=True).start()


def invalidate_all_priorities() -> None:
    with _lock:
        _cache.clear()


def cache_status(limit: int = 3) -> dict:
    key = _cache_key(limit)
    with _lock:
        entry = _cache.get(key)
        if not entry or not entry.items:
            return {
                "cached": False,
                "fresh": False,
                "count": 0,
                "refresh_in_progress": bool(entry and entry.refresh_in_progress),
            }
        return {
            "cached": True,
            "fresh": _is_fresh(entry),
            "count": len(entry.items),
            "fetched_at": entry.fetched_at.isoformat(),
            "refresh_in_progress": entry.refresh_in_progress,
        }


def _refresh_top(reader: IMessageReader, limit: int, key: str) -> list[ResponsePriority]:
    try:
        items = get_top_priorities(reader, limit=limit)
    except SuggestionGenerationError:
        with _lock:
            entry = _cache.get(key)
            if entry:
                entry.refresh_in_progress = False
        raise

    with _lock:
        _cache[key] = _CacheEntry(
            items=items,
            fetched_at=datetime.now(tz=timezone.utc),
            refresh_in_progress=False,
        )
    return items
