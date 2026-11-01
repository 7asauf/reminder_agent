import os
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from google import genai
from google.genai import types
from db import save_event, list_events, cancel_event, reschedule_event
from db import find_duplicate

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-3.5-flash-lite"
TZ = ZoneInfo("Asia/Dhaka")


# ---- Tools: ordinary Python functions the model may ask us to run ----

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
}

# ---- The menu the model sees ----

declarations = [
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
    system = f"""You are a personal reminder assistant for a student in Dhaka.
Current date and time: {now} (Asia/Dhaka).

Rules:
- Convert relative dates into real dates using the current date above.
- Day parts: morning=09:00, afternoon=14:00, evening=18:00, night=21:00. Use these only when a day part is given instead of a time.
- If the date or time is missing or unclear, ask the user. Never guess and never call add_event.
- To cancel or move an event, call list_events first to find its id. If several events could match, ask which one.
- A correction like "actually 4:40" refers to the event we just discussed: reschedule it, do not add a new one.
- After using tools, reply in one or two short sentences saying what you did."""
    return types.GenerateContentConfig(
        system_instruction=system,
        tools=[types.Tool(function_declarations=declarations)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


# ---- Short-term memory: the last few plain-text turns ----
memory = []


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