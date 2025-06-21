import requests
import pandas as pd
import time

# Функция для получения данных о свечах с Bybit
def get_coin_data(symbol):
    # URL для запроса в тестовой сети
    url = "https://api-testnet.bybit.com/v2/public/kline/list"
    
    # Параметры запроса
    params = {
        "symbol": f"{symbol}USDT",  # Символ монеты
        "interval": "1d",  # Интервал 1 день (можно использовать другие: 1m, 5m, 15m, 1h и т.д.)
        "limit": 30  # Данные за последние 30 дней
    }

    # Отправка GET-запроса
    response = requests.get(url, params=params)
    
    # Проверяем, успешен ли запрос
    if response.status_code != 200:
        print(f"Ошибка при запросе: {response.status_code} - {response.text}")
        return None

    # Получение данных из ответа
    data = response.json()

    # Проверяем наличие данных в ответе
    if "result" not in data:
        print("Ошибка: Не получены данные о свечах.")
        return None

    # Преобразование данных в DataFrame
    df = pd.DataFrame(data['result'])

    # Преобразуем временные метки в читаемый формат
    df['timestamp'] = pd.to_datetime(df['open_time'], unit='s')

    # Устанавливаем индекс как временную метку
    df.set_index('timestamp', inplace=True)

    # Убираем лишние столбцы, чтобы оставить только полезные
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
        time.sleep(1)  # Задержка между запросами, чтобы избежать блокировки

# Список популярных монет для анализа
symbols = ["BTC", "ETH", "XRP", "LTC", "ADA", "DOGE", "SOL", "DOT", "MATIC", "BCH"]

# Анализ монет
analyze_symbols(symbols)
