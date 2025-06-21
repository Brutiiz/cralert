import ccxt
import time

# Создаем объект для работы с Coinbase через CCXT
exchange = ccxt.coinbase()

# Получаем данные о свечах для монеты BTC/USD на Coinbase Pro
def get_coin_data(symbol):
    try:
        # Получаем данные о свечах за 1 день
        candles = exchange.fetch_ohlcv(symbol, '1d')  # '1d' означает 1 день
        return candles
    except Exception as e:
        print(f"Ошибка при получении данных: {e}")
        return None

# Пример получения данных для BTC/USD
symbol = "BTC/USD"  # Для Coinbase используем "BTC/USD"
candles = get_coin_data(symbol)

if candles:
    # Выводим данные о свечах
    for candle in candles:
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(candle[0] / 1000))  # Преобразуем timestamp
        print(f"Дата: {timestamp}, Открытие: {candle[1]}, Закрытие: {candle[4]}, Макс: {candle[2]}, Мин: {candle[3]}, Объем: {candle[5]}")
else:
    print("Нет данных о свечах")
