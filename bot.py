import os
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from db import due_reminders, mark_sent, list_events, cancel_event
from agent import handle_message
from briefing import build_briefing, briefing_due, mark_briefing_done
from db import TZ, due_reminders, mark_sent, list_events, cancel_event, get_state, set_state
from routine import due_class_alerts, classes_on, format_class
from db import upcoming_class_changes, remove_class_change
from routine import schedule_for, course_label



load_dotenv()
TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
API = f"https://api.telegram.org/bot{TOKEN}"


def send(text):
    try:
        r = requests.post(
            f"{API}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text},
            timeout=10,
        )
        return r.ok
    except requests.RequestException as e:
        print("send failed:", e)
        return False


fail_since = None


fail_since = None


def get_updates(offset):
    global fail_since
    try:
        r = requests.get(
            f"{API}/getUpdates",
            params={"offset": offset, "timeout": 5},
            timeout=20,
        )
        try:
            data = r.json()
        except ValueError:
            raise RuntimeError(f"HTTP {r.status_code}, non-JSON reply: {r.text[:80]!r}")
        if not data.get("ok"):
            raise RuntimeError(f"HTTP {r.status_code}: {data.get('description')}")
        if fail_since is not None:
            secs = int(time.time() - fail_since)
            print(f"{datetime.now():%H:%M:%S} telegram reachable again after {secs}s")
            fail_since = None
        return data["result"]
    except (requests.RequestException, RuntimeError) as e:
        if fail_since is None:
            fail_since = time.time()
        print(f"{datetime.now():%H:%M:%S} getUpdates failed: {type(e).__name__}: {e}")
        time.sleep(5)
        return []


print("Bot running. Press Ctrl+C to stop.")
offset = None
while True:
    for update in get_updates(offset):
        offset = update["update_id"] + 1
        msg = update.get("message")
        if not msg or msg["chat"]["id"] != CHAT_ID:
            continue
        text = msg.get("text", "")
        if not text:
            continue
        print("got:", text)

        if text.startswith("/list"):
            rows = list_events()
            if not rows:
                send("Nothing upcoming.")
            else:
                send("\n".join(
                    f"#{i}  {datetime.fromisoformat(w).strftime('%a %d %b, %H:%M')}  {t}"
                    for i, t, w in rows
                ))
            continue

        if text.startswith("/cancel"):
            parts = text.split()
            if len(parts) == 2 and parts[1].isdigit():
                send("Cancelled." if cancel_event(int(parts[1])) else "No event with that id.")
            else:
                send("Usage: /cancel <id>")
            continue

        if text.startswith("/today"):
            send(build_briefing())
            continue

        if text.startswith("/classes"):
            todays = classes_on(datetime.now(TZ).date())
            send("\n".join("• " + format_class(c) for c in todays) or "No classes today.")
            continue
        if text.startswith("/changes"):
            rows = upcoming_class_changes()
            if not rows:
                send("No class changes.")
            else:
                send("\n".join(
                    f"#{i}  {d}  {course_label(c)}  "
                    + ("cancelled" if k == "cancel" else f"moved: {s or 'same time'}" + (f", {r}" if r else ""))
                    for i, d, c, k, s, e, r in rows
                ))
            continue

        if text.startswith("/undo"):
            parts = text.split()
            if len(parts) == 2 and parts[1].isdigit():
                send("Removed." if remove_class_change(int(parts[1])) else "No change with that id.")
            else:
                send("Usage: /undo <id>")
            continue


        if text.startswith("/"):
            send("Unknown command. I know /list, /today and /cancel <id>.")
            continue

        try:
            send(handle_message(text))
        except Exception as e:
            print("agent failed:", e)
            send("Sorry, the AI call failed. Try again in a minute.")


    for key, message in due_class_alerts(datetime.now(TZ)):
        if get_state(key) is None and send(message):
            set_state(key, "sent")

    for rid, reminder_text in due_reminders():
        if send(reminder_text):
            mark_sent(rid)

    if briefing_due():
        if send(build_briefing()):
            mark_briefing_done()