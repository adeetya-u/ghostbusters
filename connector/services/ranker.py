"""
Semi-deterministic ML-style priority ranker for unanswered conversations.

Prioritizes threads you likely forgot to reply to, not people you text constantly.
High message volume and recent back-and-forth reduce the score; long unanswered
waits on quiet threads increase it.

Nebius LLM is used separately for reply text generation, not for ranking order.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from imessage.reader import ChatSummary, IMessage, IMessageReader

# Weights favor "forgotten" over "frequent contact still in an active thread".
WEIGHTS = {
    "time_waiting": 0.28,
    "forgotten_linger": 0.22,
    "relationship_boost": 0.20,
    "urgency_text": 0.16,
    "question": 0.08,
    "unread": 0.06,
    "direct_address": 0.05,
    "message_length": 0.03,
    "active_conversation_penalty": -0.22,
    "thread_volume_penalty": -0.16,
    "group_adjustment": -0.04,
}

URGENCY_PATTERN = re.compile(
    r"\b("
    r"urgent|asap|please|help|important|deadline|today|tonight|tomorrow|"
    r"waiting|call me|let me know|need|confirm|still on|can you|could you|"
    r"review|cover|shift|rsvp|sorry to bother|following up"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RankedChat:
    chat: ChatSummary
    score: float
    severity: str
    features: dict[str, float]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _hours_since(ts: datetime) -> float:
    now = datetime.now(tz=timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (now - ts).total_seconds() / 3600.0)


def _time_waiting_feature(hours: float) -> float:
    if hours >= 168:
        return 1.0
    if hours >= 72:
        return 0.90
    if hours >= 24:
        return 0.75
    if hours >= 6:
        return 0.55
    if hours >= 2:
        return 0.35
    return 0.15


def _urgency_text_feature(text: str) -> float:
    hits = len(URGENCY_PATTERN.findall(text))
    return min(1.0, hits * 0.35)


def _inbound_waiting_hours(chat: ChatSummary, messages: list[IMessage] | None) -> float:
    if messages:
        last_outbound_at: datetime | None = None
        for message in reversed(messages):
            if message.is_from_me:
                last_outbound_at = message.timestamp
                break
        for message in reversed(messages):
            if message.is_from_me:
                continue
            if last_outbound_at is None or message.timestamp > last_outbound_at:
                return _hours_since(message.timestamp)
    return _hours_since(chat.last_message_at)


def _active_conversation_penalty(messages: list[IMessage] | None) -> float:
    """Penalize hot threads with lots of recent back-and-forth."""
    if not messages:
        return 0.0

    recent = [m for m in messages if _hours_since(m.timestamp) <= 48]
    if len(recent) >= 10:
        return 1.0
    if len(recent) >= 6:
        return 0.75
    if len(recent) >= 3:
        return 0.45
    if len(recent) >= 2:
        return 0.20
    return 0.0


def _thread_volume_penalty(messages: list[IMessage] | None) -> float:
    """Penalize long-running threads you text all the time."""
    if not messages:
        return 0.0

    count = len(messages)
    if count >= 40:
        return 1.0
    if count >= 20:
        return 0.70
    if count >= 12:
        return 0.45
    if count >= 6:
        return 0.20
    return 0.0


def _forgotten_linger_feature(hours_waiting: float, active_penalty: float, volume_penalty: float) -> float:
    """
    High when a reply has been sitting unanswered on a quiet thread.
    Drops when the thread is active or historically very chatty.
    """
    base = _time_waiting_feature(hours_waiting)
    dampening = 1.0 - (0.75 * active_penalty) - (0.45 * volume_penalty)
    return max(0.0, min(1.0, base * max(0.0, dampening)))


def _median_reply_hours(messages: list[IMessage] | None) -> float | None:
    """Typical hours between their message and your reply in this thread."""
    if not messages:
        return None

    deltas: list[float] = []
    pending: datetime | None = None
    for message in messages:
        if not message.is_from_me:
            pending = message.timestamp
        elif pending is not None:
            hours = (message.timestamp - pending).total_seconds() / 3600.0
            if hours >= 0:
                deltas.append(hours)
            pending = None

    if not deltas:
        return None
    deltas.sort()
    return deltas[len(deltas) // 2]


def _new_relationship_boost(message_count: int) -> float:
    if message_count <= 2:
        return 1.0
    if message_count <= 5:
        return 0.75
    if message_count <= 10:
        return 0.40
    return 0.0


def _relationship_boost(
    hours_waiting: float,
    messages: list[IMessage] | None,
    active_penalty: float,
) -> float:
    """
    Boost people you usually reply to quickly but haven't this time,
    plus brand-new relationships with few messages.
    """
    message_count = len(messages) if messages else 0
    dampening = max(0.0, 1.0 - (0.55 * active_penalty))

    if message_count <= 10:
        base = _new_relationship_boost(message_count)
        if hours_waiting >= 1:
            return min(1.0, base * dampening)
        return base * 0.5 * dampening

    median = _median_reply_hours(messages)
    if median is None:
        return 0.0

    typical = min(median, 8.0)
    if hours_waiting <= typical:
        return 0.0

    ratio = hours_waiting / max(typical, 0.25)
    if ratio < 1.5:
        return 0.0

    boost = min(1.0, 0.45 + (ratio - 1.5) * 0.35)
    return boost * dampening


def extract_features(chat: ChatSummary, messages: list[IMessage] | None = None) -> dict[str, float]:
    target = chat.reply_to_message if chat.needs_reply else chat.last_message
    target = target.strip()
    hours_waiting = _inbound_waiting_hours(chat, messages)
    active_penalty = _active_conversation_penalty(messages)
    volume_penalty = _thread_volume_penalty(messages)

    return {
        "time_waiting": _time_waiting_feature(hours_waiting),
        "forgotten_linger": _forgotten_linger_feature(hours_waiting, active_penalty, volume_penalty),
        "relationship_boost": _relationship_boost(hours_waiting, messages, active_penalty),
        "urgency_text": _urgency_text_feature(target),
        "question": 1.0 if "?" in target else 0.0,
        "unread": 1.0 if chat.unread_count > 0 else 0.0,
        "message_length": min(1.0, len(target) / 120.0),
        "direct_address": 1.0 if re.search(r"\b(you|u)\b", target, re.I) else 0.0,
        "active_conversation_penalty": active_penalty,
        "thread_volume_penalty": volume_penalty,
        "group_adjustment": 1.0 if chat.is_group else 0.0,
    }


def score_chat(chat: ChatSummary, messages: list[IMessage] | None = None) -> RankedChat:
    features = extract_features(chat, messages)
    linear = sum(WEIGHTS[key] * features[key] for key in WEIGHTS)
    raw = _sigmoid((linear - 0.30) * 6.0)

    if raw >= 0.82:
        severity = "high"
    elif raw >= 0.58:
        severity = "medium"
    else:
        severity = "low"

    return RankedChat(chat=chat, score=round(raw, 4), severity=severity, features=features)


def rank_chats(
    chats: list[ChatSummary],
    *,
    reader: IMessageReader | None = None,
    message_lookup: dict[str, list[IMessage]] | None = None,
) -> list[RankedChat]:
    ranked: list[RankedChat] = []
    for chat in chats:
        if not chat.needs_reply or not chat.reply_to_message.strip():
            continue
        msgs: list[IMessage] | None = None
        if message_lookup:
            msgs = message_lookup.get(chat.chat_id)
        if msgs is None and reader is not None:
            msgs = reader.get_messages_for_chat(chat.chat_id, limit=40)
        ranked.append(score_chat(chat, msgs))

    ranked.sort(
        key=lambda item: (
            -item.score,
            -item.features.get("relationship_boost", 0.0),
            -item.features.get("forgotten_linger", 0.0),
            -item.features.get("time_waiting", 0.0),
        )
    )
    return ranked
