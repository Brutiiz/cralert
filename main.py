import os
import requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ Telegram credentials not set.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, data=data)
        print("✅ Telegram response:", response.status_code)
        print("➡️ Message text:", message)
        print("📨 Telegram says:", response.text)
    except Exception as e:
        print("❌ Error sending message:", e)

if __name__ == "__main__":
    send_telegram_message("🔔 <b>Test alert</b> from GitHub Actions every 10 minutes!")
