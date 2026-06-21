"""Write outbound messages into the local runtime chat.db (simulator/dev only)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from imessage.reader import (
    APPLE_EPOCH,
    IMessage,
    IMessageReader,
    format_sender_name,
    is_group_chat,
    working_db_path,
)


def _apple_ts(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int((dt - APPLE_EPOCH).total_seconds() * 1_000_000_000)


def _me_handle_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT ROWID FROM handle WHERE id = ?", ("Me",)).fetchone()
    if row:
        return int(row[0])
    conn.execute("INSERT INTO handle (id) VALUES (?)", ("Me",))
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def send_reply(chat_id: str, text: str) -> IMessage:
    body = text.strip()
    if not body:
        raise ValueError("Message text cannot be empty.")

    db_path = working_db_path()
    now = datetime.now(tz=timezone.utc)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        chat = conn.execute(
            "SELECT ROWID, guid, display_name FROM chat WHERE ROWID = ?",
            (chat_id,),
        ).fetchone()
        if not chat:
            raise LookupError(f"Chat {chat_id} not found.")

        handle_id = _me_handle_id(conn)
        conn.execute(
            """
            INSERT INTO message (text, is_from_me, is_read, date, handle_id)
            VALUES (?, 1, 1, ?, ?)
            """,
            (body, _apple_ts(now), handle_id),
        )
        message_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO chat_message_join (chat_id, message_id) VALUES (?, ?)",
            (chat_id, message_id),
        )
        conn.execute(
            """
            UPDATE message
            SET is_read = 1
            WHERE ROWID IN (
                SELECT m.ROWID
                FROM message m
                JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
                WHERE cmj.chat_id = ? AND m.is_from_me = 0
            )
            """,
            (chat_id,),
        )
        conn.commit()

    reader = IMessageReader(db_path)
    messages = reader.get_messages_for_chat(chat_id, limit=1)
    if messages:
        return messages[-1]

    chat_guid = chat["guid"] or ""
    group = is_group_chat(chat_guid)
    return IMessage(
        row_id=message_id,
        chat_id=str(chat_id),
        chat_guid=chat_guid,
        contact_handle="Me",
        contact_name=None,
        text=body,
        is_from_me=True,
        timestamp=now,
        is_read=True,
    )


def reset_runtime_db() -> None:
    """Restore runtime DB from the frozen initial snapshot."""
    from imessage.reader import initial_db_path, runtime_db_path
    import shutil

    initial = initial_db_path()
    runtime = runtime_db_path()
    if not initial.exists():
        raise FileNotFoundError(f"Initial snapshot missing at {initial}")
    shutil.copy2(initial, runtime)
