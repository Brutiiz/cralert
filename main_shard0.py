import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import time
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
STATE_FILE = "alert_state.json"  # Для хранения состояния уведомлений

# Уведомление в Telegram
def send_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Ошибка отправки сообщения: {e}")

# Загрузка состояния уведомлений
def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

# Сохранение состояния уведомлений
def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# Выполнение безопасного запроса с повторными попытками
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

# Получение данных о монетах (топ-400)
def get_top_400_coins():
    symbols = []
    total_pages = 4  # Всего 4 страницы, по 100 монет на странице

    # Загружаем монеты с 4 страниц
    for page in range(1, total_pages + 1):
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 100,  # 100 монет на странице
            "page": page
        }
        data = safe_request(url, params)
        if not data:
            continue
        symbols.extend([d['id'] for d in data])

    # Логируем общее количество монет
    print(f"Загружено {len(symbols)} монет")

    return symbols


def fetch_ohlcv(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/market_chart"
    params = {"vs_currency": "usd", "days": "90", "interval": "daily"}
    
    # Выполняем запрос и проверяем ответ
    data = safe_request(url, params)

    # Логируем весь ответ от API, чтобы понять что приходит
    if data:
        print(f"Ответ API для {symbol}: {data}")
    
    if not data or 'prices' not in data:
        print(f"Ошибка: Нет данных о ценах для монеты {symbol}")  # Логируем, если нет цен
        return None

    df = pd.DataFrame(data["prices"], columns=["timestamp", "price"])
    df["price"] = df["price"].astype(float)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)

    if len(df) < 12:
        print(f"Недостаточно данных для монеты {symbol} (менее 12 точек данных)")  # Логируем, если данных недостаточно
        return None
    
    df["sma12"] = df["price"].rolling(12).mean()  # Расчет 12-дневной SMA
    df["lower2"] = df["sma12"] * (1 - 0.2558)  # Ожидаемое снижение на 25.58%
    return df



# Анализ монет
def analyze_symbols(symbols, state):
    today = str(datetime.utcnow().date())
    matched, near = [], []

    # Логируем количество монет, которые анализируются
    print(f"Всего монет для анализа: {len(symbols)}")
    
    for symbol in symbols:
        print(f"Обрабатывается монета: {symbol}")  # Логируем каждую обрабатываемую монету
        
        df = fetch_ohlcv(symbol)
        if df is None or len(df) < 12:
            print(f"Нет данных или недостаточно данных для монеты {symbol}")  # Логируем, если нет данных
            continue

        price = df["price"].iloc[-1]
        lower2 = df["lower2"].iloc[-1]
        diff_percent = (price - lower2) / lower2 * 100
        print(f"{symbol} цена: {price:.2f} | Lower2: {lower2:.2f} | Δ: {diff_percent:.2f}%")

        # Если монета уже получила уведомление сегодня, пропускаем
        if state.get(symbol) == today:
            continue

        # Уведомление о достижении уровня
        if price <= lower2:
            matched.append(symbol)
            state[symbol] = today  # Обновляем состояние
        # Уведомление о приближении
        elif 0 < diff_percent <= 3:  # Например, от -22.58% до -25.58% = приближение
            near.append(symbol)

    save_state(state)

    # Логируем, сколько монет были обработаны
    print(f"Обработано {len(matched)} монет с достижением уровня")
    print(f"Обработано {len(near)} монет, которые почти достигли уровня")

    # Отправляем уведомления
    if matched:
        msg = "📉 Монеты КАСНУЛИСЬ Lower 2:\n" + "\n".join(matched)
        send_message(msg)
    if near:
        msg = "📡 Почти дошли до Lower 2:\n" + "\n".join(near)
        send_message(msg)


def main():
    state = load_state()
    symbols = get_top_400_coins()  # Получаем список топ-400 монет
    analyze_symbols(symbols, state)

if __name__ == "__main__":
    main()
