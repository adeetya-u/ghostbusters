"""Ghostbusters iMessage connector — local API bridging iMessages and HydraDB."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from api.routes import add_cors, router

# Load .env from repo root
_root = Path(__file__).resolve().parent.parent
load_dotenv(_root.parent / ".env")
load_dotenv(_root / ".env")

app = FastAPI(
    title="Ghostbusters Connector",
    description="Reads iMessages, stores context in HydraDB, serves priority queue to the UI.",
    version="0.1.0",
)
add_cors(app)
app.include_router(router)


@app.get("/")
def root():
    return {
        "service": "ghostbusters-connector",
        "docs": "/docs",
        "endpoints": ["/api/health", "/api/priorities", "/api/sync", "/api/chats"],
    }


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("CONNECTOR_HOST", "127.0.0.1")
    port = int(os.environ.get("CONNECTOR_PORT", "8787"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
