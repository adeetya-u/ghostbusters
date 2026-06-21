"""
Reads iMessage chat.db (real or test) and outputs conversations
in the format ghostbuster.process_conversations() expects.

Usage:
    python read_imessage.py                        # reads ~/Library/Messages/chat.db
    python read_imessage.py test_chat.db           # reads test DB
    python read_imessage.py test_chat.db --json    # prints raw JSON (for debugging)
"""

import sqlite3
import json
import sys
import os
from datetime import datetime, timezone
from ghostbuster import process_conversations

DEFAULT_DB = os.path.expanduser("~/Library/Messages/chat.db")
APPLE_EPOCH = 978307200  # 2001-01-01 00:00:00 UTC as Unix timestamp

def apple_to_unix(apple_ts: int) -> float:
    """Convert Apple nanoseconds to Unix seconds."""
    return (apple_ts / 1_000_000_000) + APPLE_EPOCH

def load_conversations(db_path: str) -> list[dict]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT ROWID as chat_id, chat_identifier, display_name FROM chat")
    chats = cur.fetchall()

    conversations = []
    now = datetime.now(timezone.utc).timestamp()

    for chat in chats:
        chat_id      = chat["chat_id"]
        contact_id   = chat["chat_identifier"]
        display_name = chat["display_name"]
        # 1:1 chats have a phone number (+...) or email as identifier; groups don't
        is_group     = not (contact_id.startswith("+") or "@" in contact_id)
        contact_name = display_name or contact_id

        cur.execute("""
            SELECT m.text, m.is_from_me, m.date
            FROM message m
            JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            WHERE cmj.chat_id = ?
              AND m.text IS NOT NULL
              AND m.text != ''
            ORDER BY m.date ASC
        """, (chat_id,))
        rows = cur.fetchall()

        if not rows:
            continue

        messages = [
            {
                "text":       row["text"],
                "is_from_me": bool(row["is_from_me"]),
                "timestamp":  apple_to_unix(row["date"]),
            }
            for row in rows
        ]

        last_ts   = messages[-1]["timestamp"]
        days_wait = round((now - last_ts) / 86400, 1)

        conversations.append({
            "contact_id":              contact_id,
            "contact_name":            contact_name,
            "is_group":                is_group,
            "days_since_last_message": days_wait,
            "messages":                messages,
        })

    conn.close()
    return conversations


if __name__ == "__main__":
    db_path    = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    print_json = "--json" in sys.argv

    print(f"Reading {db_path}...")
    convs = load_conversations(db_path)
    print(f"Loaded {len(convs)} conversations.\n")

    if print_json:
        print(json.dumps(convs, indent=2))
    else:
        result = process_conversations(convs)
        print(json.dumps(result, indent=2))
