import os
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from google import genai
from google.genai import types
from db import save_event, list_events, cancel_event, reschedule_event, upcoming_reminders, get_event, find_duplicate, save_turn, recent_turns
from db import add_class_change, upcoming_class_changes, remove_class_change
from routine import COURSES, course_label, classes_on
from db import add_class_change, upcoming_class_changes, remove_class_change
from routine import COURSES, course_label, classes_on




load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-3.5-flash-lite"
TZ = ZoneInfo("Asia/Dhaka")


# ---- Tools: ordinary Python functions the model may ask us to run ----

def _class_on(course, date):
    """Check the course exists and has a regular class that day. Raises a helpful error if not."""
    if course not in COURSES:
        raise ValueError(f"Unknown course code {course!r}. Valid codes: {', '.join(COURSES)}")
    day = datetime.strptime(date, "%Y-%m-%d").date()
    for c in classes_on(day):
        if c[3] == course:
            return day, c
    raise ValueError(f"{course} has no regular class on {date}. That day's classes: {[c[3] for c in classes_on(day)]}")


def tool_cancel_class(course, date):
    day, c = _class_on(course, date)
    change_id = add_class_change(day.isoformat(), course, "cancel")
    return {"status": "cancelled", "change_id": change_id, "class": course_label(course),
            "date": day.isoformat(), "was_at": c[1]}


def tool_move_class(course, date, new_start=None, new_room=None):
    if not new_start and not new_room:
        raise ValueError("Give a new start time, a new room, or both.")
    day, c = _class_on(course, date)
    new_end = None
    if new_start:
        new_start = datetime.strptime(new_start, "%H:%M").strftime("%H:%M")
        length = datetime.strptime(c[2], "%H:%M") - datetime.strptime(c[1], "%H:%M")
        new_end = (datetime.strptime(new_start, "%H:%M") + length).strftime("%H:%M")
    change_id = add_class_change(day.isoformat(), course, "move", new_start, new_end, new_room)
    return {"status": "moved", "change_id": change_id, "class": course_label(course),
            "date": day.isoformat(), "start": new_start or c[1], "end": new_end or c[2],
            "room": new_room or c[4]}


def tool_list_class_changes():
    return {"changes": [
        {"id": i, "date": d, "class": course_label(c), "kind": k,
         "new_start": s, "new_end": e, "new_room": r}
        for i, d, c, k, s, e, r in upcoming_class_changes()
    ]}


def tool_undo_class_change(change_id):
    return {"status": "removed" if remove_class_change(int(change_id)) else "not_found"}



def tool_add_event(title, when, location=None, notes=None):
    when = datetime.fromisoformat(when).strftime("%Y-%m-%dT%H:%M")
    dup = find_duplicate(title, when)
    if dup:
        return {
            "status": "duplicate",
            "event_id": dup[0],
            "note": "An event with this title and time already exists. Nothing was added.",
        }
    scheduled = save_event({"title": title, "when": when, "location": location, "notes": notes})
    result = {"status": "saved", "title": title, "when": when,
              "reminders": [r.strftime("%Y-%m-%d %H:%M") for r in scheduled]}
    if not scheduled:
        result["warning"] = "No reminders were scheduled because the event time is already past or too close. Tell the user."
    return result


def tool_list_events():
    return {"events": [{"id": i, "title": t, "when": w} for i, t, w in list_events()]}


def tool_cancel_event(event_id):
    ok = cancel_event(int(event_id))
    return {"status": "cancelled" if ok else "not_found"}


def tool_reschedule_event(event_id, new_when):
    scheduled = reschedule_event(int(event_id), new_when)
    if scheduled is None:
        return {"status": "not_found"}
    return {"status": "rescheduled", "new_when": new_when,
            "reminders": [r.strftime("%Y-%m-%d %H:%M") for r in scheduled]}


TOOLS = {
    "add_event": tool_add_event,
    "list_events": tool_list_events,
    "cancel_event": tool_cancel_event,
    "reschedule_event": tool_reschedule_event,
    "cancel_class": tool_cancel_class,
    "move_class": tool_move_class,
    "list_class_changes": tool_list_class_changes,
    "undo_class_change": tool_undo_class_change,
}

# ---- The menu the model sees ----

