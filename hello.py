import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.environ["TELEGRAM_TOKEN"]
chat_id = os.environ["TELEGRAM_CHAT_ID"]

r = requests.post(
    f"https://api.telegram.org/bot{token}/sendMessage",
    json={"chat_id": chat_id, "text": "Hello from my agent 👋"},
    timeout=10,
)
print(r.status_code, r.text)