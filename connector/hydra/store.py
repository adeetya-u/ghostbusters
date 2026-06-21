"""HydraDB memory layer for iMessage context."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from imessage.reader import ChatSummary, IMessage, IMessageReader


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

    def ingest_chat_messages(self, chat: ChatSummary, messages: list[IMessage]) -> dict[str, Any]:
        if not messages:
            return {"ingested": 0, "chat_id": chat.chat_id}

        pairs = []
        for msg in messages:
            if msg.is_from_me:
                pairs.append({"user": "[me]", "assistant": msg.text})
            else:
                pairs.append({"user": msg.text, "assistant": ""})

        memory_payload = [
            {
                "title": f"iMessage thread: {chat.display_name}",
                "user_assistant_pairs": pairs[-20:],  # last 20 turns
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

        result = self.client.context.ingest(
            type="memory",
            tenant_id=self.tenant_id,
            sub_tenant_id=self.sub_tenant_id,
            memories=json.dumps(memory_payload),
        )
        return {"ingested": len(messages), "chat_id": chat.chat_id, "result": result}

    def ingest_recent_inbound(self, reader: IMessageReader, limit: int = 50) -> dict[str, Any]:
        messages = reader.get_recent_inbound_messages(limit=limit)
        if not messages:
            return {"ingested": 0, "message_count": 0}

        by_chat: dict[str, list[IMessage]] = {}
        for msg in messages:
            by_chat.setdefault(msg.chat_id, []).append(msg)

        chats = {c.chat_id: c for c in reader.list_recent_chats(limit=100)}
        results = []
        for chat_id, chat_messages in by_chat.items():
            chat = chats.get(
                chat_id,
                ChatSummary(
                    chat_id=chat_id,
                    chat_guid=chat_messages[0].chat_guid,
                    display_name=chat_messages[0].contact_name or chat_messages[0].contact_handle,
                    contact_handle=chat_messages[0].contact_handle,
                    last_message=chat_messages[-1].text,
                    last_message_at=chat_messages[-1].timestamp,
                    is_from_me=False,
                    unread_count=1,
                ),
            )
            results.append(self.ingest_chat_messages(chat, chat_messages))

        return {"ingested_chats": len(results), "results": results}

    def query_context(self, query: str, max_results: int = 8) -> Any:
        return self.client.query(
            tenant_id=self.tenant_id,
            sub_tenant_id=self.sub_tenant_id,
            query=query,
            type="memory",
            query_by="hybrid",
            max_results=max_results,
        )
