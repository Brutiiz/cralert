import ccxt
import requests
import pandas as pd
import time
import os
import json
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

# Создаем объект для работы с Coinbase через CCXT
exchange = ccxt.coinbase()

# Получаем данные для монеты с Coinbase
def get_coin_data(symbol):
    try:
        # Получаем данные о свечах за 1 день
        candles = exchange.fetch_ohlcv(symbol, '1d')  # '1d' означает 1 день
        return candles
    except Exception as e:
        print(f"Ошибка при получении данных: {e}")
        return None

# Анализ монет
def analyze_symbols(symbols, state):
    today = str(datetime.utcnow().date())
    matched, near = [], []

    # Статистика
    matched_count = 0
    near_count = 0

    for symbol in symbols:
        print(f"Обрабатывается монета: {symbol}")

        # Получаем данные для монеты с Coinbase
        df = get_coin_data(symbol)
        if df is None or len(df) < 12:
            continue

        # Расчет 12-дневной SMA
        df = pd.DataFrame(df, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)

        df["sma12"] = df["close"].rolling(12).mean()
        df["lower2"] = df["sma12"] * (1 - 0.2558)  # Ожидаемое снижение на 25.58%

        price = df["close"].iloc[-1]
        lower2 = df["lower2"].iloc[-1]
        diff_percent = (price - lower2) / lower2 * 100

        # Печать информации о монете с 10 знаками после запятой
        print(f"Цена монеты {symbol}: {price:.10f}")
        print(f"12-дневная SMA: {df['sma12'].iloc[-1]:.10f}")
        print(f"Lower2 (25.58% ниже SMA): {lower2:.10f}")
        print(f"Разница от Lower2: {diff_percent:.10f}%")

        # Если монета уже получила уведомление сегодня, пропускаем
        if state.get(symbol) == today:
            continue

        # Уведомление о достижении уровня
        if price <= lower2:
            matched.append(symbol)
            matched_count += 1
            state[symbol] = today  # Обновляем состояние
        # Уведомление о приближении (почти достигли уровня)
        elif 0 < diff_percent <= 3:
            near.append(symbol)
            near_count += 1

    save_state(state)

    # Итоговые сообщения
    if matched:
        msg = "📉 Монеты, которые достигли Lower 2:\n" + "\n".join(matched)
        send_message(msg)

    if near:
        msg = "📡 Монеты, которые почти достигли Lower 2:\n" + "\n".join(near)
        send_message(msg)

    # Итоговый отчет
    summary = f"Итог:\n{matched_count} монет достигли уровня Lower2.\n{near_count} монет находятся рядом с уровнем Lower2."
    print(summary)
    if matched_count > 0 or near_count > 0:
        send_message(summary)

def main():
    state = load_state()

    # Список монет для анализа
    symbols = [
        "BCH/USD", "SUI/USD", "ADA/USD", "DOGE/USD", "SOL/USD", "XRP/USD", "ETH/USD",
        "PEPE/USD", "UNI/USD", "DOT/USD", "HBAR/USD", "LTC/USD", "SHIB/USD", "AVAX/USD", "XLM/USD", "LINK/USD",
        "POL/USD", "MANTLE/USD", "ONDO/USD", "ETC/USD", "NEAR/USD", "ICP/USD", "CRO/USD", "APT/USD", "TAO/USD", "AAVE/USD",
        "ALGO/USD", "WLD/USD", "ATOM/USD", "FIL/USD", "FET/USD", "RENDER/USD", "ENA/USD", "VET/USD", "TRUMP/USD",
        "STX/USD", "OP/USD", "TIA/USD", "BONK/USD", "INJ/USD", "QNT/USD", "FLR/USD", "SEI/USD", "ARB/USD",
        "FLOKI/USD", "CAKE/USD", "JTO/USD", "IMX/USD", "IP/USD", "WIF/USD", "CRV/USD", "GRT/USD", "PAXG/USD", "FARTCOIN/USD",
        "XTZ/USD", "PENGU/USD", "ZRO/USD", "PENDLE/USD", "JASMY/USD", "SAND/USD", "LDO/USD", "AERO/USD", "ZEC/USD", "ENS/USD",
        "HNT/USD", "KAVA/USD", "COMP/USD", "XCN/USD", "APE/USD", "MANA/USD", "SYRUP/USD", "FLOW/USD", "PYTH/USD", "CORECHAIN/USD",
        "EIGEN/USD", "ETHFI/USD", "SUPER/USD", "RSR/USD", "AXS/USD", "AIOZ/USD", "STRK/USD", "AXL/USD", "MORPHO/USD", "EGLD/USD",
        "DASH/USD", "TURBO/USD", "CVX/USD", "LPT/USD", "1INCH/USD", "AKT/USD", "POPCAT/USD", "GNO/USD", "AMP/USD", "ZK/USD", "MOG/USD", "CHZ/USD", "KAITO/USD", "ATH/USD",
        "SAFE/USD", "PNUT/USD", "KSM/USD", "GLM/USD", "BERA/USD", "MINA/USD", "IOTX/USD"
    ]

    analyze_symbols(symbols, state)

if __name__ == "__main__":
    main()
