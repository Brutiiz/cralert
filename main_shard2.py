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
    symbols_per_shard = 100  # Каждый шард получает 100 монет

    # Рассчитываем, с какой страницы нужно начать для каждого шардового скрипта
    start_page = shard_index + 1  # Если shard_index == 0, то начинаем с первой страницы
    end_page = start_page + 1     # Переходим к следующей странице

    for page in range(start_page, end_page):
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": symbols_per_shard,  # 100 монет на странице
            "page": page
        }
        data = safe_request(url, params)
        if not data:
            continue

        # Логирование количества монет на текущей странице
        print(f"Страница {page}, количество монет: {len(data)}")
        
        symbols.extend([d['id'] for d in data])

    # Логируем, сколько монет загружено
    print(f"Загружено {len(symbols)} монет на шард {shard_index}")
    
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
    df["lower2"] = df["sma12"] * (1 - 2 * 0.1279)
    return df


def analyze_symbols(symbols):
    print(f"Всего монет для анализа: {len(symbols)}")
    for symbol in symbols:
        print(f"Обрабатывается монета: {symbol}")
        
        df = fetch_ohlcv(symbol)
        if df is None or len(df) < 12:
            print(f"Нет данных или недостаточно данных для монеты {symbol}")
            continue
        price = df["price"].iloc[-1]
        lower2 = df["lower2"].iloc[-1]
        
        print(f"{symbol} цена: {price} | Lower2: {lower2} | Δ: {(price - lower2) / lower2 * 100:.2f}%")
        
        if price <= lower2:
            print(f"Уведомление: Монета {symbol} достигла Lower2!")
        else:
            print(f"Монета {symbol} не достигла Lower2 (цена: {price}, Lower2: {lower2})")

def main():
    shard_index = 0
    symbols = get_symbols_shard(shard_index)
    print(f"Количество монет в symbols: {len(symbols)}")  # Логируем количество монет
    print(f"Монеты: {symbols}")  # Логируем все монеты
    analyze_symbols(symbols)  # Анализируем монеты

if __name__ == "__main__":
    main()
