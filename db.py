import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Dhaka")
db = sqlite3.connect("agent.db")

db.execute("""CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY,
    title TEXT, when_at TEXT, location TEXT, notes TEXT)""")
db.execute("""CREATE TABLE IF NOT EXISTS reminders(
    id INTEGER PRIMARY KEY,
    event_id INTEGER, remind_at TEXT, text TEXT, sent INTEGER DEFAULT 0)""")
db.commit()

OFFSETS = [
    ("1 day", timedelta(days=1)),
    ("2 hours", timedelta(hours=2)),
    ("30 minutes", timedelta(minutes=30)),
    ("now", timedelta(0)),
]


def save_event(ev):
    event_time = datetime.fromisoformat(ev["when"])
    when_s = event_time.strftime("%Y-%m-%dT%H:%M")
    now = datetime.now(TZ).replace(tzinfo=None)

    cur = db.execute(
        "INSERT INTO events(title, when_at, location, notes) VALUES (?, ?, ?, ?)",
        (ev["title"], when_s, ev["location"], ev["notes"]),
    )
    event_id = cur.lastrowid

    scheduled = []
    for label, delta in OFFSETS:
        remind_at = event_time - delta
        if remind_at <= now:
            continue  # that moment has already passed
        prefix = "Now" if label == "now" else f"In {label}"
        text = f"⏰ {prefix}: {ev['title']}"
        if ev["location"]:
            text += f" @ {ev['location']}"
        if ev["notes"]:
            text += f"\n{ev['notes']}"
        db.execute(
            "INSERT INTO reminders(event_id, remind_at, text) VALUES (?, ?, ?)",
            (event_id, remind_at.strftime("%Y-%m-%dT%H:%M"), text),
        )
        scheduled.append(remind_at)
    db.commit()
    return scheduled


def due_reminders():
    now = datetime.now(TZ)
    now_s = now.strftime("%Y-%m-%dT%H:%M")
    cutoff = (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M")
    return db.execute(
        """SELECT r.id, r.text
           FROM reminders r JOIN events e ON e.id = r.event_id
           WHERE r.sent = 0 AND r.remind_at <= ?
             AND (e.when_at > ? OR (r.remind_at = e.when_at AND e.when_at > ?))""",
        (now_s, now_s, cutoff),
    ).fetchall()

def mark_sent(reminder_id):
    db.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
    db.commit()


def list_events():
    now = datetime.now(TZ).strftime("%Y-%m-%dT%H:%M")
    return db.execute(
        "SELECT id, title, when_at FROM events WHERE when_at > ? ORDER BY when_at",
        (now,),
    ).fetchall()


def cancel_event(event_id):
    db.execute("DELETE FROM reminders WHERE event_id = ?", (event_id,))
    cur = db.execute("DELETE FROM events WHERE id = ?", (event_id,))
    db.commit()
    return cur.rowcount > 0


def reschedule_event(event_id, new_when):
    datetime.fromisoformat(new_when)  # raises an error early if the format is bad
    row = db.execute(
        "SELECT title, location, notes FROM events WHERE id = ?", (event_id,)
    ).fetchone()
    if row is None:
        return None
    cancel_event(event_id)
    title, location, notes = row
    return save_event({"title": title, "when": new_when, "location": location, "notes": notes})



db.execute("CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT)")
db.commit()


def get_state(key):
    row = db.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_state(key, value):
    db.execute(
        "INSERT INTO state(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    db.commit()


def events_on(day):
    # day looks like "2026-11-02"
    return db.execute(
        "SELECT id, title, when_at, location FROM events "
        "WHERE substr(when_at, 1, 10) = ? ORDER BY when_at",
        (day,),
    ).fetchall()


def find_duplicate(title, when):
    return db.execute(
        "SELECT id FROM events WHERE when_at = ? AND lower(title) = lower(?)",
        (when, title.strip()),
    ).fetchone()

db.execute("CREATE TABLE IF NOT EXISTS chat(id INTEGER PRIMARY KEY, role TEXT, text TEXT, at TEXT)")
db.commit()


def save_turn(role, text):
    db.execute(
        "INSERT INTO chat(role, text, at) VALUES (?, ?, ?)",
        (role, text, datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S")),
    )
    db.execute("DELETE FROM chat WHERE id NOT IN (SELECT id FROM chat ORDER BY id DESC LIMIT 200)")
    db.commit()


def recent_turns(n=12, hours=6):
    cutoff = (datetime.now(TZ) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
    rows = db.execute(
        "SELECT role, text FROM chat WHERE at >= ? ORDER BY id DESC LIMIT ?",
        (cutoff, n),
    ).fetchall()
    rows.reverse()  # oldest first
    while rows and rows[0][0] != "user":
        rows.pop(0)  # the model needs the history to start with a user turn
    return rows


def upcoming_reminders():
    now = datetime.now(TZ).strftime("%Y-%m-%dT%H:%M")
    return db.execute(
        """SELECT e.id, e.title, r.remind_at
           FROM reminders r JOIN events e ON e.id = r.event_id
           WHERE r.sent = 0 AND r.remind_at >= ?
           ORDER BY r.remind_at""",
        (now,),
    ).fetchall()


def get_event(event_id):
    return db.execute(
        "SELECT title, when_at FROM events WHERE id = ?", (event_id,)
    ).fetchone()


db.execute("""CREATE TABLE IF NOT EXISTS class_changes(
    id INTEGER PRIMARY KEY,
    day TEXT, course TEXT, kind TEXT,
    new_start TEXT, new_end TEXT, new_room TEXT)""")
db.commit()


def add_class_change(day, course, kind, new_start=None, new_end=None, new_room=None):
    # a newer change for the same class on the same day replaces the older one
    db.execute("DELETE FROM class_changes WHERE day = ? AND course = ?", (day, course))
    cur = db.execute(
        "INSERT INTO class_changes(day, course, kind, new_start, new_end, new_room) VALUES (?, ?, ?, ?, ?, ?)",
        (day, course, kind, new_start, new_end, new_room),
    )
    db.commit()
    return cur.lastrowid


def changes_on(day):
    return db.execute(
        "SELECT id, course, kind, new_start, new_end, new_room FROM class_changes WHERE day = ?",
        (day,),
    ).fetchall()


def upcoming_class_changes():
    today = datetime.now(TZ).date().isoformat()
    return db.execute(
        "SELECT id, day, course, kind, new_start, new_end, new_room "
        "FROM class_changes WHERE day >= ? ORDER BY day, id",
        (today,),
    ).fetchall()


def remove_class_change(change_id):
    cur = db.execute("DELETE FROM class_changes WHERE id = ?", (change_id,))
    db.commit()
    return cur.rowcount > 0