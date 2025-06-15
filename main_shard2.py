import requests
import pandas as pd
import numpy as np
from datetime import datetime
import time
import os
import json

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STATE_FILE = "alert_state.json"

def send_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload)
    except:
        pass

def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

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

def get_symbols_shard(shard_index):
    symbols = []
    total_pages = 4  # Всего 4 страницы, по 100 монет на странице

    for page in range(1, total_pages + 1):
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 100,
            "page": page
        }
        data = safe_request(url, params)
        if not data:
            continue
        symbols.extend([d['id'] for d in data])

    # Для shard2 обрабатываются монеты с 200 по 299
    start = 200
    end = 300
    return symbols[start:end]




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
    df["lower2"] = df["sma12"] * (1 - 2 * 0.1279)
    return df

def main():
    shard_index = 0
    symbols = get_symbols_shard(shard_index)
    state = load_state()
    today = str(datetime.utcnow().date())
    matched, near = [], []

    for symbol in symbols:
        df = fetch_ohlcv(symbol)
        if df is None or len(df) < 12:
            continue
        price = df["price"].iloc[-1]
        lower2 = df["lower2"].iloc[-1]
        if pd.isna(lower2):
            continue
        diff_percent = (price - lower2) / lower2 * 100
        print(f"{symbol:<15} цена: {price:.4f} | Lower2: {lower2:.4f} | Δ: {diff_percent:.2f}%")

        if state.get(symbol) == today:
            continue  # уже был сигнал сегодня

        if price <= lower2:
            matched.append(symbol)
            state[symbol] = today
        elif 0 < diff_percent <= 3:
            near.append(symbol)

    save_state(state)

    if matched:
        msg = "📉 Монеты КАСНУЛИСЬ Lower 2 (шард 0):\n" + "\n".join(matched)
        send_message(msg)
    if near:
        msg = "📡 Почти дошли до Lower 2 (шард 0):\n" + "\n".join(near)
        send_message(msg)

if __name__ == "__main__":
    main()
