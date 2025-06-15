import requests
import pandas as pd
import numpy as np
import json
import time
import os
from datetime import datetime

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

def get_binance_data(symbol, interval='1d', limit=1000):
    url = f'https://api.binance.com/api/v1/klines'
    params = {
        'symbol': symbol,  # Например 'BTCUSDT'
        'interval': interval,  # интервал, например '1d' (1 день)
        'limit': limit  # максимум 1000 записей
    }

    print(f"Запрос для {symbol}: {url}, параметры: {params}")  # Логируем запрос
    response = requests.get(url, params=params)
    print(f"Ответ от API для {symbol}: {response.status_code}")  # Логируем статус ответа

    if response.status_code != 200:
        print(f"Ошибка при запросе для {symbol}: {response.status_code}")
        return None

    data = response.json()
    print(f"Ответ API для {symbol}: {data}")  # Логируем данные ответа

    if not data:
        print(f"Нет данных для монеты {symbol}")
        return None
    
    # Преобразуем данные в DataFrame для дальнейшего анализа
    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "close_time", "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df[['timestamp', 'close']]
    df['close'] = pd.to_numeric(df['close'])

    print(f"Получены данные для {symbol}: {len(df)} строк.")  # Логируем количество полученных строк
    return df


# Анализ монет
def analyze_symbols(symbols, state):
    today = str(datetime.utcnow().date())
    matched, near = [], []

    print(f"Всего монет для анализа: {len(symbols)}")
    
    for symbol in symbols:
        print(f"Обрабатывается монета: {symbol}")
        
        # Получаем данные для монеты
        df = get_binance_data(symbol)
        if df is None or len(df) < 12:
            print(f"Нет данных или недостаточно данных для монеты {symbol}")
            continue
        
        # Расчет 12-дневной SMA
        df["sma12"] = df["close"].rolling(12).mean()  # Расчет 12-дневной SMA
        df["lower2"] = df["sma12"] * (1 - 0.2558)  # Ожидаемое снижение на 25.58%
        
        price = df["close"].iloc[-1]
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
    
    # Получаем список монет (для примера: BTC, ETH, BNB и т.д.)
    symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT']  # Пример монет
    analyze_symbols(symbols, state)

if __name__ == "__main__":
    main()
