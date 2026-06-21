"""Generate a realistic dummy chat.db for local Ghostbusters development."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)


def _apple_ts(dt: datetime) -> int:
    return int((dt - APPLE_EPOCH).total_seconds() * 1_000_000_000)


def create_dummy_db(db_path: str = "dummy_chat.db") -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.executescript(
        """
        DROP TABLE IF EXISTS chat_message_join;
        DROP TABLE IF EXISTS message;
        DROP TABLE IF EXISTS handle;
        DROP TABLE IF EXISTS chat;

        CREATE TABLE chat (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT,
            display_name TEXT,
            chat_identifier TEXT
        );

        CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT,
            attributedBody BLOB,
            is_from_me INTEGER,
            is_read INTEGER,
            date INTEGER,
            handle_id INTEGER
        );

        CREATE TABLE handle (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT
        );

        CREATE TABLE chat_message_join (
            chat_id INTEGER,
            message_id INTEGER
        );
        """
    )

    now = datetime.now(tz=timezone.utc)

    def insert_handle(phone: str) -> int:
        cur.execute("INSERT INTO handle (id) VALUES (?)", (phone,))
        return cur.lastrowid

    def insert_chat(guid: str, display_name: str, chat_identifier: str) -> int:
        cur.execute(
            "INSERT INTO chat (guid, display_name, chat_identifier) VALUES (?, ?, ?)",
            (guid, display_name, chat_identifier),
        )
        return cur.lastrowid

    def insert_messages(
        chat_id: int,
        handle_id: int,
        messages: list[tuple[str, bool, datetime, bool]],
    ) -> None:
        for text, is_from_me, ts, is_read in messages:
            cur.execute(
                """
                INSERT INTO message (text, is_from_me, is_read, date, handle_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (text, int(is_from_me), int(is_read), _apple_ts(ts), handle_id),
            )
            msg_id = cur.lastrowid
            cur.execute(
                "INSERT INTO chat_message_join (chat_id, message_id) VALUES (?, ?)",
                (chat_id, msg_id),
            )

    # --- 1-on-1 conversations -------------------------------------------------

    jordan_handle = insert_handle("+18885551212")
    jordan_chat = insert_chat("iMessage;-;+18885551212", "+1 (888) 555-1212", "+18885551212")
    insert_messages(
        jordan_chat,
        jordan_handle,
        [
            ("Hey! Are you free this weekend?", False, now - timedelta(hours=6), True),
            ("Maybe — what's up?", True, now - timedelta(hours=5, minutes=45), True),
            ("A few of us are doing brunch Saturday. You in?", False, now - timedelta(hours=5, minutes=30), True),
            ("Sounds fun! What time?", True, now - timedelta(hours=5), True),
            ("Hi!", False, now - timedelta(minutes=3), False),
        ],
    )

    kelly_handle = insert_handle("+15555648583")
    kelly_chat = insert_chat("iMessage;-;+15555648583", "+1 (555) 564-8583", "+15555648583")
    insert_messages(
        kelly_chat,
        kelly_handle,
        [
            ("Did you finish the slides for Monday?", False, now - timedelta(days=1, hours=2), True),
            ("Almost — sending tonight", True, now - timedelta(days=1), True),
            ("Great, the client asked for a pricing section too", False, now - timedelta(hours=8), True),
            ("Hi!", False, now - timedelta(minutes=3), False),
        ],
    )

    alex_handle = insert_handle("+15551234567")
    alex_chat = insert_chat("iMessage;-;+15551234567", "Alex Chen", "+15551234567")
    insert_messages(
        alex_chat,
        alex_handle,
        [
            ("Dinner tomorrow still on?", False, now - timedelta(hours=12), True),
            ("Yep! I was thinking that Thai place on 5th", True, now - timedelta(hours=11), True),
            ("Perfect. 7pm?", False, now - timedelta(hours=10), True),
            ("Hey, are we still on for dinner tomorrow?", False, now - timedelta(minutes=45), False),
        ],
    )

    mom_handle = insert_handle("+15559876543")
    mom_chat = insert_chat("iMessage;-;+15559876543", "Mom", "+15559876543")
    insert_messages(
        mom_chat,
        mom_handle,
        [
            ("Happy birthday sweetie!! 🎂", False, now - timedelta(days=2), True),
            ("Thanks mom!!", True, now - timedelta(days=2), True),
            ("Call me when you get a chance", False, now - timedelta(hours=4), False),
        ],
    )

    sam_handle = insert_handle("+15552345678")
    sam_chat = insert_chat("iMessage;-;+15552345678", "Sam Rivera", "+15552345678")
    insert_messages(
        sam_chat,
        sam_handle,
        [
            ("Bro the game last night was insane", False, now - timedelta(days=1, hours=6), True),
            ("I know!! That last-minute goal", True, now - timedelta(days=1, hours=5), True),
            ("We need tickets for the next one", False, now - timedelta(hours=2), True),
            ("Can you cover my shift Friday? I have a concert", False, now - timedelta(minutes=90), False),
        ],
    )

    dr_handle = insert_handle("+15558765432")
    dr_chat = insert_chat("iMessage;-;+15558765432", "Dr. Patel's Office", "+15558765432")
    insert_messages(
        dr_chat,
        dr_handle,
        [
            ("Reminder: annual checkup Thu 2pm", False, now - timedelta(days=3), True),
            ("Confirmed, thank you", True, now - timedelta(days=3), True),
            ("Please arrive 15 min early for paperwork", False, now - timedelta(hours=20), False),
        ],
    )

    recruiter_handle = insert_handle("+15554443322")
    recruiter_chat = insert_chat("iMessage;-;+15554443322", "Morgan (Recruiter)", "+15554443322")
    insert_messages(
        recruiter_chat,
        recruiter_handle,
        [
            ("Hi! Saw your profile — interested in a senior role at Stripe?", False, now - timedelta(hours=6), True),
            ("Thanks for reaching out! Can you share more details?", True, now - timedelta(hours=5), True),
            ("Absolutely — 30 min call this week?", False, now - timedelta(hours=1), False),
        ],
    )

    dad_handle = insert_handle("+15551112233")
    dad_chat = insert_chat("iMessage;-;+15551112233", "Dad", "+15551112233")
    insert_messages(
        dad_chat,
        dad_handle,
        [
            ("Your car registration expires next month", False, now - timedelta(days=5), True),
            ("Thanks for the heads up", True, now - timedelta(days=5), True),
            ("Sent you the DMV link", False, now - timedelta(days=4), True),
        ],
    )

    sarah_handle = insert_handle("+15559988777")
    sarah_chat = insert_chat("iMessage;-;+15559988777", "Sarah Kim", "+15559988777")
    insert_messages(
        sarah_chat,
        sarah_handle,
        [
            ("Reunion planning — who's in for July?", False, now - timedelta(days=2), True),
            ("Count me in!", True, now - timedelta(days=2), True),
            ("Venue options in the group doc", False, now - timedelta(days=1), True),
        ],
    )

    amazon_handle = insert_handle("+15550001234")
    amazon_chat = insert_chat("iMessage;-;+15550001234", "Amazon", "+15550001234")
    insert_messages(
        amazon_chat,
        amazon_handle,
        [
            ("Your package was delivered to the front door", False, now - timedelta(hours=3), True),
        ],
    )

    # --- Group chats ----------------------------------------------------------

    work_handle = insert_handle("chat-work-deck")
    work_chat = insert_chat("iMessage;+;chat-work-deck", "Work Group", "chat-work-deck")
    insert_messages(
        work_chat,
        work_handle,
        [
            ("Standup moved to 10:30 today", False, now - timedelta(hours=7), True),
            ("Got it", True, now - timedelta(hours=6, minutes=50), True),
            ("Can someone review the deck before 3pm?", False, now - timedelta(hours=3), False),
            ("I can take a look at 2", True, now - timedelta(hours=2, minutes=30), True),
        ],
    )

    roommates_handle = insert_handle("chat-roommates")
    roommates_chat = insert_chat("iMessage;+;chat-roommates", "Roommates 🏠", "chat-roommates")
    insert_messages(
        roommates_chat,
        roommates_handle,
        [
            ("Rent is due Friday", False, now - timedelta(days=1), True),
            ("Sent mine", True, now - timedelta(hours=18), True),
            ("Who's taking out trash this week?", False, now - timedelta(hours=5), False),
        ],
    )

    book_club_handle = insert_handle("chat-book-club")
    book_club_chat = insert_chat("iMessage;+;chat-book-club", "Book Club", "chat-book-club")
    insert_messages(
        book_club_chat,
        book_club_handle,
        [
            ("This month's pick: Project Hail Mary", False, now - timedelta(days=4), True),
            ("Loved that one!", True, now - timedelta(days=3), True),
            ("Discussion Sunday 4pm — who's hosting?", False, now - timedelta(hours=14), False),
        ],
    )

    conn.commit()
    conn.close()
    print(f"Created {db_path} with 13 conversations")


if __name__ == "__main__":
    create_dummy_db()
