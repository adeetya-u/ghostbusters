"""Ghostbusters iMessage connector - local API bridging iMessages and HydraDB."""

from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from api.routes import add_cors, router

# Load .env from repo root and connector directory
_connector = Path(__file__).resolve().parent
_repo = _connector.parent
load_dotenv(_repo / ".env")
load_dotenv(_connector / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from imessage.reader import ensure_runtime_db, working_reader
    from services.priority_cache import prefetch_top_priorities
    from services.ranker import rank_chats
    from services.suggestion_cache import prefetch_chat_suggestions

    ensure_runtime_db()
    reader = working_reader()
    prefetch_top_priorities(reader, limit=3)
    ranked = rank_chats(reader.list_recent_chats(limit=30), reader=reader)
    prefetch_chat_suggestions(reader, [item.chat for item in ranked], count=3)
    yield


app = FastAPI(
    title="Ghostbusters Connector",
    description="Reads iMessages, stores context in HydraDB, serves priority queue to the UI.",
    version="0.1.0",
    lifespan=lifespan,
)
add_cors(app)
app.include_router(router)


@app.get("/")
def root():
    return {
        "service": "ghostbusters-connector",
        "docs": "/docs",
        "endpoints": ["/api/health", "/api/priorities", "/api/prefetch", "/api/sync", "/api/chats"],
    }


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("CONNECTOR_HOST", "127.0.0.1")
    port = int(os.environ.get("CONNECTOR_PORT", "8787"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
