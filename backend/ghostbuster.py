"""
Ghostbuster: AI-powered iMessage reply prioritizer

Pipeline:
  1. Filter locally  — drop non-candidates, no API cost
  2. HydraDB ingest  — send raw conversation text, it handles embedding/graph
  3. HydraDB query   — returns ranked context chunks ready for an LLM
  4. Nebius LLM      — receives context, picks top 3, generates replies

Run: import and call process_conversations(conversations)
Input/output format documented at the bottom of this file.
"""

import os
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from openai import OpenAI
from hydra_db import HydraDB

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

NEBIUS_API_KEY  = os.environ.get("NEBIUS_API_KEY", "")
HYDRADB_API_KEY = os.environ.get("HYDRA_DB_API_KEY", "")

LOOKBACK_DAYS      = 14
TOP_N              = 3
MIN_MESSAGES       = 2
MIN_MESSAGE_LENGTH = 8

NEBIUS_MODEL   = "meta-llama/Llama-3.3-70B-Instruct"
HYDRA_TENANT   = "ghostbuster"

INDEXING_POLL_INTERVAL = 2     # seconds between status checks
INDEXING_TIMEOUT       = 120   # seconds before giving up (infer=True takes longer)

# ── Clients ───────────────────────────────────────────────────────────────────

def _nebius() -> OpenAI:
    if not NEBIUS_API_KEY:
        raise ValueError("NEBIUS_API_KEY not set")
    return OpenAI(
        base_url="https://api.studio.nebius.com/v1/",
        api_key=NEBIUS_API_KEY,
    )

def _hydra() -> HydraDB:
    if not HYDRADB_API_KEY:
        raise ValueError("HYDRA_DB_API_KEY not set")
    return HydraDB(token=HYDRADB_API_KEY)

# ── Step 1: Local filter ──────────────────────────────────────────────────────

