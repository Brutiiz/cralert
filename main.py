import os
import requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Telegram credentials not set.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    response = requests.post(url, data=data)
    print("Message sent:", response.status_code)

def check_dummy_alert():
    # Это заглушка — вместо неё вставь реальный анализ монет
    send_telegram_message("🔔 Test alert from GitHub Actions!")

if __name__ == "__main__":
    check_dummy_alert()
