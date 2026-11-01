import os
import requests
from datetime import datetime
from dotenv import load_dotenv
from db import due_reminders, mark_sent, list_events, cancel_event
from agent import handle_message
from briefing import build_briefing, briefing_due, mark_briefing_done

load_dotenv()
TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
API = f"https://api.telegram.org/bot{TOKEN}"


def send(text):
    requests.post(f"{API}/sendMessage", json={"chat_id": CHAT_ID, "text": text}, timeout=10)


def get_updates(offset):
    r = requests.get(
        f"{API}/getUpdates",
        params={"offset": offset, "timeout": 5},
        timeout=15,
    )
    return r.json()["result"]


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

        if text.startswith("/"):
            send("Unknown command. I know /list and /cancel <id>.")
            continue

        try:
            send(handle_message(text))
        except Exception as e:
            print("agent failed:", e)
            send("Sorry, the AI call failed. Try again in a minute.")




    for rid, reminder_text in due_reminders():
        send(reminder_text)
        mark_sent(rid)

    if briefing_due():
        send(build_briefing())
        mark_briefing_done()