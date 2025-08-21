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
MARKET_CAP_USD_MIN = 100_000_000                  # порог капитализации ($100M)
TIMEFRAME = "1d"                                  # дневные свечи
SMA_LEN = 12
LOWER_PCT = 0.2558                                # 25.58%
NEAR_PCT = 3.0                                    # «почти достигли» — в пределах 3%
PREFERRED_QUOTES = ["USD", "USDT"]                # сначала USD, иначе USDT
# =======================================================

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
    # CCXT id биржи Crypto.com — 'cryptocom'
    ex = ccxt.cryptocom({
        "enableRateLimit": True,
        # при необходимости можно указать прокси:
        # "aiohttp_trust_env": True
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

# ---------- капитализации через CoinGecko ----------
def fetch_market_caps_coingecko(min_cap=MARKET_CAP_USD_MIN, max_pages=5):
    """
    Возвращает dict symbol_upper -> (id, name, market_cap)
    Берём топ по капитализации (до ~1250 монет, 250*5 страниц).
    """
    result = defaultdict(lambda: {"id": None, "name": None, "market_cap": 0})
    session = requests.Session()

    for page in range(1, max_pages + 1):
        url = (
            "https://api.coingecko.com/api/v3/coins/markets"
            f"?vs_currency=usd&order=market_cap_desc&per_page=250&page={page}"
            "&price_change_percentage=24h"
        )
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            arr = resp.json()
        except Exception as e:
            print(f"CoinGecko страница {page}: ошибка запроса: {e}")
            break

        if not arr:
            break

        for it in arr:
            try:
                mc = it.get("market_cap") or 0
                if mc >= min_cap:
                    sym = (it.get("symbol") or "").upper()
                    # если символ повторяется (разные сети/версии), оставляем запись с бОльшим MC
                    if mc > result[sym]["market_cap"]:
                        result[sym] = {
                            "id": it.get("id"),
                            "name": it.get("name"),
                            "market_cap": mc,
                        }
            except Exception:
                continue

        # если на странице в конце капитализации пошли < min_cap — дальнейшие страницы можно не брать
        if all((x.get("market_cap") or 0) < min_cap for x in arr[-10:]):
            break

        time.sleep(1.2)  # бережём лимиты CoinGecko

    return dict(result)

def filter_symbols_by_market_cap(crypto_com_map, mc_map):
    """
    На вход:
      crypto_com_map: dict base -> "BASE/QUOTE"
      mc_map: dict SYMBOL -> {...}
    На выход:
      список торговых символов (например, ["BTC/USD", "ETH/USDT", ...])
    """
    filtered = []
    for base, symbol in crypto_com_map.items():
        sym_upper = base.upper()
        info = mc_map.get(sym_upper)
        if info and (info.get("market_cap") or 0) >= MARKET_CAP_USD_MIN:
            filtered.append(symbol)
    return filtered

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
        msg = "📉 Монеты на Crypto.com, пересёкшие Lower2:\n" + "\n".join(matched)
        send_message(msg)
    if near:
        msg = "📡 Монеты на Crypto.com, близко к Lower2 (≤3%):\n" + "\n".join(near)
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
    base_to_symbol = pick_crypto_com_symbols(exchange)
    print(f"Найдено базовых активов (с USD/USDT): {len(base_to_symbol)}")

    # 2) Тянем капитализации и фильтруем ≥ $100M
    print("Загружаю капитализации с CoinGecko...")
    mc_map = fetch_market_caps_coingecko(MARKET_CAP_USD_MIN, max_pages=6)  # до ~1500 монет
    symbols = filter_symbols_by_market_cap(base_to_symbol, mc_map)
    symbols = sorted(set(symbols))
    print(f"К анализу отобрано {len(symbols)} инструментов (капитализация ≥ ${MARKET_CAP_USD_MIN:,}).")

    if not symbols:
        send_message("⚠️ На Crypto.com не найдено монет с капитализацией ≥ $100M (или не удалось получить данные CoinGecko).")
        return

    # 3) Аналитика и уведомления
    analyze_symbols(exchange, symbols, state)

if __name__ == "__main__":
    main()
