import requests
import pandas as pd
import json
import time
import os
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
STATE_FILE = "alert_state.json"  # Для хранения состояния уведомлений
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")  # Ваш API-ключ для Bybit
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")  # Ваш API-ключ Secret для Bybit

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

# Получение исторических данных с Bybit
def get_bybit_data(symbol, api_key, interval='1', limit=1000):
    url = "https://api.bybit.com/public/linear/kline"
    params = {
        'symbol': symbol,  # Например 'BTCUSDT'
        'interval': interval,  # интервал, например '1' (1 минута)
        'limit': limit,  # максимум 1000 записей
        'api_key': api_key  # Ваш API-ключ
    }

    try:
        response = requests.get(url, params=params)
        # Логируем все ответы
        print(f"Ответ от Bybit: {response.status_code}, {response.text}")
        
        # Проверяем статус ответа
        response.raise_for_status()
        data = response.json()

        if 'result' in data:
            return data['result']
        else:
            print(f"Ошибка при запросе для {symbol}: {data}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе для {symbol}: {e}")
        return None

# Анализ монет
def analyze_symbols(symbols, state, api_key):
    today = str(datetime.utcnow().date())
    matched, near = [], []

    print(f"Всего монет для анализа: {len(symbols)}")
    
    for symbol in symbols:
        print(f"Обрабатывается монета: {symbol}")
        
        # Получаем данные для монеты с Bybit
        data = get_bybit_data(symbol, api_key)
        if not data or len(data) < 12:
            print(f"Нет данных или недостаточно данных для монеты {symbol}")
            continue
        
        # Преобразуем данные в DataFrame
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        df.set_index('timestamp', inplace=True)
        df['close'] = pd.to_numeric(df['close'])
        
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
        # Уведомление о приближении (почти достигли уровня)
        elif 0 < diff_percent <= 3:  # Например, от -22.58% до -25.58% = приближение
            near.append(symbol)

    save_state(state)

    print(f"Обработано {len(matched)} монет с до
