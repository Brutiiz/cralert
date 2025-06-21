import requests
import pandas as pd
import json
import time
import os
from datetime import datetime

# Получаем Telegram токен и другие данные из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # Токен Telegram бота
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # ID чата для отправки сообщений в Telegram
STATE_FILE = "alert_state.json"  # Для хранения состояния уведомлений

# Загрузка состояния уведомлений
def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка при загрузке состояния: {e}")
        return {}

# Сохранение состояния уведомлений
def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Ошибка при сохранении состояния: {e}")

# Уведомление в Telegram
def send_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        response = requests.post(url, json=payload)
        response.raise_for_status()  # Проверка успешности запроса
        print("Сообщение отправлено успешно!")
    except Exception as e:
        print(f"Ошибка отправки сообщения: {e}")

# Получение данных для монеты с FTX
def get_coin_data(symbol):
    url = f"https://ftx.com/api/markets/{symbol}/candles"
    params = {
        "resolution": 86400,  # Данные за день
        "limit": 30,  # Ограничение на 30 последних свечей
    }
    
    retries = 5  # Количество попыток
    delay = 5  # Задержка между попытками (в секундах)
    
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, timeout=10)  # Устанавливаем тайм-аут
            response.raise_for_status()  # Проверка на статус ответа
            data = response.json()

            if "result" not in data:
                print("Ошибка: Не получены данные о свечах.")
                return None

            df = pd.DataFrame(data['result'])
            df['timestamp'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('timestamp', inplace=True)
            return df
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при запросе (попытка {attempt + 1}): {e}")
            time.sleep(delay)  # Задержка перед повторной попыткой
    print("Превышено количество попыток запроса.")
    return None

# Анализ монет
def analyze_symbols(symbols, state):
    today = str(datetime.utcnow().date())
    matched, near = [], []

    for symbol in symbols:
        print(f"Обрабатывается монета: {symbol}")

        # Получаем данные для монеты с FTX
        df = get_coin_data(symbol)
        if df is None or len(df) < 12:
            continue

        # Расчет 12-дневной SMA
        df["sma12"] = df["close"].rolling(12).mean()
        df["lower2"] = df["sma12"] * (1 - 0.2558)  # Ожидаемое снижение на 25.58%

        price = df["close"].iloc[-1]
        lower2 = df["lower2"].iloc[-1]
        diff_percent = (price - lower2) / lower2 * 100

        # Если монета уже получила уведомление сегодня, пропускаем
        if state.get(symbol) == today:
            continue

        # Уведомление о достижении уровня
        if price <= lower2:
            matched.append(symbol)
            state[symbol] = today  # Обновляем состояние
        # Уведомление о приближении (почти достигли уровня)
        elif 0 < diff_percent <= 3:
            near.append(symbol)

    save_state(state)

    if matched:
        msg = "📉 Монеты, которые достигли Lower 2:\n" + "\n".join(matched)
        send_message(msg)

    if near:
        msg = "📡 Монеты, которые почти достигли Lower 2:\n" + "\n".join(near)
        send_message(msg)

def main():
    state = load_state()
    symbols = ["BTC-USD", "ETH-USD", "XRP-USD", "LTC-USD", "ADA-USD", "DOGE-USD", "SOL-USD", "DOT-USD", "MATIC-USD", "BCH-USD"]
    analyze_symbols(symbols, state)

if __name__ == "__main__":
    main()
