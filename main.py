import os
import requests
import pandas as pd
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

LOWER_MULTIPLIER = 0.1279  # 12.79%
SMA_PERIOD = 12
ALERTED_COINS = set()

def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("❌ Telegram credentials not set.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=data)
        print("✅ Telegram response:", response.status_code)
    except Exception as e:
        print("❌ Error sending message:", e)

def get_top_400_symbols():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 250, "page": 1}
    response = requests.get(url, params=params)
    coins = response.json()
    params["page"] = 2
    response2 = requests.get(url, params=params)
    coins += response2.json()
    return [coin["id"] for coin in coins]

def get_ohlc_data(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": SMA_PERIOD + 5, "interval": "daily"}
    response = requests.get(url, params=params)
    data = response.json()
    prices = data.get("prices", [])
    if len(prices) < SMA_PERIOD:
        return None
    df = pd.DataFrame(prices, columns=["timestamp", "price"])
    df["price"] = df["price"].astype(float)
    df["sma"] = df["price"].rolling(window=SMA_PERIOD).mean()
    df["lower_2"] = df["sma"] * (1 - 2 * LOWER_MULTIPLIER)
    return df

def check_lower_touch(coin_id):
    df = get_ohlc_data(coin_id)
    if df is None or df.empty:
        return
    latest = df.iloc[-1]
    price = latest["price"]
    lower_2 = latest["lower_2"]
    if price <= lower_2 and coin_id not in ALERTED_COINS:
        ALERTED_COINS.add(coin_id)
        send_telegram_message(
            f"📉 <b>{coin_id.upper()}</b> на <b>1D</b> коснулась нижней линии <b>Lower 2</b>\n"
            f"Цена: <code>{price:.5f}</code>\n"
            f"Lower 2: <code>{lower_2:.5f}</code>\n"
            f"Дата: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC"
        )

def main():
    print("🚀 Запускаю анализ топ-400 монет...")
    coins = get_top_400_symbols()
    for coin_id in coins:
        try:
            check_lower_touch(coin_id)
        except Exception as e:
            print(f"⚠️ Ошибка с {coin_id}: {e}")

if __name__ == "__main__":
    main()
