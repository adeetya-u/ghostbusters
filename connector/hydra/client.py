"""HydraDB memory layer wrapper."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class HydraMemoryClient:
    def __init__(
        self,
        api_key: str | None = None,
        tenant_id: str | None = None,
        sub_tenant_id: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("HYDRA_DB_API_KEY", "")
        self.tenant_id = tenant_id or os.environ.get("HYDRA_TENANT_ID", "ghostbusters")
        self.sub_tenant_id = sub_tenant_id or os.environ.get("HYDRA_SUB_TENANT_ID", "default")
        self._client = None

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "your_api_key_here")

    def _get_client(self):
        if self._client is None:
            from hydra_db import HydraDB

            self._client = HydraDB(token=self.api_key)
        return self._client

    def ensure_tenant(self) -> None:
        client = self._get_client()
        try:
            client.tenants.create(tenant_id=self.tenant_id)
        except Exception as exc:
            # Tenant may already exist
            logger.debug("Tenant create skipped: %s", exc)

    def ingest_conversation(self, memory: dict[str, Any]) -> dict:
        client = self._get_client()
        return client.context.ingest(
            type="memory",
            tenant_id=self.tenant_id,
            sub_tenant_id=self.sub_tenant_id,
            memories=json.dumps([memory]),
        )

    def query_context(self, query: str, max_results: int = 8) -> dict:
        client = self._get_client()
        return client.query(
            tenant_id=self.tenant_id,
            sub_tenant_id=self.sub_tenant_id,
            query=query,
            type="memory",
            query_by="hybrid",
            max_results=max_results,
            graph_context=True,
        )
