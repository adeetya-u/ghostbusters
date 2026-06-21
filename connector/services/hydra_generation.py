"""Reply generation through HydraDB context (required) + LLM synthesis."""

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any

from hydra.activity_log import record_hydra_log
from imessage.reader import ChatSummary

HYDRA_QUERY_TIMEOUT_SECONDS = float(os.environ.get("HYDRA_QUERY_TIMEOUT", "12"))
NEBIUS_MODEL = os.environ.get("NEBIUS_MODEL", "meta-llama/Llama-3.3-70B-Instruct")


class HydraGenerationError(Exception):
    """Raised when HydraDB-backed reply generation fails."""


@dataclass
class HydraContextResult:
    context: str
    chunk_count: int
    configured: bool
    query: str


def hydra_generation_configured() -> bool:
    from hydra.store import HydraMemoryStore

    store = HydraMemoryStore()
    return store.is_configured and bool(_nebius_api_key())


def _nebius_api_key() -> str:
    return os.environ.get("NEBIUS_API_KEY", "").strip()


def _chunk_text(chunk: Any) -> str:
    for attr in ("chunk_content", "text", "content"):
        value = getattr(chunk, attr, None)
        if value and str(value).strip():
            return str(value).strip()
    return ""


def extract_hydra_context(result: Any, *, limit: int = 8) -> tuple[str, int]:
    """Build a single context string from HydraDB chunks and graph relations."""
    data = getattr(result, "data", result)
    parts: list[str] = []

    graph = getattr(data, "graph_context", None)
    if graph and getattr(graph, "synthesis_context", None):
        parts.append(str(graph.synthesis_context).strip())

    if graph:
        for path in (getattr(graph, "chunk_relations", None) or [])[:limit]:
            combined = getattr(path, "combined_context", None)
            if combined and str(combined).strip():
                parts.append(str(combined).strip())

    chunks = getattr(data, "chunks", []) or []
    for chunk in chunks[:limit]:
        text = _chunk_text(chunk)
        if text and text not in parts:
            parts.append(text)

    unique: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = part[:120]
        if key in seen:
            continue
        seen.add(key)
        unique.append(part)

    return "\n\n---\n\n".join(unique), len(chunks)


def _reply_query(chat: ChatSummary, *, multiple: bool) -> str:
    target = chat.reply_to_message if chat.needs_reply else chat.last_message
    sender = chat.reply_to_sender or chat.display_name
    if chat.is_group:
        lead = f"In my group chat '{chat.display_name}', {sender} said: {target[:200]}"
    else:
        lead = f"My contact {chat.display_name} said: {target[:200]}"

    if multiple:
        return (
            f"{lead}\n"
            "Using my message history and relationship context, draft 3 distinct brief "
            "iMessage reply options. Return ONLY a JSON array of 3 strings."
        )
    return (
        f"{lead}\n"
        "Using my message history and relationship context, draft one brief "
        "iMessage reply. Return ONLY the reply text."
    )


def fetch_hydra_context(chat: ChatSummary, *, multiple: bool = False) -> HydraContextResult:
    """Query HydraDB (thinking + graph) for personalized reply context."""
    from hydra.store import HydraMemoryStore

    store = HydraMemoryStore()
    query = _reply_query(chat, multiple=multiple)

    if not store.is_configured:
        record_hydra_log("skipped", reason="not_configured", chat_id=chat.chat_id)
        return HydraContextResult(context="", chunk_count=0, configured=False, query=query)

    record_hydra_log(
        "query_start",
        chat_id=chat.chat_id,
        contact=chat.display_name,
        query=query[:160],
    )

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                store.query_reply_context,
                query,
                chat_id=chat.chat_id,
                max_results=8,
            )
            result = future.result(timeout=HYDRA_QUERY_TIMEOUT_SECONDS)
    except FuturesTimeoutError:
        record_hydra_log(
            "query_timeout",
            chat_id=chat.chat_id,
            contact=chat.display_name,
            timeout_seconds=HYDRA_QUERY_TIMEOUT_SECONDS,
        )
        raise HydraGenerationError(
            f"HydraDB query timed out after {HYDRA_QUERY_TIMEOUT_SECONDS:.0f}s for {chat.display_name}."
        ) from None
    except Exception as exc:
        record_hydra_log(
            "query_error",
            chat_id=chat.chat_id,
            contact=chat.display_name,
            error=str(exc)[:200],
        )
        raise HydraGenerationError(f"HydraDB query failed: {exc}") from exc

    context, chunk_count = extract_hydra_context(result)
    if not context.strip():
        record_hydra_log(
            "query_empty",
            chat_id=chat.chat_id,
            contact=chat.display_name,
        )
        raise HydraGenerationError(
            f"HydraDB returned no usable context for {chat.display_name}. "
            "Run POST /api/sync to ingest messages first."
        )

    record_hydra_log(
        "query_ok",
        chat_id=chat.chat_id,
        contact=chat.display_name,
        chunks=chunk_count,
        preview=context[:180],
    )
    return HydraContextResult(
        context=context,
        chunk_count=chunk_count,
        configured=True,
        query=query,
    )


