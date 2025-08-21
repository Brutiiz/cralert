import requests
import json
import time
from datetime import datetime

# ====================== НАСТРОЙКИ ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")      # токен Telegram-бота
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # chat_id для уведомлений
STATE_FILE = "alert_state.json"                   # файл состояния уведомлений
TIMEFRAME = "1d"                                  # дневные свечи
SMA_LEN = 12
LOWER_PCT = 0.2558                                # 25.58%
NEAR_PCT = 5.0                                    # «почти достигли» — в пределах 5%
CAPITALIZATION_THRESHOLD = 90_000_000             # Порог капитализации (90 миллионов)
# =======================================================

# Получаем API ключи для Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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

# ---------- CoinGecko API ----------
def get_coingecko_market_caps(min_cap=CAPITALIZATION_THRESHOLD, max_pages=5):
    """
    Получаем список монет с капитализацией выше заданного порога.
    """
    result = []
    session = requests.Session()

    for page in range(1, max_pages + 1):
        url = (
            f"https://api.coingecko.com/api/v3/coins/markets"
            f"?vs_currency=usd&order=market_cap_desc&per_page=250&page={page}"
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

        for coin in arr:
            if coin.get("market_cap", 0) >= min_cap:
                result.append({
                    "symbol": coin["symbol"].upper(),
                    "name": coin["name"],
                    "market_cap": coin["market_cap"],
                    "current_price": coin["current_price"]
                })
        
        # Если на последней странице не найдено монет с капитализацией > порога — останавливаем загрузку
        if all(coin["market_cap"] < min_cap for coin in arr[-10:]):
            break

        time.sleep(1.2)  # бережем лимиты CoinGecko

    return result

# ---------- Crypto.com API ----------
def get_crypto_com_price(symbol):
    """
    Получение текущей цены с Crypto.com.
    Symbol должен быть в формате 'BASE/QUOTE', например 'BTC/USDT'.
    """
    url = f"https://api.crypto.com/v2/public/get-ticker"
    params = {
        "instrument_name": symbol.replace("/", "_")  # Заменяем слеш на подчеркивание
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if data.get("result"):
            price = data["result"]["last"]
            return float(price)
        else:
            return None
    except Exception as e:
        print(f"Ошибка при получении данных с Crypto.com для {symbol}: {e}")
        return None

# ---------- анализ монет ----------
def analyze_symbols(symbols, state):
    today = str(datetime.utcnow().date())
    matched, near = [], []
    matched_count, near_count = 0, 0

    for symbol_data in symbols:
        symbol = symbol_data['symbol']
        print(f"Обрабатывается {symbol} ...")
        
        price = get_crypto_com_price(symbol)  # Получаем цену с Crypto.com
        if price is None:
            continue

        # Рассчитываем 12-дневную SMA и другие параметры
        # Для упрощения, на этом этапе мы не используем реальные исторические данные,
        # но для реальной работы можно подключить API или использовать данные вручную
        sma12 = price  # Просто пример, реальную SMA нужно вычислять на основе исторических данных
        lower2 = sma12 * (1 - LOWER_PCT)
        diff_percent = (price - lower2) / lower2 * 100.0

        print(f"{symbol}: close={price:.8f} SMA12={sma12:.8f} Lower2={lower2:.8f} Δ={diff_percent:.4f}%")

        # Анти-спам: если уже уведомляли сегодня о достижении уровня — пропускаем
        if state.get(symbol) == today:
            continue

        # Сигнал «пересекли линию»
        if price <= lower2:
            matched.append(symbol)
            matched_count += 1
            state[symbol] = today
        # Сигнал «приближение»
        elif 0 < diff_percent <= NEAR_PCT:
            near.append(symbol)
            near_count += 1

        # Пауза для бережного обращения к API
        time.sleep(0.2)

    save_state(state)

    # Уведомления
    if matched:
        msg = "📉 Монеты, которые пересекли Lower2:\n" + "\n".join(matched)
        send_message(msg)
    if near:
        msg = "📡 Монеты, которые близки к Lower2 (≤5%):\n" + "\n".join(near)
        send_message(msg)

    summary = f"Итог:\n{matched_count} монет пересекли Lower2.\n{near_count} монет близко к Lower2."
    print(summary)
    if matched_count > 0 or near_count > 0:
        send_message(summary)

# ---------- main ----------
def main():
    state = load_state()

    # 1) Получаем список монет с капитализацией > 90 млн
    coins = get_coingecko_market_caps(min_cap=CAPITALIZATION_THRESHOLD)
    print(f"К анализу отобрано {len(coins)} монет с капитализацией > {CAPITALIZATION_THRESHOLD:,} USD.")

    if not coins:
        send_message("⚠️ Не найдено монет с капитализацией > 90 млн USD.")
        return

    # 2) Анализируем монеты
    analyze_symbols(coins, state)

if __name__ == "__main__":
    main()