def filter_candidates(conversations: list[dict]) -> list[dict]:
    """
    Drop obvious non-candidates without any API calls.
    The 2-week window + basic rules keep the candidate pool reasonable.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    out = []

    for conv in conversations:
        messages = conv.get("messages", [])

        if len(messages) < MIN_MESSAGES:
            continue

        if conv.get("is_group", False):
            continue

        last = messages[-1]

        # They must be waiting on you
        if last.get("is_from_me", True):
            continue

        # Within the 2-week window
        ts = last.get("timestamp")
        if ts:
            t = (
                datetime.fromtimestamp(ts, tz=timezone.utc)
                if isinstance(ts, (int, float))
                else datetime.fromisoformat(str(ts)).replace(tzinfo=timezone.utc)
            )
            if t < cutoff:
                continue

        # Real message content, not a reaction or empty ping
        if len((last.get("text") or "").strip()) < MIN_MESSAGE_LENGTH:
            continue

        out.append(conv)

    return out

# ── Step 2: Ingest into HydraDB ───────────────────────────────────────────────

def _conversation_text(conv: dict) -> str:
    """
    Human-readable conversation formatted for HydraDB ingestion.
    Days waiting is surfaced prominently so Nebius has an explicit time signal.
    """
    name = conv.get("contact_name") or conv.get("contact_id", "Unknown")
    days = conv.get("days_since_last_message", "?")
    last_msg = (conv.get("messages") or [{}])[-1].get("text", "")

    lines = [
        f"CONTACT: {name}",
        f"DAYS WITHOUT REPLY: {days}",
        f"THEIR LAST MESSAGE: {last_msg}",
        f"CONVERSATION HISTORY:",
    ]
    for m in conv.get("messages", [])[-20:]:
        speaker = "Me" if m.get("is_from_me") else name
        text = (m.get("text") or "").strip()
        if text:
            lines.append(f"  {speaker}: {text}")
    return "\n".join(lines)

def _ensure_tenant(hydra: HydraDB) -> None:
    try:
        hydra.tenants.create(tenant_id=HYDRA_TENANT)
    except Exception:
        return  # already exists, no need to wait

    # Poll until tenant infrastructure is fully provisioned
    deadline = time.time() + INDEXING_TIMEOUT
    while time.time() < deadline:
        try:
            status = hydra.tenants.status(tenant_id=HYDRA_TENANT)
            components = getattr(status, "data", None) or {}
            if all(v == "ready" for v in components.values()):
                break
        except Exception:
            pass
        time.sleep(INDEXING_POLL_INTERVAL)

def ingest_and_wait(conversations: list[dict], hydra: HydraDB, session_id: str) -> list[str]:
    """
    Send all conversation texts to HydraDB as memories.
    HydraDB handles parsing, chunking, embedding, and graph construction.
    Returns the ingestion IDs so we can poll for completion.
    """
    memories = [
        {
            "text": _conversation_text(c),
            "infer": True,   # let HydraDB extract implicit context
            "additional_metadata": {
                "contact_id":   c.get("contact_id", ""),
                "contact_name": c.get("contact_name", ""),
                "days_waiting": str(c.get("days_since_last_message", "")),
                "last_message": (c.get("messages") or [{}])[-1].get("text", ""),
                "session_id":   session_id,
            },
        }
        for c in conversations
    ]

    result = hydra.context.ingest(
        type="memory",
        tenant_id=HYDRA_TENANT,
        sub_tenant_id=session_id,
        memories=json.dumps(memories),
    )

    # IDs are nested at result.data.results[i].id
    results = getattr(getattr(result, "data", None), "results", []) or []
    ids = [item.id for item in results if getattr(item, "id", None)]
    print(f"[hydradb] queued ids: {ids}")

    if ids:
        deadline = time.time() + INDEXING_TIMEOUT
        while time.time() < deadline:
            status = hydra.context.status(
                tenant_id=HYDRA_TENANT,
                sub_tenant_id=session_id,
                ids=ids,
            )
            statuses = [s.indexing_status for s in status.data.statuses]
            print(f"[hydradb] indexing statuses: {statuses}")

            if any(s == "errored" for s in statuses):
                raise RuntimeError(f"HydraDB indexing failed: {status.data.statuses}")

            # graph_creation means searchable; completed means fully indexed
            if all(s in ("graph_creation", "completed") for s in statuses):
                break

            time.sleep(INDEXING_POLL_INTERVAL)

    return ids

# ── Step 3: Query HydraDB ─────────────────────────────────────────────────────

def retrieve_context(hydra: HydraDB, session_id: str) -> str:
    """
    Ask HydraDB which conversations are most worth replying to.
    Returns the context string to pass directly to Nebius.
    """
    result = hydra.query(
        tenant_id=HYDRA_TENANT,
        sub_tenant_id=session_id,
        query=(
            "Which unanswered conversations are most urgent or important "
            "for me to reply to? Who has been waiting longest or seems closest to me?"
        ),
        type="memory",
        query_by="hybrid",
        mode="thinking",
        graph_context=True,
    )
    print(f"[hydradb] raw result: {result}")
    data = getattr(result, "data", None)
    chunks = getattr(data, "chunks", []) or []
    print(f"[hydradb] chunks returned: {len(chunks)}")

    # Extract text from each chunk and join into one context string
    texts = []
    for chunk in chunks:
        text = getattr(chunk, "text", None) or getattr(chunk, "content", None) or str(chunk)
        if text:
            texts.append(text)

    context = "\n\n---\n\n".join(texts)
    print(f"[hydradb] context ({len(context)} chars): {context[:300]}")
    return context

# ── Step 4: Nebius LLM — pick top 3 + generate replies ───────────────────────

_SYSTEM = f"""You are helping someone who ghosts people catch up on their most important unanswered iMessages.

You will receive context about their unanswered conversations retrieved from HydraDB, which includes
relationship context and conversation history.

Score each conversation on these two dimensions to pick the top {TOP_N}:

URGENCY (based on message content):
- High: emotional language, health concerns, time-sensitive events, explicit asks for a reply
- Medium: plans that need confirming, questions with a clear answer needed
- Low: casual catch-up, no clear action needed

TIME (based on days without reply):
- 7+ days: very overdue
- 3–6 days: overdue
- 1–2 days: mild

Prioritize conversations where BOTH urgency and time are high. Use the conversation history
and relationship context to judge closeness — a 3-day wait from a close friend matters more
than a 7-day wait from an acquaintance.

Then write a short, natural reply for each of the top {TOP_N}:
- Sound human, not AI
- 1–3 sentences max
- Acknowledge the wait only if it has been more than 3 days
- Do NOT open with "I"

Reply with ONLY valid JSON, no explanation:
{{
  "top_candidates": [
    {{
      "contact_name": "<name from context>",
      "contact_id": "<id from context>",
      "days_waiting": "<number>",
      "last_message": "<their last message>",
      "urgency": "<high | medium | low>",
      "suggested_reply": "<your reply>",
      "reply_tone": "<warm | casual | apologetic | playful>"
    }}
  ]
}}"""

def _extract_json(text: str) -> str:
    """Strip markdown code fences if the LLM wrapped its JSON in them."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # drop opening fence line and closing fence line
        inner = [l for l in lines[1:] if l.strip() != "```"]
        text = "\n".join(inner).strip()
    return text

