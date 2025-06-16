import requests
import pandas as pd
import json
import time
import os
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
STATE_FILE = "alert_state.json"  # Для хранения состояния уведомлений
API_KEY = os.getenv("CRYPTOCOMPARE_API_KEY")  # Ваш API-ключ для CryptoCompare

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

# Получение топ-400 монет с CryptoCompare
def get_top_400(api_key):
    url = "https://min-api.cryptocompare.com/data/top/totalvolumes"
    params = {
        'limit': 400,  # Получаем топ 400 монет
        'tsym': 'USD',  # По капитализации в долларах
        'api_key': api_key
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        # Логирование содержимого ответа API
        print(f"Ответ от API: {json.dumps(data, indent=2)}")

        if "Data" in data:
            symbols = [coin['CoinInfo']['Name'] for coin in data['Data']]
            print(f"Полученные монеты: {symbols}")
            return symbols
        else:
            print("Ошибка: Не удается найти 'Data' в ответе.")
            return []
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе для топ-400: {e}")
        return []

# Получение данных с CryptoCompare для анализа
def get_cryptocompare_data(symbol, api_key, currency="USD", limit=2000):
    url = "https://min-api.cryptocompare.com/data/v2/histoday"
    params = {
        'fsym': symbol,  # Символ криптовалюты (например, 'BTC')
        'tsym': currency,  # Валюта для конвертации (например, 'USD')
        'limit': limit,  # Максимальное количество записей
        'api_key': api_key  # Ваш API-ключ
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if data['Response'] == 'Error':
            print(f"Ошибка: {data['Message']}")
            return None

        # Преобразуем данные в DataFrame для дальнейшего анализа
        prices = []
        for item in data['Data']['Data']:
            prices.append({
                'timestamp': pd.to_datetime(item['time'], unit='s'),
                'close': item['close']
            })

        df = pd.DataFrame(prices)
        return df

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
        
        # Получаем данные для монеты с CryptoCompare
        df = get_cryptocompare_data(symbol, api_key)
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
    
    # Получаем список топ-400 монет
    symbols = get_top_400(API_KEY)  # Получаем топ 400 монет по капитализации
    if symbols:
        analyze_symbols(symbols, state, API_KEY)  # Анализируем монеты

if __name__ == "__main__":
    main()
