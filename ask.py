import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

MODEL = "gemini-3.5-flash-lite"   # e.g. a name from list_models.py, with or without "models/"

resp = client.models.generate_content(
    model=MODEL,
    contents="Repeat after me, FUCK WITH YOUR BUTT",
)
print(resp.text)