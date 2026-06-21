"""FastAPI routes for the Ghostbusters iMessage connector."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from hydra.store import HydraMemoryStore
from imessage.reader import IMessageReader, ensure_runtime_db, working_reader
from imessage.writer import reset_runtime_db, send_reply
from services.hydra_generation import hydra_generation_configured
from services.priorities import (
    ResponsePriority,
    SuggestionGenerationError,
    find_chat_for_suggestions,
    get_priority_for_chat,
    get_top_priorities,
    nebius_configured,
)
from services.priority_cache import (
    cache_status,
    get_cached_top_priorities,
    invalidate_all_priorities,
    prefetch_top_priorities,
)
from services.ranker import rank_chats
from services.suggestion_cache import cache_status as suggestion_cache_status
from services.suggestion_cache import (
    get_chat_suggestions,
    invalidate_all as invalidate_all_suggestions,
    invalidate_chat as invalidate_chat_suggestions,
    prefetch_chat_suggestions,
)

router = APIRouter(prefix="/api")


class PriorityOut(BaseModel):
    rank: int
    contact_name: str
    contact_handle: str
    chat_id: str
    chat_guid: str
    last_message_preview: str
    last_message_at: datetime
    reply_waiting_at: Optional[datetime] = None
    suggested_response: str
    severity: str
    importance_score: float


class HealthOut(BaseModel):
    status: str
    imessage_available: bool
    imessage_db_path: str
    hydradb_configured: bool
    reply_generation_configured: bool
    nebius_configured: bool
    priorities_cache: dict[str, Any]
    suggestions_cache: dict[str, Any]


class SyncOut(BaseModel):
    success: bool
    detail: str
    result: Optional[dict[str, Any]] = None


class MessageOut(BaseModel):
    row_id: int
    chat_id: str
    chat_guid: str
    contact_handle: str
    contact_name: Optional[str]
    text: str
    is_from_me: bool
    timestamp: datetime
    is_read: bool


class ChatOut(BaseModel):
    chat_id: str
    chat_guid: str
    display_name: str
    contact_handle: str
    last_message: str
    last_message_at: datetime
    is_from_me: bool
    is_group: bool = False
    needs_reply: bool = False
    reply_waiting_at: Optional[datetime] = None
    unread_count: int = 0


class ChatSuggestionsOut(BaseModel):
    chat_id: str
    suggestions: list[str]
    needs_reply: bool = True
    reason: Optional[str] = None
    context_snippets: list[str] = []
    hydra_chunk_count: int = 0
    context_chat_id: Optional[str] = None
    context_scoped_to_chat: bool = True
    context_sub_tenant_id: Optional[str] = None
    generation_source: str = "hydradb"


class ChatContextOut(BaseModel):
    chat_id: str
    context_snippets: list[str] = []
    hydra_chunk_count: int = 0
    context_sub_tenant_id: Optional[str] = None


class SendMessageIn(BaseModel):
    text: str


class ResetOut(BaseModel):
    success: bool
    detail: str


def _to_priority_out(p: ResponsePriority) -> PriorityOut:
    return PriorityOut(
        rank=p.rank,
        contact_name=p.contact_name,
        contact_handle=p.contact_handle,
        chat_id=p.chat_id,
        chat_guid=p.chat_guid,
        last_message_preview=p.last_message_preview,
        last_message_at=p.last_message_at,
        reply_waiting_at=p.reply_waiting_at,
        suggested_response=p.suggested_response,
        severity=p.severity,
        importance_score=p.importance_score,
    )


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    reader = working_reader()
    store = HydraMemoryStore()
    return HealthOut(
        status="ok",
        imessage_available=reader.is_available(),
        imessage_db_path=str(reader.db_path),
        hydradb_configured=store.is_configured,
        reply_generation_configured=hydra_generation_configured(),
        nebius_configured=nebius_configured(),
        priorities_cache=cache_status(limit=3),
        suggestions_cache=suggestion_cache_status(),
    )


@router.get("/priorities", response_model=list[PriorityOut])
def priorities(
    limit: int = Query(default=3, ge=1, le=10),
    chat_id: Optional[str] = Query(default=None),
    chat_guid: Optional[str] = Query(default=None),
    refresh: bool = Query(default=False),
) -> list[PriorityOut]:
    reader = working_reader()
    try:
        if chat_id or chat_guid:
            if not reader.is_available():
                raise HTTPException(status_code=503, detail="iMessage database unavailable.")

            item = get_priority_for_chat(reader, chat_id=chat_id, chat_guid=chat_guid)
            return [_to_priority_out(item)] if item else []

        if not reader.is_available():
            raise HTTPException(status_code=503, detail="iMessage database unavailable.")

        items, _from_cache = get_cached_top_priorities(reader, limit=limit, refresh=refresh)
        return [_to_priority_out(p) for p in items]
    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Full Disk Access required. Grant it in System Settings > Privacy & Security > Full Disk Access.",
        )
    except SuggestionGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except (FileNotFoundError, sqlite3.OperationalError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/prefetch")
def prefetch_priorities(limit: int = Query(default=3, ge=1, le=10)) -> dict[str, Any]:
    """Warm priority cache for top N and Hydra suggestions for every waiting chat."""
    reader = working_reader()
    prefetch_top_priorities(reader, limit=limit)

    ranked = rank_chats(reader.list_recent_chats(limit=30), reader=reader)
    all_waiting = [item.chat for item in ranked]
    prefetch_chat_suggestions(reader, all_waiting, count=3)

    return {
        "status": "prefetch_started",
        "priorities_limit": limit,
        "suggestions_prefetch_count": len(all_waiting),
        "cache": cache_status(limit=limit),
        "suggestions_cache": suggestion_cache_status(),
    }


@router.post("/sync", response_model=SyncOut)
def sync_messages(limit: int = 50) -> SyncOut:
    reader = IMessageReader()
    store = HydraMemoryStore()

    if not store.is_configured:
        return SyncOut(
            success=False,
            detail="HydraDB not configured. Set HYDRA_DB_API_KEY in .env",
        )

    try:
        if not reader.is_available():
            raise FileNotFoundError(str(reader.db_path))
        store.ensure_tenant()
        result = store.ingest_recent_inbound(reader, limit=limit)
        return SyncOut(
            success=True,
            detail="Each chat synced to its own HydraDB context window",
            result=result,
        )
    except FileNotFoundError as exc:
        return SyncOut(success=False, detail=str(exc))
    except Exception as exc:
        return SyncOut(success=False, detail=f"Sync failed: {exc}")


@router.get("/hydra/logs")
def hydra_logs(limit: int = Query(default=20, ge=1, le=50)) -> dict[str, Any]:
    from hydra.activity_log import recent_hydra_logs

    logs = recent_hydra_logs(limit=limit)
    store = HydraMemoryStore()
    return {
        "configured": store.is_configured,
        "count": len(logs),
        "logs": logs,
    }


@router.get("/chats", response_model=list[ChatOut])
def list_chats(limit: int = 20) -> list[ChatOut]:
    reader = working_reader()
    try:
        chats = reader.list_recent_chats(limit=limit)
        return [
            ChatOut(
                chat_id=c.chat_id,
                chat_guid=c.chat_guid,
                display_name=c.display_name,
                contact_handle=c.contact_handle,
                last_message=c.last_message,
                last_message_at=c.last_message_at,
                is_from_me=c.is_from_me,
                is_group=c.is_group,
                needs_reply=c.needs_reply,
                reply_waiting_at=c.reply_waiting_at,
                unread_count=c.unread_count,
            )
            for c in chats
        ]
    except (FileNotFoundError, PermissionError, sqlite3.OperationalError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/chats/{chat_id}/context", response_model=ChatContextOut)
def chat_hydra_context(chat_id: str) -> ChatContextOut:
    from hydra.store import HydraMemoryStore
    from services.hydra_generation import fetch_hydra_context_snippets_for_chat

    reader = working_reader()
    try:
        chat = find_chat_for_suggestions(reader, chat_id=chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail=f"Chat {chat_id} not found")
        snippets, chunk_count = fetch_hydra_context_snippets_for_chat(chat)
        return ChatContextOut(
            chat_id=chat_id,
            context_snippets=snippets,
            hydra_chunk_count=chunk_count,
            context_sub_tenant_id=HydraMemoryStore.chat_sub_tenant_id(chat_id),
        )
    except SuggestionGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except (FileNotFoundError, PermissionError, sqlite3.OperationalError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/chats/{chat_id}/suggestions", response_model=ChatSuggestionsOut)
def chat_suggestions(
    chat_id: str,
    limit: int = Query(default=3, ge=1, le=5),
    refresh: bool = Query(default=False),
    follow_up: bool = Query(default=False),
) -> ChatSuggestionsOut:
    reader = working_reader()
    try:
        chat = find_chat_for_suggestions(reader, chat_id=chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail=f"Chat {chat_id} not found")
        if not chat.needs_reply or not chat.reply_to_message.strip():
            return ChatSuggestionsOut(
                chat_id=chat_id,
                suggestions=[],
                needs_reply=False,
                reason="caught_up",
            )
        payload = get_chat_suggestions(
            reader,
            chat,
            count=limit,
            refresh=refresh,
            follow_up=follow_up,
        )
        from hydra.store import HydraMemoryStore

        return ChatSuggestionsOut(
            chat_id=chat_id,
            suggestions=payload.suggestions,
            needs_reply=True,
            context_snippets=payload.context_snippets,
            hydra_chunk_count=payload.hydra_chunk_count,
            context_chat_id=chat_id,
            context_scoped_to_chat=not follow_up,
            context_sub_tenant_id=HydraMemoryStore.chat_sub_tenant_id(chat_id) if not follow_up else None,
            generation_source=payload.generation_source,
        )
    except SuggestionGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except (FileNotFoundError, PermissionError, sqlite3.OperationalError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/chats/{chat_id}/messages", response_model=list[MessageOut])
def chat_messages(chat_id: str, limit: int = 50) -> list[MessageOut]:
    reader = working_reader()
    try:
        messages = reader.get_messages_for_chat(chat_id, limit=limit)
        return [
            MessageOut(
                row_id=m.row_id,
                chat_id=m.chat_id,
                chat_guid=m.chat_guid,
                contact_handle=m.contact_handle,
                contact_name=m.contact_name,
                text=m.text,
                is_from_me=m.is_from_me,
                timestamp=m.timestamp,
                is_read=m.is_read,
            )
            for m in messages
        ]
    except (FileNotFoundError, PermissionError, sqlite3.OperationalError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/chats/{chat_id}/messages", response_model=MessageOut)
def send_chat_message(chat_id: str, body: SendMessageIn) -> MessageOut:
    try:
        message = send_reply(chat_id, body.text)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (FileNotFoundError, sqlite3.OperationalError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    invalidate_chat_suggestions(chat_id)
    invalidate_all_priorities()
    invalidate_all_suggestions()

    reader = working_reader()
    try:
        store = HydraMemoryStore()
        if store.is_configured:
            store.ingest_chat_thread(reader, chat_id, limit=60)
    except Exception:
        pass

    prefetch_top_priorities(reader, limit=3)

    return MessageOut(
        row_id=message.row_id,
        chat_id=message.chat_id,
        chat_guid=message.chat_guid,
        contact_handle=message.contact_handle,
        contact_name=message.contact_name,
        text=message.text,
        is_from_me=message.is_from_me,
        timestamp=message.timestamp,
        is_read=message.is_read,
    )


@router.post("/reset", response_model=ResetOut)
def reset_database() -> ResetOut:
    """Restore the runtime DB from the frozen initial unreplied snapshot."""
    try:
        reset_runtime_db()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    invalidate_all_priorities()
    invalidate_all_suggestions()
    reader = working_reader()
    prefetch_top_priorities(reader, limit=3)
    return ResetOut(success=True, detail="Runtime database restored from initial snapshot.")


def add_cors(app) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
