"""Sync iMessage conversations into HydraDB memory."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from imessage.reader import ChatSummary, IMessageReader, Message
from hydra.client import HydraMemoryClient

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    chats_processed: int
    memories_ingested: int
    skipped: int
    errors: list[str]


class MessageSyncService:
    def __init__(
        self,
        reader: IMessageReader | None = None,
        hydra: HydraMemoryClient | None = None,
    ):
        self.reader = reader or IMessageReader()
        self.hydra = hydra or HydraMemoryClient()

    def sync_recent(self, chat_limit: int = 20, messages_per_chat: int = 15) -> SyncResult:
        if not self.reader.is_available():
            return SyncResult(0, 0, 0, [f"chat.db not found at {self.reader.db_path}"])

        if not self.hydra.is_configured():
            return SyncResult(0, 0, 0, ["HydraDB API key not configured. Set HYDRA_DB_API_KEY in .env"])

        chats = self.reader.list_recent_chats(limit=chat_limit)
        ingested = 0
        skipped = 0
        errors: list[str] = []

        for chat in chats:
            try:
                messages = self.reader.fetch_messages(chat.chat_id, limit=messages_per_chat)
                if not messages:
                    skipped += 1
                    continue

                payload = self._build_memory_payload(chat, messages)
                self.hydra.ingest_conversation(payload)
                ingested += 1
            except Exception as exc:
                logger.exception("Failed to sync chat %s", chat.chat_id)
                errors.append(f"chat {chat.chat_id}: {exc}")

        return SyncResult(
            chats_processed=len(chats),
            memories_ingested=ingested,
            skipped=skipped,
            errors=errors,
        )

    def _build_memory_payload(self, chat: ChatSummary, messages: list[Message]) -> dict:
        pairs = []
        pending_user: str | None = None

        for msg in messages:
            if not msg.text:
                continue
            if msg.is_from_me:
                if pending_user:
                    pairs.append({"user": pending_user, "assistant": msg.text})
                    pending_user = None
                else:
                    pairs.append({"user": "(conversation)", "assistant": msg.text})
            else:
                pending_user = msg.text

        if pending_user and not pairs:
            pairs.append({"user": pending_user, "assistant": ""})

        return {
            "id": f"imessage_chat_{chat.chat_id}",
            "title": f"iMessage with {chat.display_name}",
            "user_assistant_pairs": pairs[-10:],
            "infer": False,
            "metadata": {
                "source": "imessage",
                "chat_id": chat.chat_id,
                "chat_guid": chat.chat_guid,
                "contact": chat.display_name,
            },
        }
