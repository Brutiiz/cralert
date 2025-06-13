import requests
import pandas as pd
import numpy as np
from datetime import datetime
import time
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload)
    except:
        pass

def safe_request(url, params=None, retries=3, delay=5):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"[Retry {i+1}] Error: {e}")
            time.sleep(delay)
    return None

def get_top_400_symbols():
    symbols = []
    for page in range(1, 3):  # 250 + 150 = 400
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 250,
            "page": page
        }
        data = safe_request(url, params)
        if not data:
            continue
        symbols.extend([d['id'] for d in data])
    return symbols

def fetch_ohlcv(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/market_chart"
    params = {"vs_currency": "usd", "days": "90", "interval": "daily"}
    data = safe_request(url, params)
    if not data or 'prices' not in data:
        return None
    df = pd.DataFrame(data["prices"], columns=["timestamp", "price"])
    df["price"] = df["price"].astype(float)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    df["sma12"] = df["price"].rolling(12).mean()
    df["lower1"] = df["sma12"] * (1 - 0.1279)
    df["lower2"] = df["sma12"] * (1 - 2 * 0.1279)
    return df

def main():
    matched = []
    symbols = get_top_400_symbols()
    for symbol in symbols:
        df = fetch_ohlcv(symbol)
        if df is None or len(df) < 20:
            continue
        latest_price = df["price"].iloc[-1]
        lower2 = df["lower2"].iloc[-1]
        if latest_price <= lower2:
            matched.append((symbol, round(latest_price, 4), round(lower2, 4)))

    if matched:
        message = "📉 Монеты у нижней границы Lower 2:\n\n"
        for m in matched:
            message += f"{m[0]} — {m[1]} (нижняя линия: {m[2]})\n"
        send_message(message)
    else:
        print("Нет монет у нижней линии.")

if __name__ == "__main__":
    main()
