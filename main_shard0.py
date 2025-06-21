import requests
import pandas as pd
from time import sleep
import hashlib
import time
import json

# Ваши данные для авторизации
API_KEY = "your_api_key"
API_SECRET = "your_api_secret"

# Генерация подписи для запроса с использованием вашего API ключа и секрета
def generate_signature(api_key, api_secret, params):
    query_string = '&'.join([f"{key}={value}" for key, value in sorted(params.items())])
    signature = hashlib.sha256((query_string + f"&api_secret={api_secret}").encode('utf-8')).hexdigest()
    return signature

# Получение данных для монеты с Bybit с авторизацией
def get_coin_data(symbol):
    url = "https://api.bybit.com/v2/public/kline/list"

    params = {
        "api_key": API_KEY,
        "symbol": f"{symbol}USDT",  # Символ монеты
        "interval": "1d",  # Интервал 1 день
        "limit": 30,  # Данные за последние 30 дней
        "timestamp": int(time.time() * 1000)  # Текущее время в миллисекундах
    }

    # Генерация подписи
    params['sign'] = generate_signature(API_KEY, API_SECRET, params)

    # Отправка запроса
    response = requests.get(url, params=params)
    
    if response.status_code != 200:
        print(f"Ошибка при запросе: {response.status_code} - {response.text}")
        return None

    data = response.json()
    
    # Проверка на наличие данных в ответе
    if "result" not in data:
        print("Ошибка: Не получены данные о свечах.")
        return None

    # Преобразование данных в DataFrame
    df = pd.DataFrame(data['result'])
    
    # Преобразование временной метки в читаемый формат
    df['timestamp'] = pd.to_datetime(df['open_time'], unit='s')
    df.set_index('timestamp', inplace=True)

    # Оставляем только нужные столбцы
    df = df[['open', 'high', 'low', 'close', 'volume']]

    return df

# Функция для получения данных и обработки монет
def analyze_symbols(symbols):
    for symbol in symbols:
        print(f"Обрабатывается монета: {symbol}")

        # Получаем данные для монеты с Bybit
        df = get_coin_data(symbol)
        if df is None:
            continue

        # Пример вывода последних данных о свечах
        print(f"Последние данные для {symbol}:\n", df.tail(1))
        sleep(1)  # Задержка между запросами, чтобы избежать блокировки

# Список популярных монет для анализа
symbols = ["BTC", "ETH", "XRP", "LTC", "ADA", "DOGE", "SOL", "DOT", "MATIC", "BCH"]

# Анализ монет
analyze_symbols(symbols)
