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
TIMEFRAME = "1d"                                  # дневные свечи
SMA_LEN = 12
LOWER_PCT = 0.2558                                # 25.58%
NEAR_PCT = 5.0                                    # «почти достигли» — в пределах 5%
PREFERRED_QUOTES = ["USD", "USDT"]                # сначала USD, иначе USDT
# =======================================================

# Абсолютные пути к файлам состояния и lock — рядом со скриптом
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "alert_state.json")
LOCK_FILE = os.path.join(BASE_DIR, ".alert_state.lock")

# ---------- утилиты лок-файла ----------
def acquire_lock(timeout=10, interval=0.2):
    start = time.time()
    while True:
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            if time.time() - start > timeout:
                print("⚠️ Не удалось получить lock — продолжаю без блокировки.")
                return False
            time.sleep(interval)

def release_lock():
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass

# ---------- утилиты состояния ----------
def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        if os.path.getsize(STATE_FILE) == 0:
            print("⚠️ Файл состояния пуст — начинаю с пустого словаря.")
            return {}
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"⚠️ Некорректный JSON в файле состояния ({e}). Переименовываю и начинаю с пустого.")
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        try:
            os.replace(STATE_FILE, STATE_FILE + f".corrupt.{ts}")
        except Exception:
            pass
        return {}
    except Exception as e:
        print(f"Ошибка при чтении состояния: {e}")
        return {}

def save_state(state):
    tmp_path = STATE_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, STATE_FILE)
    except Exception as e:
        print(f"Ошибка при сохранении состояния: {e}")
        try:
            os.remove(tmp_path)
        except Exception:
            pass

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
    # CCXT id биржи Crypto.com — 'cryptocom'
    ex = ccxt.cryptocom({
        "enableRateLimit": True,
    })
    ex.load_markets()
    return ex

def pick_crypto_com_symbols(exchange):
    """
    Возвращает словарь base -> выбранный инструмент (symbol) на Crypto.com.
    Предпочтение парам в USD, иначе USDT. Только активные SPOT-рынки.
    """
    markets = exchange.markets
    by_base = defaultdict(dict)  # base -> {quote: market}
    for m in markets.values():
        try:
            if not m.get("active", True):
                continue
            if not m.get("spot", True):
                continue
            base = m.get("base")
            quote = m.get("quote")
            if base and quote in PREFERRED_QUOTES:
                by_base[base][quote] = m
        except Exception:
            continue

    selected = {}
    for base, quotes in by_base.items():
        for q in PREFERRED_QUOTES:  # приоритет USD, затем USDT
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

        # Если уже уведомляли сегодня — пропускаем
        if state.get(f"{symbol}_crossed", "") == today or state.get(f"{symbol}_near", "") == today:
            continue

        # Сигнал «пересекли линию»
        if price <= lower2 and state.get(f"{symbol}_crossed", "") != today:
            matched.append(symbol)
            matched_count += 1
            state[symbol] = today
            state[f"{symbol}_crossed"] = today
            save_state(state)  # сохраняем сразу, чтобы не потерять отметку

        # Сигнал «приближение»
        elif 0 < diff_percent <= NEAR_PCT and state.get(f"{symbol}_near", "") != today:
            near.append(symbol)
            near_count += 1
            state[symbol] = today
            state[f"{symbol}_near"] = today
            save_state(state)

        # Пауза для бережного обращения к API биржи
        time.sleep(exchange.rateLimit / 1000.0 if getattr(exchange, "rateLimit", None) else 0.2)

    # финальная запись (на всякий случай)
    save_state(state)

    # Уведомления
    if matched:
        msg = "📉 Монеты на Crypto.com, пересёкшие Lower2:\n" + "\n".join(matched)
        send_message(msg)
    if near:
        msg = f"📡 Монеты на Crypto.com, близко к Lower2 (≤{NEAR_PCT:.0f}%):\n" + "\n".join(near)
        send_message(msg)

    summary = f"Итог:\n{matched_count} монет пересекли Lower2.\n{near_count} монет близко к Lower2."
    print(summary)
    if matched_count > 0 or near_count > 0:
        send_message(summary)

# ---------- main ----------
def main():
    print("STATE_FILE:", STATE_FILE)
    print("CWD:", os.getcwd())

    got_lock = acquire_lock()
    try:
        state = load_state()

        # 1) Подключаемся к бирже и собираем список доступных спотовых пар
        exchange = make_exchange()
        base_to_symbol = pick_crypto_com_symbols(exchange)
        print(f"Найдено базовых активов (с USD/USDT): {len(base_to_symbol)}")

        # 2) Получаем все монеты и начинаем анализ
        symbols = sorted(set(base_to_symbol.values()))
        print(f"К анализу отобрано {len(symbols)} инструментов.")

        if not symbols:
            send_message("⚠️ На Crypto.com не найдено спотовых монет для анализа.")
            return

        # 3) Аналитика и уведомления
        analyze_symbols(exchange, symbols, state)
    finally:
        if got_lock:
            release_lock()

if __name__ == "__main__":
    main()
