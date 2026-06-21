"""FastAPI routes for the Ghostbusters iMessage connector."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from hydra.store import HydraMemoryStore
from imessage.reader import IMessageReader, working_reader
from services.priorities import (
    ResponsePriority,
    demo_priorities,
    get_priority_for_chat,
    get_top_priorities,
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
    suggested_response: str
    severity: str
    importance_score: float


class HealthOut(BaseModel):
    status: str
    imessage_available: bool
    imessage_db_path: str
    hydradb_configured: bool


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


def _to_priority_out(p: ResponsePriority) -> PriorityOut:
    return PriorityOut(
        rank=p.rank,
        contact_name=p.contact_name,
        contact_handle=p.contact_handle,
        chat_id=p.chat_id,
        chat_guid=p.chat_guid,
        last_message_preview=p.last_message_preview,
        last_message_at=p.last_message_at,
        suggested_response=p.suggested_response,
        severity=p.severity,
        importance_score=p.importance_score,
    )


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    reader = IMessageReader()
    store = HydraMemoryStore()
    return HealthOut(
        status="ok",
        imessage_available=reader.is_available(),
        imessage_db_path=str(reader.db_path),
        hydradb_configured=store.is_configured,
    )


@router.get("/priorities", response_model=list[PriorityOut])
def priorities(
    limit: int = Query(default=3, ge=1, le=10),
    chat_id: Optional[str] = Query(default=None),
    chat_guid: Optional[str] = Query(default=None),
) -> list[PriorityOut]:
    reader = working_reader()
    try:
        if chat_id or chat_guid:
            if not reader.is_available():
                demo = demo_priorities()
                match = None
                if chat_id:
                    match = next((p for p in demo if p.chat_id == chat_id), None)
                if not match and chat_guid:
                    match = next((p for p in demo if p.chat_guid == chat_guid), None)
                return [_to_priority_out(match)] if match else []

            item = get_priority_for_chat(reader, chat_id=chat_id, chat_guid=chat_guid)
            return [_to_priority_out(item)] if item else []

        if not reader.is_available():
            return [_to_priority_out(p) for p in demo_priorities()[:limit]]
        items = get_top_priorities(reader, limit=limit)
        if not items:
            return [_to_priority_out(p) for p in demo_priorities()[:limit]]
        return [_to_priority_out(p) for p in items]
    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Full Disk Access required. Grant it in System Settings → Privacy & Security → Full Disk Access.",
        )
    except (FileNotFoundError, sqlite3.OperationalError):
        return [_to_priority_out(p) for p in demo_priorities()[:limit]]


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
        return SyncOut(success=True, detail="Messages synced to HydraDB", result=result)
    except FileNotFoundError as exc:
        return SyncOut(success=False, detail=str(exc))
    except Exception as exc:
        return SyncOut(success=False, detail=f"Sync failed: {exc}")


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
            )
            for c in chats
        ]
    except (FileNotFoundError, PermissionError, sqlite3.OperationalError):
        demo = demo_priorities()
        return [
            ChatOut(
                chat_id=p.chat_id,
                chat_guid=p.chat_guid,
                display_name=p.contact_name,
                contact_handle=p.contact_handle,
                last_message=p.last_message_preview,
                last_message_at=p.last_message_at,
                is_from_me=False,
            )
            for p in demo[:limit]
        ]


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


def add_cors(app) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
