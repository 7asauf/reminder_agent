from datetime import datetime, timedelta
from db import TZ, events_on, get_state, set_state


def build_briefing():
    today = datetime.now(TZ).date()
    tomorrow = today + timedelta(days=1)
    lines = [f"☀️ Good morning! {today.strftime('%A, %d %B')}", ""]
    for label, day in (("Today", today), ("Tomorrow", tomorrow)):
        lines.append(f"{label}:")
        events = events_on(day.isoformat())
        if not events:
            lines.append("• nothing scheduled")
        for _id, title, when_at, location in events:
            time_text = datetime.fromisoformat(when_at).strftime("%H:%M")
            line = f"• {time_text}  {title}"
            if location:
                line += f" @ {location}"
            lines.append(line)
        lines.append("")
    return "\n".join(lines).strip()


def briefing_due(first_hour=8, last_hour=20):
    now = datetime.now(TZ)
    already_sent = get_state("last_briefing") == now.date().isoformat()
    return first_hour <= now.hour <= last_hour and not already_sent


def mark_briefing_done():
    set_state("last_briefing", datetime.now(TZ).date().isoformat())