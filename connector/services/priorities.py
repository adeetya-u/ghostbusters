"""
Priority ranking and reply suggestions.

Top-3 Ghostbusters priorities always use HydraDB (per-chat window) + Nebius.
In-thread follow-up suggestions use Nebius with the last 4 messages only.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from imessage.reader import ChatSummary, IMessageReader
from services.hydra_generation import (
    HydraGenerationError,
    ReplySuggestionResult,
    generate_chat_reply_suggestions_with_context,
    generate_followup_suggestions_with_context,
    hydra_generation_configured,
)
from services.ranker import rank_chats


class SuggestionGenerationError(Exception):
    """Raised when reply generation fails."""


def generate_chat_reply_suggestions_for_chat(chat: ChatSummary, count: int = 3) -> list[str]:
    """Public wrapper mapping HydraDB generation errors to API errors."""
    return generate_chat_reply_suggestions_with_context_for_chat(chat, count=count).suggestions


def generate_chat_reply_suggestions_with_context_for_chat(
    chat: ChatSummary,
    count: int = 3,
) -> ReplySuggestionResult:
    """Initial/priority suggestions: full HydraDB context window + Nebius."""
    try:
        return generate_chat_reply_suggestions_with_context(chat, count=count)
    except HydraGenerationError as exc:
        raise SuggestionGenerationError(str(exc)) from exc


def generate_followup_suggestions_for_chat(
    reader: IMessageReader,
    chat: ChatSummary,
    count: int = 3,
) -> ReplySuggestionResult:
    """Follow-up suggestions: Nebius only with the last 4 thread messages."""
    try:
        messages = reader.get_messages_for_chat(chat.chat_id, limit=50)
        return generate_followup_suggestions_with_context(chat, messages, count=count)
    except HydraGenerationError as exc:
        raise SuggestionGenerationError(str(exc)) from exc


def find_chat_for_suggestions(
    reader: IMessageReader,
    *,
    chat_id: str | None = None,
    chat_guid: str | None = None,
) -> ChatSummary | None:
    chats = reader.list_recent_chats(limit=50)
    if chat_id:
        match = next((c for c in chats if c.chat_id == chat_id), None)
        if match:
            return match
    if chat_guid:
        return next((c for c in chats if c.chat_guid == chat_guid), None)
    return None


def nebius_configured() -> bool:
    """True when HydraDB + LLM synthesis pipeline is configured."""
    return hydra_generation_configured()


def verify_nebius() -> str:
    """Smoke-test HydraDB-backed reply generation."""
    sample = ChatSummary(
        chat_id="verify",
        chat_guid="verify",
        display_name="Alex",
        contact_handle="alex",
        last_message="Hey, are we still on for dinner tomorrow?",
        last_message_at=datetime.now(),
        is_from_me=False,
        needs_reply=True,
        reply_to_message="Hey, are we still on for dinner tomorrow?",
    )
    return generate_chat_reply_suggestions_for_chat(sample, count=1)[0]


@dataclass
class ResponsePriority:
    rank: int
    contact_name: str
    contact_handle: str
    chat_id: str
    chat_guid: str
    last_message_preview: str
    last_message_at: datetime
    suggested_response: str
    severity: str
    importance_score: float
    reply_waiting_at: datetime | None = None


def _chat_to_priority(
    reader: IMessageReader,
    chat: ChatSummary,
    rank: int,
    *,
    importance_score: float | None = None,
    severity: str | None = None,
) -> ResponsePriority:
    from services.suggestion_cache import get_chat_suggestions

    if importance_score is None or severity is None:
        scored = rank_chats([chat], reader=reader)[0]
        importance_score = scored.score
        severity = scored.severity

    preview = chat.reply_to_message[:120] if chat.needs_reply else chat.last_message[:120]
    if chat.is_group and chat.reply_to_sender:
        preview = f"{chat.reply_to_sender}: {preview}"
    suggestions = get_chat_suggestions(reader, chat, count=3)
    return ResponsePriority(
        rank=rank,
        contact_name=chat.display_name,
        contact_handle=chat.contact_handle,
        chat_id=chat.chat_id,
        chat_guid=chat.chat_guid,
        last_message_preview=preview,
        last_message_at=chat.last_message_at,
        reply_waiting_at=chat.reply_waiting_at,
        suggested_response=suggestions.suggestions[0] if suggestions.suggestions else "Generating reply…",
        severity=severity,
        importance_score=importance_score,
    )


def build_fast_priorities(reader: IMessageReader, limit: int = 3) -> list[ResponsePriority]:
    """Return ranked priorities immediately using any cached suggestions."""
    from services.suggestion_cache import peek_chat_suggestion

    chats = reader.list_recent_chats(limit=30)
    ranked = rank_chats(chats, reader=reader)[:limit]
    items: list[ResponsePriority] = []
    for rank, item in enumerate(ranked, start=1):
        chat = item.chat
        preview = chat.reply_to_message[:120] if chat.needs_reply else chat.last_message[:120]
        if chat.is_group and chat.reply_to_sender:
            preview = f"{chat.reply_to_sender}: {preview}"
        suggestion = peek_chat_suggestion(chat) or "Generating reply…"
        items.append(
            ResponsePriority(
                rank=rank,
                contact_name=chat.display_name,
                contact_handle=chat.contact_handle,
                chat_id=chat.chat_id,
                chat_guid=chat.chat_guid,
                last_message_preview=preview,
                last_message_at=chat.last_message_at,
                reply_waiting_at=chat.reply_waiting_at,
                suggested_response=suggestion,
                severity=item.severity,
                importance_score=item.score,
            )
        )
    return items


def get_top_priorities(reader: IMessageReader, limit: int = 3) -> list[ResponsePriority]:
    chats = reader.list_recent_chats(limit=30)
    ranked = rank_chats(chats, reader=reader)[:limit]

    def build(args: tuple[int, object]) -> ResponsePriority:
        rank, item = args
        return _chat_to_priority(
            reader,
            item.chat,
            rank,
            importance_score=item.score,
            severity=item.severity,
        )

    if len(ranked) <= 1:
        return [build((i, item)) for i, item in enumerate(ranked, start=1)]

    with ThreadPoolExecutor(max_workers=min(limit, len(ranked))) as pool:
        return list(pool.map(build, enumerate(ranked, start=1)))


def get_priority_for_chat(
    reader: IMessageReader,
    *,
    chat_id: str | None = None,
    chat_guid: str | None = None,
) -> ResponsePriority | None:
    chats = reader.list_recent_chats(limit=50)
    match: ChatSummary | None = None

    if chat_id:
        match = next((c for c in chats if c.chat_id == chat_id), None)
    if not match and chat_guid:
        match = next((c for c in chats if c.chat_guid == chat_guid), None)

    if not match or not match.needs_reply or not match.reply_to_message.strip():
        return None

    ranked = rank_chats([match], reader=reader)
    item = ranked[0]
    return _chat_to_priority(
        reader,
        item.chat,
        rank=1,
        importance_score=item.score,
        severity=item.severity,
    )
