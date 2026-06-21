"""Generate a realistic dummy chat.db for local Ghostbusters development."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil

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

    def insert_group_messages(
        chat_id: int,
        messages: list[tuple[str, int, bool, datetime, bool]],
    ) -> None:
        for text, handle_id, is_from_me, ts, is_read in messages:
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
    jordan_chat = insert_chat("iMessage;-;+18885551212", "Jordan Adams", "+18885551212")
    insert_messages(
        jordan_chat,
        jordan_handle,
        [
            ("Did you end up trying that ramen place on Valencia?", False, now - timedelta(days=2), True),
            ("Yeah twice actually. The spicy miso is legit", True, now - timedelta(days=2), True),
            ("Ok I'm convinced. Hey! Are you free this weekend?", False, now - timedelta(hours=6), True),
            ("Maybe, what's up?", True, now - timedelta(hours=5, minutes=45), True),
            ("A few of us are doing brunch at Tartine Saturday. You in?", False, now - timedelta(hours=5, minutes=30), True),
            ("Sounds fun! What time?", True, now - timedelta(hours=5), True),
        ],
    )

    kelly_handle = insert_handle("+15555648583")
    kelly_chat = insert_chat("iMessage;-;+15555648583", "Kelly Brooks", "+15555648583")
    insert_messages(
        kelly_chat,
        kelly_handle,
        [
            ("Client kickoff got moved to Monday 9am btw", False, now - timedelta(days=2), True),
            ("Ugh ok. I'll shuffle the deck outline tonight", True, now - timedelta(days=2), True),
            ("Did you finish the slides for Monday?", False, now - timedelta(days=1, hours=2), True),
            ("Almost, sending tonight", True, now - timedelta(days=1), True),
            (
                "Great, the client asked for a pricing section too. "
                "They want tier comparison + implementation timeline if you have it",
                False,
                now - timedelta(hours=8),
                False,
            ),
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
            ("Perfect. 7pm? I'll grab us a res under Adams", False, now - timedelta(hours=10), True),
            (
                "Hey, are we still on for dinner tomorrow? "
                "Work ran long and I might be 10 min late",
                False,
                now - timedelta(minutes=45),
                True,
            ),
            ("No worries, see you at 7!", True, now - timedelta(minutes=20), True),
        ],
    )

    mom_handle = insert_handle("+15559876543")
    mom_chat = insert_chat("iMessage;-;+15559876543", "Mom", "+15559876543")
    insert_messages(
        mom_chat,
        mom_handle,
        [
            ("Happy birthday sweetie!! 🎂 Did you get the cake?", False, now - timedelta(days=2), True),
            ("Thanks mom!! Yes, roommates sang off-key at midnight", True, now - timedelta(days=2), True),
            ("😂 sounds about right. Dad says hi", False, now - timedelta(days=1, hours=6), True),
            (
                "Call me when you get a chance. Nothing bad, "
                "just want to hear how the new apartment is",
                False,
                now - timedelta(hours=4),
                True,
            ),
            ("Will call you tonight after dinner!", True, now - timedelta(hours=2), True),
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
            ("We need tickets for the next one, they're dropping Friday", False, now - timedelta(hours=2), True),
            (
                "Can you cover my shift Friday? I have a concert at the Fillmore "
                "and I'm double-booked. I'll swap you Saturday AM",
                False,
                now - timedelta(minutes=90),
                True,
            ),
            (
                "Sorry, can't cover Friday. Saturday AM is already booked for me",
                True,
                now - timedelta(minutes=30),
                True,
            ),
        ],
    )

    dr_handle = insert_handle("+15558765432")
    dr_chat = insert_chat("iMessage;-;+15558765432", "Dr. Patel's Office", "+15558765432")
    insert_messages(
        dr_chat,
        dr_handle,
        [
            ("Reminder: annual checkup Thu 2pm with Dr. Patel", False, now - timedelta(days=3), True),
            ("Confirmed, thank you", True, now - timedelta(days=3), True),
            ("Please bring insurance card + list of current meds", False, now - timedelta(days=2), True),
            (
                "Please arrive 15 min early for paperwork. "
                "Parking is in garage B, validation at front desk",
                False,
                now - timedelta(days=1),
                False,
            ),
        ],
    )

    recruiter_handle = insert_handle("+15554443322")
    recruiter_chat = insert_chat("iMessage;-;+15554443322", "Morgan (Recruiter)", "+15554443322")
    insert_messages(
        recruiter_chat,
        recruiter_handle,
        [
            (
                "Hi! Saw your profile on LinkedIn. Interested in a senior backend role "
                "at Stripe? Remote-friendly, infra team",
                False,
                now - timedelta(hours=6),
                True,
            ),
            ("Thanks for reaching out! Can you share comp range + team size?", True, now - timedelta(hours=5), True),
            (
                "Absolutely, base is competitive plus equity. 30 min call this week? "
                "I have Thu 11am or Fri 2pm PT",
                False,
                now - timedelta(hours=1),
                False,
            ),
        ],
    )

    dad_handle = insert_handle("+15551112233")
    dad_chat = insert_chat("iMessage;-;+15551112233", "Dad", "+15551112233")
    insert_messages(
        dad_chat,
        dad_handle,
        [
            (
                "How's the move going? Mom wants to send the extra sheet set for the new bed",
                False,
                now - timedelta(days=21, hours=4),
                True,
            ),
            (
                "Almost done unpacking. Place is on 24th near Potrero, apt 4B. "
                "Kitchen is tiny but the light is amazing",
                True,
                now - timedelta(days=21, hours=2),
                True,
            ),
            (
                "Good spot. Remember to update your address with DMV when you get a sec, "
                "they mail registration stickers to whatever address they have on file",
                False,
                now - timedelta(days=20, hours=6),
                True,
            ),
            ("On it. Also hung shelves in the bedroom already", True, now - timedelta(days=20, hours=4), True),
            (
                "Send photos when the living room is set up. Your mom keeps asking about the view",
                False,
                now - timedelta(days=18, hours=8),
                True,
            ),
            (
                "Will send this weekend. You can see the Bay from the bedroom window, it's wild",
                True,
                now - timedelta(days=18, hours=6),
                True,
            ),
            (
                "Proud of you for landing that SF place. Rent is nuts but the SoMa commute must be better",
                False,
                now - timedelta(days=17, hours=3),
                True,
            ),
            ("22 bus gets me to the office in about 20 min now", True, now - timedelta(days=17, hours=2), True),
            (
                "Your car registration on the Honda expires next month. "
                "Don't wait till the last week like last year",
                False,
                now - timedelta(days=14, hours=5),
                True,
            ),
            (
                "Yeah still the 2019 Civic. I remember the rush fees last time, won't cut it close again",
                True,
                now - timedelta(days=14, hours=4),
                True,
            ),
            (
                "Smog check has to pass before you can renew online. "
                "AAA on Stevens Creek still does walk-ins, no appointment",
                False,
                now - timedelta(days=13, hours=10),
                True,
            ),
            ("The one next to Trader Joe's on Stevens Creek?", True, now - timedelta(days=13, hours=9), True),
            (
                "That's the one. Bring your AAA card, you're still on our family membership",
                False,
                now - timedelta(days=13, hours=8),
                True,
            ),
            ("Still have the card in my wallet, thanks", True, now - timedelta(days=13, hours=7), True),
            (
                "How's the new place? Mom said the kitchen is tiny",
                False,
                now - timedelta(days=10, hours=2),
                True,
            ),
            ("Tiny but workable. Already hung shelves and got the desk set up", True, now - timedelta(days=10, hours=1), True),
            (
                "Did you update DMV with the Potrero address yet? "
                "Last year the sticker went to Millbrae and you had to chase it",
                False,
                now - timedelta(days=9, hours=6),
                True,
            ),
            (
                "Updated online last night. Used apt 4B like management said for USPS",
                True,
                now - timedelta(days=9, hours=4),
                True,
            ),
            (
                "Did the smog check yet? AAA on Stevens Creek still does walk-ins",
                False,
                now - timedelta(days=7, hours=12),
                True,
            ),
            ("Not yet, planning Saturday morning around 9", True, now - timedelta(days=7, hours=10), True),
            (
                "Go before 10, lines get long on weekends. "
                "Ask for the printout even if they say it's electronic",
                False,
                now - timedelta(days=7, hours=8),
                True,
            ),
            (
                "After smog passes, renewal is quick on dmv.ca.gov. "
                "Have your odometer reading ready, I think you're around 48k",
                False,
                now - timedelta(days=6, hours=14),
                True,
            ),
            ("Odometer was 48217 when I checked Tuesday", True, now - timedelta(days=6, hours=12), True),
            (
                "Sent you the DMV renewal link. Use the plate number ending in 442. "
                "Insurance card photo is in the glove box if they ask",
                False,
                now - timedelta(days=5, hours=3),
                True,
            ),
            (
                "Got it, will use plate 442. Found the insurance photo in the glove box too",
                True,
                now - timedelta(days=5, hours=1),
                True,
            ),
            (
                "Saturday still the plan for smog? I can meet you for coffee at Philz on 24th after if you want",
                False,
                now - timedelta(days=4, hours=8),
                True,
            ),
            (
                "Still aiming for Saturday 9am at AAA. Coffee after sounds good",
                True,
                now - timedelta(days=4, hours=6),
                True,
            ),
            (
                "Late fee kicks in after the 15th if registration slips. "
                "You know the plate ends in 442 right?",
                False,
                now - timedelta(days=3, hours=5),
                True,
            ),
            ("Yep 442, Civic, odometer 48217. I have it all saved in Notes", True, now - timedelta(days=3, hours=3), True),
            (
                "Work ran long today so smog got pushed to tomorrow morning instead",
                True,
                now - timedelta(days=6),
                True,
            ),
            (
                "No worries. Just text when you're done. "
                "Mom keeps asking if the car stuff is handled before we visit next month",
                False,
                now - timedelta(days=5, hours=6),
                True,
            ),
            (
                "Will take care of registration and smog tomorrow, promise. "
                "Tell Mom I'll send apartment photos too",
                True,
                now - timedelta(days=5),
                True,
            ),
            (
                "Did the smog check yet? Text me when you're done. "
                "Mom is asking again and I told her you're on top of it",
                False,
                now - timedelta(days=3),
                False,
            ),
        ],
    )

    sarah_handle = insert_handle("+15559988777")
    sarah_chat = insert_chat("iMessage;-;+15559988777", "Sarah Kim", "+15559988777")
    insert_messages(
        sarah_chat,
        sarah_handle,
        [
            (
                "Reunion planning: who's in for July 4th weekend?",
                False,
                now - timedelta(days=4, hours=6),
                True,
            ),
            (
                "Count me in! Can bring the photo slideshow",
                True,
                now - timedelta(days=4, hours=5, minutes=40),
                True,
            ),
            (
                "Nice. Looking at Lake Tahoe vs Napa for Airbnb",
                False,
                now - timedelta(days=2, hours=14),
                True,
            ),
            (
                "Venue options in the group doc, leaning toward Tahoe. "
                "Need headcount by Wed for the deposit",
                False,
                now - timedelta(days=1, hours=3),
                False,
            ),
        ],
    )

    amazon_handle = insert_handle("+15550001234")
    amazon_chat = insert_chat("iMessage;-;+15550001234", "Amazon", "+15550001234")
    insert_messages(
        amazon_chat,
        amazon_handle,
        [
            ("Out for delivery: desk lamp (Order #112-8847291)", False, now - timedelta(hours=5), True),
            (
                "Your package was delivered to the front door at 2:14pm. "
                "Photo proof available in the app",
                False,
                now - timedelta(hours=3),
                False,
            ),
        ],
    )

    # --- Group chats ----------------------------------------------------------

    priya_handle = insert_handle("Priya Shah")
    sarah_work_handle = insert_handle("Sarah Kim")
    mike_handle = insert_handle("Mike Torres")
    me_handle = insert_handle("Me")

    work_chat = insert_chat("iMessage;+;chat-work-deck", "Work Group", "chat-work-deck")
    insert_group_messages(
        work_chat,
        [
            ("Q4 planning doc is in Drive if anyone needs it", mike_handle, False, now - timedelta(hours=9), True),
            ("Standup moved to 10:30 today, conflict with all-hands", priya_handle, False, now - timedelta(hours=7), True),
            ("Got it", me_handle, True, now - timedelta(hours=6, minutes=50), True),
            (
                "Can someone review the deck before 3pm? "
                "Client wants fewer bullets on slide 8",
                sarah_work_handle,
                False,
                now - timedelta(hours=3),
                True,
            ),
            ("I can take a look at 2", me_handle, True, now - timedelta(hours=2, minutes=30), True),
            (
                "Thanks! Can you also sanity-check the Q4 revenue slide? "
                "Numbers feel high vs last quarter",
                sarah_work_handle,
                False,
                now - timedelta(minutes=20),
                False,
            ),
        ],
    )

    jess_handle = insert_handle("Jess")
    chris_handle = insert_handle("Chris")
    roommates_chat = insert_chat("iMessage;+;chat-roommates", "Roommates 🏠", "chat-roommates")
    insert_group_messages(
        roommates_chat,
        [
            ("PG&E bill is $187 this month 😬", jess_handle, False, now - timedelta(days=2), True),
            ("Rent is due Friday, Venmo me $950", jess_handle, False, now - timedelta(days=1), True),
            ("Sent mine", me_handle, True, now - timedelta(hours=18), True),
            (
                "Who's taking out trash this week? Recycling pickup is tomorrow AM",
                chris_handle,
                False,
                now - timedelta(hours=5),
                False,
            ),
        ],
    )

    lisa_handle = insert_handle("Lisa Park")
    tom_handle = insert_handle("Tom Nguyen")
    book_club_chat = insert_chat("iMessage;+;chat-book-club", "Book Club", "chat-book-club")
    insert_group_messages(
        book_club_chat,
        [
            ("Loved that one! Rocky is the best", me_handle, True, now - timedelta(days=5), True),
            ("I'm only on chapter 4 no spoilers pls", tom_handle, False, now - timedelta(days=4), True),
            (
                "Discussion Sunday 4pm. Who's hosting? I can bring snacks "
                "but my apartment is chaos",
                tom_handle,
                False,
                now - timedelta(days=3, hours=6),
                False,
            ),
        ],
    )

    conn.commit()
    conn.close()
    print(f"Created {db_path} with 13 conversations")


def bootstrap_databases() -> None:
    """Write the frozen initial snapshot and refresh the runtime working copy."""
    base = Path(__file__).resolve().parent
    initial = base / "initial_chat.db"
    runtime = base / "runtime_chat.db"
    legacy = base / "dummy_chat.db"

    create_dummy_db(str(initial))
    shutil.copy2(initial, runtime)
    shutil.copy2(initial, legacy)
    print(f"Bootstrapped {initial.name} and {runtime.name}")


if __name__ == "__main__":
    bootstrap_databases()
