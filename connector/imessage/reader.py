"""Read-only access to macOS iMessage chat.db."""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)


@dataclass
class IMessage:
    row_id: int
    chat_id: str
    chat_guid: str
    contact_handle: str
    contact_name: Optional[str]
    text: str
    is_from_me: bool
    timestamp: datetime
    is_read: bool


@dataclass
class ChatSummary:
    chat_id: str
    chat_guid: str
    display_name: str
    contact_handle: str
    last_message: str
    last_message_at: datetime
    is_from_me: bool
    unread_count: int


def default_db_path() -> Path:
    override = os.environ.get("IMESSAGE_DB_PATH")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Messages" / "chat.db"


def dummy_db_path() -> Path:
    return Path(__file__).resolve().parent.parent / "dummy_chat.db"


def working_reader() -> IMessageReader:
    """Return a reader that can actually query, falling back to dummy_chat.db."""
    primary = IMessageReader()
    candidates = [primary.db_path]
    dummy = dummy_db_path()
    if dummy not in candidates:
        candidates.append(dummy)

    for path in candidates:
        reader = IMessageReader(path)
        if not reader.is_available():
            continue
        try:
            with reader._connect() as conn:
                conn.execute("SELECT 1").fetchone()
            return reader
        except sqlite3.OperationalError:
            continue
    return primary


def _apple_ts_to_datetime(raw: int | None) -> datetime:
    if not raw:
        return datetime.now(tz=timezone.utc)
    # chat.db stores nanoseconds since 2001-01-01 on modern macOS
    seconds = raw / 1_000_000_000 if raw > 10_000_000_000 else raw
    return APPLE_EPOCH + timedelta(seconds=seconds)


def _decode_attributed_body(blob: bytes | None) -> str:
    """Best-effort extraction of plain text from attributedBody blobs."""
    if not blob:
        return ""

    # NSString + length-prefixed UTF-8 (common on Ventura+)
    match = re.search(rb"NSString\x00.{1,20}(.+?)\x00", blob, re.DOTALL)
    if match:
        candidate = match.group(1)
        # Strip leading length/control bytes
        for i in range(min(8, len(candidate))):
            try:
                text = candidate[i:].decode("utf-8", errors="strict").strip("\x00")
                if text and text.isprintable():
                    return text
            except UnicodeDecodeError:
                continue

    # Fallback: longest printable UTF-8 run
    runs = re.findall(rb"[\x20-\x7e\u00a0-\uffff]{4,}", blob)
    if runs:
        try:
            return max((r.decode("utf-8", errors="ignore") for r in runs), key=len)
        except Exception:
            pass

    return ""


def _extract_text(row: sqlite3.Row) -> str:
    text = row["text"] or ""
    if text.strip():
        return text.strip()
    return _decode_attributed_body(row["attributedBody"])


class IMessageReader:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or default_db_path()

    def is_available(self) -> bool:
        return self.db_path.exists()

    def _connect(self) -> sqlite3.Connection:
        if not self.is_available():
            raise FileNotFoundError(
                f"iMessage database not found at {self.db_path}. "
                "Ensure Messages is set up and grant Full Disk Access to your terminal."
            )
        uri = f"file:{self.db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def list_recent_chats(self, limit: int = 20) -> list[ChatSummary]:
        query = """
        SELECT
            c.ROWID AS chat_id,
            c.guid AS chat_guid,
            c.display_name,
            c.chat_identifier,
            m.text,
            m.attributedBody,
            m.is_from_me,
            m.is_read,
            m.date,
            h.id AS handle_id
        FROM chat c
        JOIN chat_message_join cmj ON cmj.chat_id = c.ROWID
        JOIN message m ON m.ROWID = cmj.message_id
        LEFT JOIN handle h ON h.ROWID = m.handle_id
        WHERE m.ROWID = (
            SELECT MAX(m2.ROWID)
            FROM message m2
            JOIN chat_message_join cmj2 ON cmj2.message_id = m2.ROWID
            WHERE cmj2.chat_id = c.ROWID
        )
        ORDER BY m.date DESC
        LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(query, (limit,)).fetchall()

        chats: list[ChatSummary] = []
        for row in rows:
            body = _extract_text(row)
            display = row["display_name"] or row["handle_id"] or row["chat_identifier"] or "Unknown"
            chats.append(
                ChatSummary(
                    chat_id=str(row["chat_id"]),
                    chat_guid=row["chat_guid"] or "",
                    display_name=display,
                    contact_handle=row["handle_id"] or row["chat_identifier"] or "",
                    last_message=body,
                    last_message_at=_apple_ts_to_datetime(row["date"]),
                    is_from_me=bool(row["is_from_me"]),
                    unread_count=0 if row["is_from_me"] or row["is_read"] else 1,
                )
            )
        return chats

    def get_messages_for_chat(self, chat_id: str, limit: int = 50) -> list[IMessage]:
        query = """
        SELECT
            m.ROWID AS message_id,
            c.ROWID AS chat_id,
            c.guid AS chat_guid,
            h.id AS handle_id,
            c.display_name,
            m.text,
            m.attributedBody,
            m.is_from_me,
            m.is_read,
            m.date
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        JOIN chat c ON c.ROWID = cmj.chat_id
        LEFT JOIN handle h ON h.ROWID = m.handle_id
        WHERE c.ROWID = ?
        ORDER BY m.date DESC
        LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(query, (chat_id, limit)).fetchall()

        messages: list[IMessage] = []
        for row in rows:
            body = _extract_text(row)
            if not body:
                continue
            display = row["display_name"] or row["handle_id"] or "Unknown"
            messages.append(
                IMessage(
                    row_id=row["message_id"],
                    chat_id=str(row["chat_id"]),
                    chat_guid=row["chat_guid"] or "",
                    contact_handle=row["handle_id"] or "",
                    contact_name=display if not row["is_from_me"] else None,
                    text=body,
                    is_from_me=bool(row["is_from_me"]),
                    timestamp=_apple_ts_to_datetime(row["date"]),
                    is_read=bool(row["is_read"]),
                )
            )
        return list(reversed(messages))

    def get_recent_inbound_messages(self, limit: int = 100) -> list[IMessage]:
        query = """
        SELECT
            m.ROWID AS message_id,
            c.ROWID AS chat_id,
            c.guid AS chat_guid,
            h.id AS handle_id,
            c.display_name,
            m.text,
            m.attributedBody,
            m.is_from_me,
            m.is_read,
            m.date
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        JOIN chat c ON c.ROWID = cmj.chat_id
        LEFT JOIN handle h ON h.ROWID = m.handle_id
        WHERE m.is_from_me = 0
        ORDER BY m.date DESC
        LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(query, (limit,)).fetchall()

        messages: list[IMessage] = []
        for row in rows:
            body = _extract_text(row)
            if not body:
                continue
            display = row["display_name"] or row["handle_id"] or "Unknown"
            messages.append(
                IMessage(
                    row_id=row["message_id"],
                    chat_id=str(row["chat_id"]),
                    chat_guid=row["chat_guid"] or "",
                    contact_handle=row["handle_id"] or "",
                    contact_name=display,
                    text=body,
                    is_from_me=False,
                    timestamp=_apple_ts_to_datetime(row["date"]),
                    is_read=bool(row["is_read"]),
                )
            )
        return messages
