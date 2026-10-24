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
]


def save_event(ev):
    event_time = datetime.fromisoformat(ev["when"])
    now = datetime.now(TZ).replace(tzinfo=None)

    cur = db.execute(
        "INSERT INTO events(title, when_at, location, notes) VALUES (?, ?, ?, ?)",
        (ev["title"], ev["when"], ev["location"], ev["notes"]),
    )
    event_id = cur.lastrowid

    scheduled = []
    for label, delta in OFFSETS:
        remind_at = event_time - delta
        if remind_at <= now:
            continue  # that moment has already passed
        text = f"⏰ In {label}: {ev['title']}"
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
    now = datetime.now(TZ).strftime("%Y-%m-%dT%H:%M")
    return db.execute(
        """SELECT r.id, r.text
           FROM reminders r JOIN events e ON e.id = r.event_id
           WHERE r.sent = 0 AND r.remind_at <= ? AND e.when_at > ?""",
        (now, now),
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