"""In-memory cache for Nebius-generated per-chat reply suggestions."""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from imessage.reader import ChatSummary, IMessageReader

from services.priorities import SuggestionGenerationError

CACHE_TTL_SECONDS = int(__import__("os").environ.get("SUGGESTION_CACHE_TTL", "300"))


@dataclass
class _CacheEntry:
    suggestions: list[str]
    fingerprint: str
    fetched_at: datetime
    refresh_in_progress: bool = False


_lock = threading.Lock()
_cache: dict[str, _CacheEntry] = {}


def _fingerprint(chat: ChatSummary) -> str:
    payload = "|".join(
        [
            chat.chat_id,
            chat.reply_to_message.strip(),
            chat.reply_to_sender or "",
            str(chat.is_group),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_fresh(entry: _CacheEntry) -> bool:
    age = (datetime.now(tz=timezone.utc) - entry.fetched_at).total_seconds()
    return age < CACHE_TTL_SECONDS


def get_chat_suggestions(
    reader: IMessageReader,
    chat: ChatSummary,
    *,
    count: int = 3,
    refresh: bool = False,
) -> list[str]:
    """Return cached Nebius suggestions for a chat, generating on miss."""
    if not chat.needs_reply or not chat.reply_to_message.strip():
        raise SuggestionGenerationError("No inbound message to reply to.")

    key = chat.chat_id
    fingerprint = _fingerprint(chat)

    with _lock:
        entry = _cache.get(key)
        if entry and not refresh and entry.fingerprint == fingerprint and entry.suggestions:
            if _is_fresh(entry):
                return entry.suggestions[:count]
            if not entry.refresh_in_progress:
                entry.refresh_in_progress = True
                threading.Thread(
                    target=_refresh_chat,
                    args=(reader, chat, count, key, fingerprint),
                    daemon=True,
                ).start()
            return entry.suggestions[:count]

    return _refresh_chat(reader, chat, count, key, fingerprint)[:count]


def prefetch_chat_suggestions(
    reader: IMessageReader,
    chats: list[ChatSummary],
    *,
    count: int = 3,
) -> None:
    """Warm suggestion cache for the given chats in background threads."""
    for chat in chats:
        if not chat.needs_reply or not chat.reply_to_message.strip():
            continue

        key = chat.chat_id
        fingerprint = _fingerprint(chat)
        with _lock:
            entry = _cache.get(key)
            if entry and entry.fingerprint == fingerprint and entry.suggestions and _is_fresh(entry):
                continue
            if entry and entry.refresh_in_progress:
                continue
            if entry:
                entry.refresh_in_progress = True
            else:
                _cache[key] = _CacheEntry(
                    suggestions=[],
                    fingerprint=fingerprint,
                    fetched_at=datetime.min.replace(tzinfo=timezone.utc),
                    refresh_in_progress=True,
                )

        threading.Thread(
            target=_refresh_chat,
            args=(reader, chat, count, key, fingerprint),
            daemon=True,
        ).start()


def invalidate_chat(chat_id: str) -> None:
    with _lock:
        _cache.pop(chat_id, None)


def invalidate_all() -> None:
    with _lock:
        _cache.clear()


def peek_chat_suggestion(chat: ChatSummary) -> str | None:
    """Return a cached suggestion without triggering generation."""
    with _lock:
        entry = _cache.get(chat.chat_id)
        if entry and entry.suggestions:
            return entry.suggestions[0]
    return None


def cache_status() -> dict:
    with _lock:
        fresh = sum(1 for entry in _cache.values() if entry.suggestions and _is_fresh(entry))
        in_progress = sum(1 for entry in _cache.values() if entry.refresh_in_progress)
        return {
            "cached_chats": len(_cache),
            "fresh_entries": fresh,
            "refresh_in_progress": in_progress,
        }


def _refresh_chat(
    reader: IMessageReader,
    chat: ChatSummary,
    count: int,
    key: str,
    fingerprint: str,
) -> list[str]:
    del reader
    from services.priorities import generate_chat_reply_suggestions_for_chat

    try:
        suggestions = generate_chat_reply_suggestions_for_chat(chat, count=count)
    except SuggestionGenerationError:
        with _lock:
            entry = _cache.get(key)
            if entry:
                entry.refresh_in_progress = False
        raise

    with _lock:
        _cache[key] = _CacheEntry(
            suggestions=suggestions,
            fingerprint=fingerprint,
            fetched_at=datetime.now(tz=timezone.utc),
            refresh_in_progress=False,
        )
    return suggestions