def _llm_from_hydra_context(
    chat: ChatSummary,
    hydra_context: str,
    *,
    multiple: bool,
) -> str:
    """Synthesize reply text strictly from HydraDB-retrieved context."""
    api_key = _nebius_api_key()
    if not api_key:
        raise HydraGenerationError(
            "NEBIUS_API_KEY is not set. HydraDB context retrieval requires an LLM "
            "to synthesize replies from that context."
        )

    target = chat.reply_to_message if chat.needs_reply else chat.last_message
    group_note = (
        " This is a group iMessage thread; keep replies appropriate for the whole group."
        if chat.is_group
        else ""
    )

    if multiple:
        system = (
            "You draft iMessage replies using ONLY the HydraDB context provided. "
            "Return exactly 3 different brief reply options as a JSON array of 3 strings. "
            f"No em dashes, no markdown, no labels.{group_note}"
        )
        user = (
            f"Contact/thread: {chat.display_name}\n"
            f"Message to reply to: {target}\n\n"
            f"HydraDB personalized context:\n{hydra_context}\n\n"
            "Return 3 distinct reply options as a JSON array."
        )
        max_tokens = 220
    else:
        system = (
            "You draft iMessage replies using ONLY the HydraDB context provided. "
            f"Return ONLY the reply text, no quotes.{group_note}"
        )
        user = (
            f"Contact/thread: {chat.display_name}\n"
            f"Message to reply to: {target}\n\n"
            f"HydraDB personalized context:\n{hydra_context}"
        )
        max_tokens = 80

    url = "https://api.studio.nebius.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": NEBIUS_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }

    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        try:
            import certifi

            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            text = result["choices"][0]["message"]["content"].strip()
            if not text:
                raise HydraGenerationError("LLM returned an empty suggestion.")
            record_hydra_log(
                "synthesis_ok",
                chat_id=chat.chat_id,
                contact=chat.display_name,
                preview=text[:120],
            )
            return text
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        raise HydraGenerationError(f"LLM HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise HydraGenerationError(f"LLM request failed: {exc.reason}") from exc
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise HydraGenerationError(f"Unexpected LLM response: {exc}") from exc


def _parse_suggestion_list(raw: str, count: int) -> list[str]:
    stripped = raw.strip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                items = [str(item).strip() for item in parsed if str(item).strip()]
                if items:
                    return items[:count]
        except json.JSONDecodeError:
            pass

    lines: list[str] = []
    for line in stripped.splitlines():
        cleaned = re.sub(r"^\s*\d+[\).\s-]+", "", line).strip().strip('"').strip("'")
        if cleaned:
            lines.append(cleaned)
    if lines:
        return lines[:count]

    raise HydraGenerationError("Could not parse reply suggestions from LLM output.")


def generate_chat_reply_suggestions(chat: ChatSummary, count: int = 3) -> list[str]:
    """
    Generate reply options for a chat.
    Always queries HydraDB first; LLM only sees HydraDB-retrieved context.
    """
    if not chat.needs_reply or not chat.reply_to_message.strip():
        raise HydraGenerationError("No inbound message to reply to.")

    hydra = fetch_hydra_context(chat, multiple=count > 1)
    raw = _llm_from_hydra_context(chat, hydra.context, multiple=count > 1)
    if count <= 1:
        return [raw]
    return _parse_suggestion_list(raw, count)


# Backwards-compatible alias used by older imports
fetch_personalized_context = fetch_hydra_context
