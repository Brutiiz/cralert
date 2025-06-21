import ccxt

# Создаем объект для работы с биржей (например, Binance)
exchange = ccxt.binance()

# Получаем данные о свечах для монеты BTC/USDT на Binance
def get_coin_data(symbol):
    try:
        candles = exchange.fetch_ohlcv(symbol, '1d')  # '1d' — это 1 день
        return candles
    except Exception as e:
        print(f"Ошибка при получении данных: {e}")
        return None

# Пример получения данных для BTC/USDT
symbol = "BTC/USDT"
candles = get_coin_data(symbol)

if candles:
    for candle in candles:
        print(candle)  # Печать данных о свечах
else:
    print("Нет данных о свечах")