def pick_and_reply(nebius: OpenAI, context: str) -> list[dict]:
    resp = nebius.chat.completions.create(
        model=NEBIUS_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": f"My unanswered conversations:\n\n{context}"},
        ],
        max_tokens=800,
        temperature=0.7,
    )
    raw = resp.choices[0].message.content.strip()
    if not raw:
        print("[ghostbuster] Warning: LLM returned empty response")
        return []
    try:
        data = json.loads(_extract_json(raw))
        return data.get("top_candidates", [])
    except json.JSONDecodeError:
        print(f"[ghostbuster] Warning: could not parse LLM response as JSON:\n{raw}")
        return []

# ── Main entry point ──────────────────────────────────────────────────────────

def process_conversations(conversations: list[dict]) -> dict:
    """
    Main function — call this from your iMessage plugin script.

    Input : list of conversation dicts  (see INPUT FORMAT below)
    Output: dict with top 3 candidates + crafted replies (see OUTPUT FORMAT below)
    """
    if not conversations:
        return {"top_candidates": [], "total_unread": 0}

    nebius = _nebius()
    hydra  = _hydra()

    # Unique ID per run so sessions don't bleed into each other
    session_id = str(uuid.uuid4())

    # 1. Filter locally — no API cost
    candidates = filter_candidates(conversations)
    if not candidates:
        return {"top_candidates": [], "total_unread": 0}

    # 2. Send raw text to HydraDB — it handles all embedding/graph internally
    _ensure_tenant(hydra)
    ingest_and_wait(candidates, hydra, session_id)

    # 3. Query HydraDB — returns ranked context ready for an LLM
    context = retrieve_context(hydra, session_id)

    # 4. Nebius LLM picks top 3 and writes replies from the HydraDB context
    top3 = pick_and_reply(nebius, context)

    return {
        "top_candidates": top3,
        "total_unread":   len(candidates),
    }


# ── CLI for testing ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        path = sys.argv[1]
        if path.endswith(".db"):
            from read_imessage import load_conversations
            data = load_conversations(path)
        else:
            with open(path) as f:
                data = json.load(f)
    else:
        now = datetime.now(timezone.utc).timestamp()
        data = [
            {
                "contact_id": "+15551234567", "contact_name": "Alex",
                "is_group": False, "days_since_last_message": 3,
                "messages": [
                    {"text": "hey how are you!",                          "is_from_me": False, "timestamp": now - 86400 * 5},
                    {"text": "doing well, you?",                          "is_from_me": True,  "timestamp": now - 86400 * 4},
                    {"text": "good! are you coming to the party Saturday?","is_from_me": False, "timestamp": now - 86400 * 3},
                ],
            },
            {
                "contact_id": "+15559876543", "contact_name": "Mom",
                "is_group": False, "days_since_last_message": 7,
                "messages": [
                    {"text": "Did you eat dinner?",                        "is_from_me": False, "timestamp": now - 86400 * 8},
                    {"text": "yes!",                                       "is_from_me": True,  "timestamp": now - 86400 * 7},
                    {"text": "Ok good. Miss you, call me when you can",    "is_from_me": False, "timestamp": now - 86400 * 7},
                ],
            },
            {
                "contact_id": "+15550001111", "contact_name": "Jordan",
                "is_group": False, "days_since_last_message": 1,
                "messages": [
                    {"text": "wanna grab lunch tomorrow?",                 "is_from_me": False, "timestamp": now - 86400},
                    {"text": "sounds good!",                               "is_from_me": True,  "timestamp": now - 86400 + 3600},
                    {"text": "awesome, noon work?",                        "is_from_me": False, "timestamp": now - 3600 * 5},
                ],
            },
        ]

    result = process_conversations(data)
    print(json.dumps(result, indent=2))


# ══════════════════════════════════════════════════════════════════════════════
# INPUT FORMAT (each conversation dict):
# {
#   "contact_id":              str,    # phone number or iMessage handle
#   "contact_name":            str,    # display name (can be null)
#   "is_group":                bool,
#   "days_since_last_message": int,    # pre-compute when reading iMessage DB
#   "messages": [                      # ordered oldest → newest
#     {
#       "text":        str,
#       "is_from_me":  bool,
#       "timestamp":   float            # Unix timestamp (seconds)
#     }
#   ]
# }
#
# OUTPUT FORMAT:
# {
#   "top_candidates": [
#     {
#       "contact_name":    str,
#       "contact_id":      str,
#       "days_waiting":    str,
#       "last_message":    str,
#       "suggested_reply": str,
#       "reply_tone":      str    # warm | casual | apologetic | playful
#     }
#   ],
#   "total_unread": int
# }
# ══════════════════════════════════════════════════════════════════════════════
