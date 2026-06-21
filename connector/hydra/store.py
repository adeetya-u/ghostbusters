"""HydraDB memory layer for iMessage context."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from imessage.reader import ChatSummary, IMessage, IMessageReader
from hydra.activity_log import record_hydra_log


class HydraMemoryStore:
    def __init__(
        self,
        api_key: Optional[str] = None,
        tenant_id: Optional[str] = None,
        sub_tenant_id: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("HYDRA_DB_API_KEY", "")
        self.tenant_id = tenant_id or os.environ.get("HYDRA_TENANT_ID", "ghostbusters")
        self.sub_tenant_id = sub_tenant_id or os.environ.get("HYDRA_SUB_TENANT_ID", "default")
        self._client: Any = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "your_api_key_here")

    @property
    def client(self) -> Any:
        if self._client is None:
            if not self.is_configured:
                raise RuntimeError(
                    "HydraDB API key not configured. Set HYDRA_DB_API_KEY in .env "
                    "(get one at https://app.hydradb.com)."
                )
            from hydra_db import HydraDB

            self._client = HydraDB(token=self.api_key)
        return self._client

    def ensure_tenant(self) -> None:
        try:
            self.client.tenants.create(tenant_id=self.tenant_id)
        except Exception:
            # Tenant may already exist
            pass

    @staticmethod
    def chat_sub_tenant_id(chat_id: str) -> str:
        """Isolated HydraDB context window for one iMessage thread."""
        safe = chat_id.strip().replace("/", "-")
        return f"chat-{safe}"

    def ingest_chat_messages(self, chat: ChatSummary, messages: list[IMessage]) -> dict[str, Any]:
        if not messages:
            return {"ingested": 0, "chat_id": chat.chat_id}

        sub_tenant_id = self.chat_sub_tenant_id(chat.chat_id)
        pairs: list[dict[str, str]] = []
        pending_user: str | None = None

        for msg in messages:
            text = (msg.text or "").strip()
            if not text:
                continue
            if msg.is_from_me:
                if pending_user:
                    pairs.append({"user": pending_user, "assistant": text})
                    pending_user = None
                else:
                    pairs.append({"user": "(conversation)", "assistant": text})
            else:
                pending_user = text

        if pending_user:
            pairs.append({"user": pending_user, "assistant": ""})

        memory_payload = [
            {
                "id": f"imessage_chat_{chat.chat_id}",
                "title": f"iMessage thread: {chat.display_name}",
                "user_assistant_pairs": pairs[-20:],
                "infer": False,
                "user_name": chat.display_name,
                "metadata": {
                    "source": "imessage",
                    "chat_id": chat.chat_id,
                    "chat_guid": chat.chat_guid,
                    "contact_handle": chat.contact_handle,
                },
            }
        ]

        record_hydra_log(
            "ingest_start",
            chat_id=chat.chat_id,
            contact=chat.display_name,
            messages=len(messages),
            sub_tenant_id=sub_tenant_id,
        )
        result = self.client.context.ingest(
            type="memory",
            tenant_id=self.tenant_id,
            sub_tenant_id=sub_tenant_id,
            memories=json.dumps(memory_payload),
        )
        record_hydra_log(
            "ingest_ok",
            chat_id=chat.chat_id,
            contact=chat.display_name,
            messages=len(messages),
            sub_tenant_id=sub_tenant_id,
        )
        return {
            "ingested": len(messages),
            "chat_id": chat.chat_id,
            "sub_tenant_id": sub_tenant_id,
            "result": result,
        }

    def ingest_recent_inbound(self, reader: IMessageReader, limit: int = 50) -> dict[str, Any]:
        """Ingest full recent threads (not inbound-only) for richer HydraDB context."""
        chats = reader.list_recent_chats(limit=min(limit, 100))
        if not chats:
            return {"ingested": 0, "message_count": 0}

        results = []
        message_count = 0
        for chat in chats:
            chat_messages = reader.get_messages_for_chat(chat.chat_id, limit=40)
            if not chat_messages:
                continue
            message_count += len(chat_messages)
            results.append(self.ingest_chat_messages(chat, chat_messages))

        return {
            "ingested_chats": len(results),
            "message_count": message_count,
            "results": results,
        }

    def ingest_chat_thread(self, reader: IMessageReader, chat_id: str, *, limit: int = 60) -> dict[str, Any]:
        """Ingest one chat's full thread after a new outbound message."""
        chats = {c.chat_id: c for c in reader.list_recent_chats(limit=100)}
        chat = chats.get(chat_id)
        if not chat:
            return {"ingested": 0, "chat_id": chat_id}
        messages = reader.get_messages_for_chat(chat_id, limit=limit)
        if not messages:
            return {"ingested": 0, "chat_id": chat_id}
        return self.ingest_chat_messages(chat, messages)

    def query_context(
        self,
        query: str,
        max_results: int = 8,
        *,
        chat_id: str | None = None,
        mode: str = "thinking",
        graph_context: bool = True,
    ) -> Any:
        if chat_id:
            sub_tenant_id = self.chat_sub_tenant_id(chat_id)
            metadata_filters = None
        else:
            sub_tenant_id = self.sub_tenant_id
            metadata_filters = None

        record_hydra_log(
            "store_query",
            query=query[:160],
            max_results=max_results,
            chat_id=chat_id,
            mode=mode,
            sub_tenant_id=sub_tenant_id,
        )
        return self.client.query(
            tenant_id=self.tenant_id,
            sub_tenant_id=sub_tenant_id,
            query=query,
            type="memory",
            query_by="hybrid",
            mode=mode,
            graph_context=graph_context,
            max_results=max_results,
            metadata_filters=metadata_filters,
        )

    def query_reply_context(
        self,
        query: str,
        *,
        chat_id: str | None = None,
        max_results: int = 8,
    ) -> Any:
        """Thinking-mode graph query tuned for reply generation."""
        self.ensure_tenant()
        return self.query_context(
            query,
            max_results=max_results,
            chat_id=chat_id,
            mode="thinking",
            graph_context=True,
        )
