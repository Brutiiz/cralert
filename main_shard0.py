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
        print(f"TELEGRAM_TOKEN: {TELEGRAM_TOKEN}")  # Выводим токен для отладки
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        response = requests.post(url, json=payload)
        response.raise_for_status()  # Проверка успешности запроса
        print("Сообщение отправлено успешно!")
    except Exception as e:
        print(f"Ошибка отправки сообщения: {e}")

# Выполнение безопасного запроса с повторными попытками
def safe_request(url, params, retries=3, delay=5, backoff=2):
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()  # Возвращаем успешный ответ
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при запросе: {e}")
            if attempt < retries - 1:
                print(f"Попытка {attempt + 1} из {retries}, повтор через {delay} секунд.")
                time.sleep(delay)
                delay *= backoff  # Увеличиваем задержку после каждой попытки
            else:
                return None  # Если все попытки не удались, возвращаем None

# Получение данных о монетах с Bybit
def get_top_150_coins():
    # Для анализа будем использовать популярные монеты на USDT, которые торгуются на Bybit
    # Это не идеальный способ, так как API Bybit не предоставляет данных по капитализации напрямую,
    # но мы можем выбрать те монеты, которые торгуются активно.
    popular_symbols = [
        "BTC", "ETH", "XRP", "LTC", "ADA", "DOGE", "SOL", "DOT", "MATIC", "BCH", 
        "AVAX", "ATOM", "LINK", "SHIB", "UNI", "TRX", "FTM", "AAVE", "SUSHI", "BAL"
    ]
    return popular_symbols  # Вернем список популярных монет

# Получение данных для монеты с Bybit
def get_coin_data(symbol):
    url = f"https://api.bybit.com/v2/public/kline/list"
    params = {
        "symbol": f"{symbol}USDT",  # Формируем запрос с символом монеты
        "interval": "1d",  # Используем дневной интервал
        "limit": 30,  # Данные за последние 30 дней
    }
    data = safe_request(url, params, retries=3, delay=5, backoff=2)
    
    if data is None or 'result' not in data:
        print(f"Ошибка: Нет данных для монеты {symbol}")
        return None
    
    df = pd.DataFrame(data["result"], columns=["timestamp", "open", "high", "low", "close", "volume", "open_time", "close_time", "status", "high_time", "low_time", "volume_30d", "market_cap", "turnover"])
    df["close"] = df["close"].astype(float)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
    df.set_index("timestamp", inplace=True)
    return df

# Анализ монет
def analyze_symbols(symbols, state):
    today = str(datetime.utcnow().date())
    matched, near = [], []

    print(f"Всего монет для анализа: {len(symbols)}")

    for symbol in symbols:
        print(f"Обрабатывается монета: {symbol}")

        # Получаем данные для монеты с Bybit
        df = get_coin_data(symbol)
        if df is None or len(df) < 12:
            print(f"Нет данных или недостаточно данных для монеты {symbol}")
            continue

        # Расчет 12-дневной SMA
        df["sma12"] = df["close"].rolling(12).mean()  # Расчет 12-дневной SMA
        df["lower2"] = df["sma12"] * (1 - 0.2558)  # Ожидаемое снижение на 25.58%

        price = df["close"].iloc[-1]
        lower2 = df["lower2"].iloc[-1]
        diff_percent = (price - lower2) / lower2 * 100
        print(f"{symbol} цена: {price:.4f} | Lower2: {lower2:.4f} | Δ: {diff_percent:.2f}%")

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

        # Задержка после обработки каждой монеты
        time.sleep(1)  # Добавляем 1-секундную задержку между запросами

    save_state(state)

    print(f"Обработано {len(matched)} монет с достижением уровня")
    print(f"Обработано {len(near)} монет, которые почти достигли уровня")

    # Отправляем уведомления
    if matched:
        msg = "📉 Монеты КАСНУЛИСЬ Lower 2:\n" + "\n".join(matched)
        send_message(msg)
    else:
        print("Нет монет, которые достигли уровня Lower 2.")

    if near:
        msg = "📡 Почти дошли до Lower 2:\n" + "\n".join(near)
        send_message(msg)
    else:
        print("Нет монет, которые почти достигли уровня Lower 2.")

def main():
    state = load_state()

    # Получаем список популярных монет для анализа
    symbols = get_top_150_coins()  # Используем топ монет для анализа
    if symbols:
        analyze_symbols(symbols, state)  # Анализируем монеты

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Ошибка во время выполнения программы: {e}")
