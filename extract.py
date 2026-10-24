import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = "gemini-3.5-flash-lite"
TZ = ZoneInfo("Asia/Dhaka")


def extract_event(message):
    now = datetime.now(TZ).strftime("%A, %Y-%m-%d %H:%M")
    prompt = f"""The current date and time in Dhaka is: {now}.

Extract the event from the message below. Reply with ONLY a JSON object:
{{"title": string, "when": "YYYY-MM-DDTHH:MM" or null, "location": string or null, "notes": string or null}}

Rules:
- Convert relative dates ("Thursday", "tomorrow") into real dates using the current date above.
- If the date or the time is missing or unclear, set "when" to null. Never guess.

Message: {message}"""

    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    return json.loads(resp.text)


if __name__ == "__main__":
    tests = [
        "Psychology makeup quiz:\nR-205 10AM Thursday\nSyllabus: Motivation & Personality",
        "dsa quiz, wednesday 2pm",
        "math assignment due sometime next week",
    ]
    for t in tests:
        print("IN: ", t)
        print("OUT:", extract_event(t))
        print()