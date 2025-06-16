import requests
import pandas as pd
import json
import time
import os
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
STATE_FILE = "alert_state.json"  # Для хранения состояния уведомлений

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

# Уведомление в Telegram
def send_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Ошибка отправки сообщения: {e}")

# Выполнение безопасного запроса с повторными попытками
def safe_request(url, params, retries=3, delay=5):
    """Выполняет запрос с попытками и задержкой между ними."""
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()  # Возвращаем успешный ответ
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при запросе: {e}")
            if attempt < retries - 1:
                print(f"Попытка {attempt + 1} из {retries}, повтор через {delay} секунд.")
                time.sleep(delay)  # Задержка перед повтором
            else:
                return None  # Если все попытки не удались, возвращаем None

# Получение топ-400 монет с CoinGecko
def get_top_400_coins():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    coins = []
    page = 1

    while len(coins) < 400:
        params = {
            'vs_currency': 'usd',
            'order': 'market_cap_desc',
            'per_page': 100,  # Максимум 100 монет на страницу
            'page': page,     # Указываем страницу
        }
        
        data = safe_request(url, params)
        
        if data:
            coins.extend([coin['id'] for coin in data])
        else:
            print("Ошибка при получении данных.")
            break

        page += 1
        if len(data) < 100:  # Если на странице меньше 100 монет, то завершить
            break
        
        # Задержка между запросами для предотвращения блокировки
        print(f"Загружено {len(coins)} монет из 400, задержка на 2 секунды...")
        time.sleep(2)

    return coins[:400]

# Получение данных для монеты с CoinGecko
def get_coin_data(symbol):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/market_chart"
    params = {"vs_currency": "usd", "days": "30", "interval": "daily"}
    data = safe_request(url, params)
    
    if data is None or 'prices' not in data:
        print(f"Ошибка: Нет данных для монеты {symbol}")
        return None
    
    df = pd.DataFrame(data["prices"], columns=["timestamp", "price"])
    df["price"] = df["price"].astype(float)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    return df

# Анализ монет
def analyze_symbols(symbols, state):
    today = str(datetime.utcnow().date())
    matched, near = [], []

    print(f"Всего монет для анализа: {len(symbols)}")
    
    for symbol in symbols:
        print(f"Обрабатывается монета: {symbol}")
        
        # Получаем данные для монеты с CoinGecko
        df = get_coin_data(symbol)
        if df is None or len(df) < 12:
            print(f"Нет данных или недостаточно данных для монеты {symbol}")
            continue
        
        # Расчет 12-дневной SMA
        df["sma12"] = df["price"].rolling(12).mean()  # Расчет 12-дневной SMA
        df["lower2"] = df["sma12"] * (1 - 0.2558)  # Ожидаемое снижение на 25.58%
        
        price = df["price"].iloc[-1]
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
    if near:
        msg = "📡 Почти дошли до Lower 2:\n" + "\n".join(near)
        send_message(msg)

def main():
    state = load_state()
    
    # Получаем список топ-400 монет
    symbols = get_top_400_coins()  # Получаем топ 400 монет по капитализации
    if symbols:
        analyze_symbols(symbols, state)  # Анализируем монеты

if __name__ == "__main__":
    main()
