import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.environ["TELEGRAM_TOKEN"]

r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10)
for update in r.json()["result"]:
    print(update["message"]["chat"]["id"], update["message"]["text"])