declarations = [
        {
        "name": "cancel_class",
        "description": "Mark one regular class as cancelled on one specific date. For the regular weekly classes only, never for events or quizzes.",
        "parameters": {
            "type": "object",
            "properties": {
                "course": {"type": "string", "description": "Course code exactly as in the course list, e.g. 'CSE 4309'"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["course", "date"],
        },
    },
    {
        "name": "move_class",
        "description": "Reschedule one regular class on one specific date to a new start time and/or a new room. The class keeps its length. For the regular weekly classes only.",
        "parameters": {
            "type": "object",
            "properties": {
                "course": {"type": "string", "description": "Course code exactly as in the course list"},
                "date": {"type": "string", "description": "YYYY-MM-DD, the date of the regular class being moved"},
                "new_start": {"type": "string", "description": "HH:MM, 24-hour"},
                "new_room": {"type": "string"},
            },
            "required": ["course", "date"],
        },
    },
    {
        "name": "list_class_changes",
        "description": "List upcoming class cancellations and reschedules with their ids.",
    },
    {
        "name": "undo_class_change",
        "description": "Remove a class cancellation or reschedule by its id, so the class goes back to normal.",
        "parameters": {
            "type": "object",
            "properties": {"change_id": {"type": "integer"}},
            "required": ["change_id"],
        },
    },
    {
        "name": "add_event",
        "description": "Save a new event, quiz or deadline and schedule reminders. Only call when both the date and the time are known.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "when": {"type": "string", "description": "YYYY-MM-DDTHH:MM, Dhaka time"},
                "location": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["title", "when"],
        },
    },
    {
        "name": "list_events",
        "description": "List upcoming events with their ids.",
    },
    {
        "name": "cancel_event",
        "description": "Delete an event and its reminders, by id.",
        "parameters": {
            "type": "object",
            "properties": {"event_id": {"type": "integer"}},
            "required": ["event_id"],
        },
    },
    {
        "name": "reschedule_event",
        "description": "Move an existing event to a new date/time, by id.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
                "new_when": {"type": "string", "description": "YYYY-MM-DDTHH:MM, Dhaka time"},
            },
            "required": ["event_id", "new_when"],
        },
    },
]


def make_config():
    now = datetime.now(TZ).strftime("%A, %Y-%m-%d %H:%M")
    courses = "; ".join(f"{code} = {title}" for code, title in COURSES.items())
    system = f"""You are a personal reminder assistant for a student in Dhaka.
Current date and time: {now} (Asia/Dhaka).

Rules:
- Convert relative dates into real dates using the current date above.
- Day parts: morning=09:00, afternoon=14:00, evening=18:00, night=21:00. Use these only when a day part is given instead of a time.
- If the date or time is missing or unclear, ask the user. Never guess and never call add_event.
- To cancel or move an event, call list_events first to find its id. If several events could match, ask which one.
- A correction like "actually 4:40" refers to the event we just discussed: reschedule it, do not add a new one.
- After using tools, reply in one or two short sentences saying what you did.
- Only state facts that came from a tool result. If you can't find something out with your tools, say so instead of guessing.
- cancel_event never deletes anything by itself; it only asks the user to confirm. Relay the question ("Cancel <title> on <date>? Reply yes or no") and wait. Cancel only one event at a time.
- The user's regular weekly classes are: {courses}. A cancelled or rescheduled regular class is handled with cancel_class or move_class for one specific date; map a course named by its title to its code. If the date is unclear, ask.
- A makeup or extra class is a normal event: use add_event. If a notice says a class is postponed to another day, cancel the original date with cancel_class and add the new session with add_event.
- cancel_class and move_class only change one date. If the user wants a change for every week, tell them to edit routine.py."""
    return types.GenerateContentConfig(
        system_instruction=system,
        tools=[types.Tool(function_declarations=declarations)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


# ---- Short-term memory: the last few plain-text turns ----
memory = [
    types.Content(role=role, parts=[types.Part(text=text)])
    for role, text in recent_turns()
]

def remember(text, reply):
    memory.append(types.Content(role="user", parts=[types.Part(text=text)]))
    memory.append(types.Content(role="model", parts=[types.Part(text=reply)]))
    del memory[:-24]  # keep RAM small; only the last 12 are used anyway
    save_turn("user", text)
    save_turn("model", reply)


def handle_message(text):
    contents = memory[-12:] + [types.Content(role="user", parts=[types.Part(text=text)])]
    config = make_config()
    reply = None

    for step in range(6):  # safety limit so it can never loop forever
        resp = client.models.generate_content(model=MODEL, contents=contents, config=config)
        calls = resp.function_calls
        if not calls:
            reply = resp.text or "(no reply)"
            break

        contents.append(resp.candidates[0].content)  # keep the model's own turn exactly as it came
        parts = []
        for fc in calls:
            args = dict(fc.args or {})
            print(f"  tool call: {fc.name}({args})")
            try:
                result = TOOLS[fc.name](**args)
            except Exception as e:
                result = {"error": str(e)}  # errors go back to the model, which can retry or explain
            print(f"  result: {result}")
            parts.append(types.Part.from_function_response(name=fc.name, response=result))
        contents.append(types.Content(role="user", parts=parts))

    if reply is None:
        reply = "I got stuck going in circles. Try rephrasing."

    memory.append(types.Content(role="user", parts=[types.Part(text=text)]))
    memory.append(types.Content(role="model", parts=[types.Part(text=reply)]))
    return reply


if __name__ == "__main__":
    print("Terminal test mode. Ctrl+C to quit.")
    while True:
        print(handle_message(input("you> ")))