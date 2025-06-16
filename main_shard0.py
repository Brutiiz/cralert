import requests
import pandas as pd
import json
import time
import os
from datetime import datetime
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Получаем Telegram токен и другие данные из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # Токен Telegram бота
CRYPTOCOMPARE_API_KEY = os.getenv("CRYPTOCOMPARE_API_KEY")  # API ключ для CryptoCompare
CHAT_ID = os.getenv("CHAT_ID")  # ID чата для отправки сообщений в Telegram
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
        payload = {"chat_id": CHAT_ID, "text": message}
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

# Получение топ-310 монет с CryptoCompare
def get_top_310_coins():
    url = "https://min-api.cryptocompare.com/data/top/totalvolfull"
    coins = []
    page = 1

    while len(coins) < 310:  # Изменено на 310
        params = {
            'apiKey': CRYPTOCOMPARE_API_KEY,
            'limit': 100,  # Максимум 100 монет на страницу
            'page': page,   # Указываем страницу
            'tsym': 'USD',  # Выводим по отношению к USD
        }

        data = safe_request(url, params, retries=3, delay=2, backoff=2)

        if data and 'Data' in data:
            # Фильтруем монеты по рыночной капитализации, проверяя наличие нужных ключей
            filtered_coins = [
                coin['CoinInfo']['Name']
                for coin in data['Data']
                if 'RAW' in coin and 'USD' in coin['RAW'] and 'MKTCAP' in coin['RAW']['USD'] and coin['RAW']['USD']['MKTCAP'] is not None
            ]
            coins.extend(filtered_coins)
        else:
            print("Ошибка при получении данных.")
            break

        page += 1
        if len(data['Data']) < 100:  # Если на странице меньше 100 монет, то завершить
            break

        # Задержка между запросами для предотвращения блокировки
        print(f"Загружено {len(coins)} монет из 310, задержка на 2 секунды...")
        time.sleep(2)

    return coins[:310]  # Ограничиваем 310 монетами

# Получение данных для монеты с CryptoCompare
def get_coin_data(symbol):
    url = f"https://min-api.cryptocompare.com/data/v2/histoday"
    params = {
        "apiKey": CRYPTOCOMPARE_API_KEY,
        "fsym": symbol,
        "tsym": "USD",
        "limit": 30,  # Данные за последние 30 дней
        "aggregate": 1,
    }
    data = safe_request(url, params, retries=3, delay=5, backoff=2)
    
    if data is None or 'Data' not in data:
        print(f"Ошибка: Нет данных для монеты {symbol}")
        return None
    
    df = pd.DataFrame(data["Data"]["Data"], columns=["time", "close"])
    df["close"] = df["close"].astype(float)
    df["timestamp"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("timestamp", inplace=True)
    return df

# Анализ монет
def analyze_symbols(symbols, state):
    today = str(datetime.utcnow().date())
    matched, near = [], []

    print(f"Всего монет для анализа: {len(symbols)}")

    for symbol in symbols:
        print(f"Обрабатывается монета: {symbol}")

        # Получаем данные для монеты с CryptoCompare
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

    # Получаем список топ-310 монет
    symbols = get_top_310_coins()  # Получаем топ 310 монет по капитализации
    if symbols:
        analyze_symbols(symbols, state)  # Анализируем монеты

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Ошибка во время выполнения программы: {e}")
