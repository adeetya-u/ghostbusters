"""
Priority ranking stub — placeholder until the backend algorithm is ready.

The real algorithm (owned by backend team) will:
  - Score conversations by severity, importance, and urgency
  - Generate personalized response suggestions
  - Factor in HydraDB memory context and user preferences

For now we surface the top 3 chats that need a reply (inbound, recent, unread-ish).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from imessage.reader import ChatSummary, IMessageReader


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
    # Backend algorithm will populate these properly:
    severity: str  # low | medium | high | critical
    importance_score: float  # 0.0 – 1.0


import json
import os
import ssl
import urllib.request


NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")

def _generate_blurb_nebius(chat: ChatSummary) -> str:
    """Generates a blurb using Nebius LLM."""
    chat_text = chat.last_message
    if not chat_text.strip():
        return "No message."
    if not NEBIUS_API_KEY:
        return f"Follow up on: \"{chat_text[:80]}\""
    url = "https://api.studio.nebius.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {NEBIUS_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "meta-llama/Llama-3.3-70B-Instruct",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant that generates a very brief (1-line) suggested response for an iMessage. Return ONLY the suggested response text, with no quotes or extra formatting."
            },
            {
                "role": "user",
                "content": f"Here is the last message I received: {chat_text}"
            }
        ],
        "max_tokens": 50,
        "temperature": 0.5
    }
    
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, context=ctx) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f"Follow up on: \"{chat_text[:80]}\""


def _severity_stub(chat: ChatSummary, rank: int) -> tuple[str, float]:
    """Placeholder scoring — backend team replaces this."""
    base = max(0.3, 1.0 - (rank - 1) * 0.15)
    if not chat.is_from_me and chat.unread_count > 0:
        base += 0.1
    if "?" in chat.last_message:
        base += 0.05
    severity = "high" if base >= 0.85 else "medium" if base >= 0.6 else "low"
    return severity, round(min(base, 1.0), 2)


def _rank_candidates(chats: list[ChatSummary]) -> list[ChatSummary]:
    """Prefer inbound messages that likely need a reply."""
    candidates = [c for c in chats if not c.is_from_me and c.last_message.strip()]
    candidates.sort(key=lambda c: c.last_message_at, reverse=True)
    return candidates


def _chat_to_priority(chat: ChatSummary, rank: int) -> ResponsePriority:
    severity, score = _severity_stub(chat, rank)
    return ResponsePriority(
        rank=rank,
        contact_name=chat.display_name,
        contact_handle=chat.contact_handle,
        chat_id=chat.chat_id,
        chat_guid=chat.chat_guid,
        last_message_preview=chat.last_message[:120],
        last_message_at=chat.last_message_at,
        suggested_response=_generate_blurb_nebius(chat),
        severity=severity,
        importance_score=score,
    )


def get_top_priorities(reader: IMessageReader, limit: int = 3) -> list[ResponsePriority]:
    chats = reader.list_recent_chats(limit=30)
    top = _rank_candidates(chats)[:limit]
    return [_chat_to_priority(chat, i) for i, chat in enumerate(top, start=1)]


def get_priority_for_chat(
    reader: IMessageReader,
    *,
    chat_id: str | None = None,
    chat_guid: str | None = None,
) -> ResponsePriority | None:
    """Return a recommendation scoped to a single conversation."""
    chats = reader.list_recent_chats(limit=50)
    match: ChatSummary | None = None

    if chat_id:
        match = next((c for c in chats if c.chat_id == chat_id), None)
    if not match and chat_guid:
        match = next((c for c in chats if c.chat_guid == chat_guid), None)

    if not match:
        return None

    if match.is_from_me or not match.last_message.strip():
        return None

    return _chat_to_priority(match, rank=1)


def demo_priorities() -> list[ResponsePriority]:
    """Fallback when chat.db is unavailable (e.g. no Full Disk Access)."""
    now = datetime.now(tz=timezone.utc)
    return [
        ResponsePriority(
            rank=1,
            contact_name="Alex Chen",
            contact_handle="+15551234567",
            chat_id="3",
            chat_guid="iMessage;-;+15551234567",
            last_message_preview="Hey, are we still on for dinner tomorrow?",
            last_message_at=now,
            suggested_response="Yes, 7pm at the Thai place on 5th works for me!",
            severity="high",
            importance_score=0.92,
        ),
        ResponsePriority(
            rank=2,
            contact_name="Mom",
            contact_handle="+15559876543",
            chat_id="4",
            chat_guid="iMessage;-;+15559876543",
            last_message_preview="Call me when you get a chance",
            last_message_at=now - timedelta(minutes=30),
            suggested_response="I'll call you tonight around 8 — is that okay?",
            severity="medium",
            importance_score=0.78,
        ),
        ResponsePriority(
            rank=3,
            contact_name="Work Group",
            contact_handle="chat-work-deck",
            chat_id="11",
            chat_guid="iMessage;+;chat-work-deck",
            last_message_preview="Can someone review the deck before 3pm?",
            last_message_at=now - timedelta(hours=3),
            suggested_response="I can review it at 2pm and send feedback before 3.",
            severity="medium",
            importance_score=0.71,
        ),
        ResponsePriority(
            rank=4,
            contact_name="Sam Rivera",
            contact_handle="+15552345678",
            chat_id="5",
            chat_guid="iMessage;-;+15552345678",
            last_message_preview="Can you cover my shift Friday? I have a concert",
            last_message_at=now - timedelta(minutes=90),
            suggested_response="Let me check my schedule and get back to you tonight.",
            severity="medium",
            importance_score=0.68,
        ),
        ResponsePriority(
            rank=5,
            contact_name="Morgan (Recruiter)",
            contact_handle="+15554443322",
            chat_id="7",
            chat_guid="iMessage;-;+15554443322",
            last_message_preview="Absolutely — 30 min call this week?",
            last_message_at=now - timedelta(hours=1),
            suggested_response="Thursday afternoon works — send me a calendar invite.",
            severity="low",
            importance_score=0.55,
        ),
    ]
