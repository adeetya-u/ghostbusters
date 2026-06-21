#!/usr/bin/env python3
"""Benchmark Dad thread: per-chat HydraDB window + Nebius synthesis."""

from __future__ import annotations

import json
import time
import urllib.request

from dotenv import load_dotenv
from pathlib import Path

_connector = Path(__file__).resolve().parent
load_dotenv(_connector.parent / ".env")
load_dotenv(_connector / ".env")

DAD_CHAT_ID = "8"
BASE = "http://127.0.0.1:8787"


def ms(seconds: float) -> str:
    return f"{seconds * 1000:.0f}ms"


def timed(label: str, fn):
    start = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - start
    print(f"  {label}: {ms(elapsed)}")
    return result, elapsed


def main() -> None:
    from hydra.store import HydraMemoryStore
    from imessage.reader import working_reader
    from services.hydra_generation import fetch_hydra_context, generate_chat_reply_suggestions_with_context
    from services.priorities import find_chat_for_suggestions
    from services.suggestion_cache import invalidate_chat

    reader = working_reader()
    chat = find_chat_for_suggestions(reader, chat_id=DAD_CHAT_ID)
    if not chat:
        raise SystemExit(f"Dad chat {DAD_CHAT_ID} not found")

    store = HydraMemoryStore()
    sub_tenant = store.chat_sub_tenant_id(DAD_CHAT_ID)

    print("=== Dad workflow benchmark (chat_id=8) ===")
    print(f"Contact: {chat.display_name}")
    print(f"Hydra sub_tenant: {sub_tenant}")
    print(f"Reply target: {chat.reply_to_message[:80]}...")
    print()

    print("--- Step 1: Re-ingest Dad thread into isolated window ---")
    _, t_ingest = timed("ingest_chat_thread", lambda: store.ingest_chat_thread(reader, DAD_CHAT_ID, limit=40))
    print()

    print("--- Step 2: HydraDB query only (thinking + graph, chat window) ---")
    hydra_result, t_hydra = timed("fetch_hydra_context", lambda: fetch_hydra_context(chat, multiple=True))
    print(f"    chunks: {hydra_result.chunk_count}, context chars: {len(hydra_result.context)}")
    print(f"    preview: {hydra_result.context[:120].replace(chr(10), ' ')}...")
    print()

    print("--- Step 3: Full pipeline (HydraDB + Nebius LLM, 3 suggestions) ---")
    invalidate_chat(DAD_CHAT_ID)
    full_result, t_full = timed(
        "generate_chat_reply_suggestions_with_context",
        lambda: generate_chat_reply_suggestions_with_context(chat, count=3),
    )
    for i, s in enumerate(full_result.suggestions, 1):
        print(f"    [{i}] {s[:90]}{'...' if len(s) > 90 else ''}")
    print(f"    context snippets: {len(full_result.context_snippets)}")
    print()

    print("--- Step 4: HTTP API /suggestions (cold refresh=true) ---")
    invalidate_chat(DAD_CHAT_ID)

    def api_suggestions(refresh: bool) -> dict:
        url = f"{BASE}/api/chats/{DAD_CHAT_ID}/suggestions?limit=3&refresh={'true' if refresh else 'false'}"
        with urllib.request.urlopen(url, timeout=120) as resp:
            return json.loads(resp.read())

    _, t_api_cold = timed("GET suggestions refresh=true", lambda: api_suggestions(refresh=True))
    _, t_api_warm = timed("GET suggestions cached", lambda: api_suggestions(refresh=False))
    print()

    print("=== Summary ===")
    print(f"  Ingest Dad thread:     {ms(t_ingest)}")
    print(f"  Hydra query only:      {ms(t_hydra)}")
    print(f"  Hydra + Nebius (full): {ms(t_full)}")
    print(f"  API cold:              {ms(t_api_cold)}")
    print(f"  API cached:            {ms(t_api_warm)}")
    nebius_est = max(0.0, t_full - t_hydra)
    print(f"  Nebius estimate:       {ms(nebius_est)} (full minus hydra query)")


if __name__ == "__main__":
    main()
