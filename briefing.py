from datetime import datetime, timedelta
from db import TZ, events_on, get_state, set_state
from routine import classes_on, format_class
from routine import schedule_for, cancelled_on, format_class, course_label


def build_briefing():
    today = datetime.now(TZ).date()
    tomorrow = today + timedelta(days=1)
    lines = [f"☀️ Good morning! {today.strftime('%A, %d %B')}", ""]

    lines.append("Classes today:")
    todays = schedule_for(today)
    if not todays:
        lines.append("• no classes")
    for c in todays:
        lines.append("• " + format_class(c))
    for course in cancelled_on(today):
        lines.append(f"❌ cancelled: {course_label(course)}")
    lines.append("")

    for label, day in (("Events today", today), ("Events tomorrow", tomorrow)):
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

    first = schedule_for(tomorrow)
    if first:
        lines.append(f"Tomorrow starts at {first[0][1]}: {course_label(first[0][3])}, {first[0][4]}.")
    return "\n".join(lines).strip()



def briefing_due(first_hour=8, last_hour=20):
    now = datetime.now(TZ)
    already_sent = get_state("last_briefing") == now.date().isoformat()
    return first_hour <= now.hour <= last_hour and not already_sent


def mark_briefing_done():
    set_state("last_briefing", datetime.now(TZ).date().isoformat())