import ccxt
import requests
import pandas as pd
import time
import os
import json
from datetime import datetime
from collections import defaultdict

# ====================== НАСТРОЙКИ ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")      # токен Telegram-бота
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # chat_id для уведомлений
STATE_FILE = "alert_state.json"                   # файл состояния уведомлений
TIMEFRAME = "1d"                                  # дневные свечи
SMA_LEN = 12
LOWER_PCT = 0.2558                                # 25.58%
NEAR_PCT = 5.0                                    # «почти достигли» — в пределах 5%
PREFERRED_QUOTES = ["USD", "USDT"]                # сначала USD, иначе USDT
# =======================================================

# Получаем API ключи из переменных окружения
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")

# ---------- утилиты состояния ----------
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception as e:
        print(f"Ошибка при сохранении состояния: {e}")

# ---------- Telegram ----------
def send_message(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ВНИМАНИЕ: TELEGRAM_TOKEN или TELEGRAM_CHAT_ID не заданы. Сообщение:")
        print(text)
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        r = requests.post(url, json=payload, timeout=20)
        r.raise_for_status()
        print("Сообщение отправлено.")
    except Exception as e:
        print(f"Ошибка отправки сообщения: {e}")

# ---------- источники данных ----------
def make_exchange():
    # Подключаемся к Bybit с использованием API ключей
    ex = ccxt.bybit({
        'apiKey': API_KEY,    # Ваш API ключ
        'secret': API_SECRET, # Ваш секретный ключ
        'enableRateLimit': True,
    })
    ex.load_markets()
    return ex

def pick_bybit_symbols(exchange):
    """
    Возвращает словарь base -> выбранный инструмент (symbol) на Bybit.
    Предпочтение парам в USD, иначе USDT. Только активные SPOT-рынки.
    """
    markets = exchange.markets
    by_base = defaultdict(dict)  # base -> {quote: market}
    for m in markets.values():
        try:
            if not m.get("active", True):
                continue
            if not m.get("spot", False):
                continue
            base = m.get("base")
            quote = m.get("quote")
            if base and quote in PREFERRED_QUOTES:
                # храним лучший маркет для каждой котировки
                by_base[base][quote] = m
        except Exception:
            continue

    selected = {}
    for base, quotes in by_base.items():
        # приоритет USD, затем USDT
        for q in PREFERRED_QUOTES:
            if q in quotes:
                selected[base] = quotes[q]["symbol"]
                break
    return selected  # dict: base -> "BASE/QUOTE"

# ---------- свечи и анализ ----------
def fetch_ohlcv_safe(exchange, symbol, timeframe=TIMEFRAME, limit=100):
    try:
        return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    except Exception as e:
        print(f"[{symbol}] ошибка fetch_ohlcv: {e}")
        return None

def analyze_symbols(exchange, symbols, state):
    today = str(datetime.utcnow().date())
    matched, near = [], []
    matched_count, near_count = 0, 0

    for symbol in symbols:
        print(f"Обрабатывается {symbol} ...")
        raw = fetch_ohlcv_safe(exchange, symbol, timeframe=TIMEFRAME, limit=max(SMA_LEN + 1, 60))
        if not raw or len(raw) < SMA_LEN:
            continue

        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        df["sma"] = df["close"].rolling(SMA_LEN).mean()
        if pd.isna(df["sma"].iloc[-1]):
            continue
        df["lower2"] = df["sma"] * (1 - LOWER_PCT)

        price = float(df["close"].iloc[-1])
        lower2 = float(df["lower2"].iloc[-1])
        diff_percent = (price - lower2) / lower2 * 100.0

        print(f"{symbol}: close={price:.8f} SMA{SMA_LEN}={df['sma'].iloc[-1]:.8f} Lower2={lower2:.8f} Δ={diff_percent:.4f}%")

        # анти-спам: если уже уведомляли сегодня о достижении уровня — пропускаем
        if state.get(symbol) == today:
            continue

        # сигнал «пересекли линию»
        if price <= lower2:
            matched.append(symbol)
            matched_count += 1
            state[symbol] = today
        # сигнал «приближение»
        elif 0 < diff_percent <= NEAR_PCT:
            near.append(symbol)
            near_count += 1

        # пауза для бережного обращения к API биржи
        time.sleep(exchange.rateLimit / 1000.0 if getattr(exchange, "rateLimit", None) else 0.2)

    save_state(state)

    # Уведомления
    if matched:
        msg = "📉 Монеты на Bybit, пересёкшие Lower2:\n" + "\n".join(matched)
        send_message(msg)
    if near:
        msg = "📡 Монеты на Bybit, близко к Lower2 (≤5%):\n" + "\n".join(near)
        send_message(msg)

    summary = f"Итог:\n{matched_count} монет пересекли Lower2.\n{near_count} монет близко к Lower2."
    print(summary)
    if matched_count > 0 or near_count > 0:
        send_message(summary)

# ---------- main ----------
def main():
    state = load_state()

    # 1) Подключаемся к бирже и собираем список доступных спотовых пар
    exchange = make_exchange()
    base_to_symbol = pick_bybit_symbols(exchange)
    print(f"Найдено базовых активов (с USD/USDT): {len(base_to_symbol)}")

    # 2) Анализируем монеты на Bybit
    symbols = sorted(set(base_to_symbol.values()))
    print(f"К анализу отобрано {len(symbols)} инструментов.")

    if not symbols:
        send_message("⚠️ На Bybit не найдено монет для анализа.")
        return

    # 3) Аналитика и уведомления
    analyze_symbols(exchange, symbols, state)

if __name__ == "__main__":
    main()
