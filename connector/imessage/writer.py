"""Write outbound messages into the local runtime chat.db (simulator/dev only)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from imessage.reader import (
    APPLE_EPOCH,
    IMessage,
    working_db_path,
)

DAD_DEMO_DISPLAY_NAME = "Dad"
DAD_DEMO_FOLLOW_UP_TEXT = (
    "Good. Save the smog certificate number, DMV sometimes asks for it later. "
    "Mom still wants a living room photo before we visit next month"
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


def _contact_handle_id(conn: sqlite3.Connection, chat_id: str) -> int | None:
    row = conn.execute(
        """
        SELECT m.handle_id
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        WHERE cmj.chat_id = ? AND m.is_from_me = 0 AND m.handle_id IS NOT NULL
        ORDER BY m.date DESC, m.ROWID DESC
        LIMIT 1
        """,
        (chat_id,),
    ).fetchone()
    return int(row[0]) if row else None


def _insert_inbound_message(
    conn: sqlite3.Connection,
    *,
    chat_id: str,
    handle_id: int,
    text: str,
    timestamp: datetime,
) -> int:
    conn.execute(
        """
        INSERT INTO message (text, is_from_me, is_read, date, handle_id)
        VALUES (?, 0, 0, ?, ?)
        """,
        (text, _apple_ts(timestamp), handle_id),
    )
    message_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        "INSERT INTO chat_message_join (chat_id, message_id) VALUES (?, ?)",
        (chat_id, message_id),
    )
    return message_id


def _dad_follow_up_already_sent(conn: sqlite3.Connection, chat_id: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        WHERE cmj.chat_id = ? AND m.is_from_me = 0 AND m.text = ?
        LIMIT 1
        """,
        (chat_id, DAD_DEMO_FOLLOW_UP_TEXT),
    ).fetchone()
    return row is not None


def _maybe_insert_dad_demo_follow_up(
    conn: sqlite3.Connection,
    *,
    chat_id: str,
    display_name: str | None,
    sent_at: datetime,
) -> None:
    if (display_name or "").strip() != DAD_DEMO_DISPLAY_NAME:
        return
    if _dad_follow_up_already_sent(conn, chat_id):
        return

    contact_handle = _contact_handle_id(conn, chat_id)
    if not contact_handle:
        return

    _insert_inbound_message(
        conn,
        chat_id=chat_id,
        handle_id=contact_handle,
        text=DAD_DEMO_FOLLOW_UP_TEXT,
        timestamp=sent_at + timedelta(seconds=2),
    )


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
        _maybe_insert_dad_demo_follow_up(
            conn,
            chat_id=str(chat_id),
            display_name=chat["display_name"],
            sent_at=now,
        )
        conn.commit()

    chat_guid = chat["guid"] or ""
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
