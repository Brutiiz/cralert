import requests
import time

# Пример использования API Bybit с задержками для предотвращения перегрузки
API_KEY = 'your_api_key'
API_SECRET = 'your_api_secret'

# Функция для получения данных с Bybit
def get_coin_data(symbol):
    url = "https://api.bybit.com/v2/public/kline/list"
    params = {
        "api_key": API_KEY,
        "symbol": f"{symbol}USDT", 
        "interval": "1d", 
        "limit": 30,
        "timestamp": int(time.time() * 1000)
    }
    response = requests.get(url, params=params)
    data = response.json()
    if data["ret_code"] == 0:
        return data['result']
    else:
        print(f"Ошибка: {data}")
        return None

symbols = ['BTC', 'ETH', 'XRP', 'ADA']  # Пример списка монет

for symbol in symbols:
    data = get_coin_data(symbol)
    if data:
        print(f"Данные для {symbol}: {data}")
    time.sleep(1)  # Задержка, чтобы избежать перегрузки API
