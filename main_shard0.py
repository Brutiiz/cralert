import websocket
import json

# WebSocket URL для получения данных о свечах
url = "wss://stream.bybit.com/realtime"

# Подключение к WebSocket для получения данных о свечах
def on_message(ws, message):
    data = json.loads(message)
    if "topic" in data and data["topic"] == "kline":
        print(f"Получены данные о свечах: {data}")

def on_error(ws, error):
    print(f"Ошибка: {error}")

def on_close(ws, close_status_code, close_msg):
    print("Закрыто соединение")

def on_open(ws):
    # Подписка на канделябры для BTC/USDT
    ws.send(json.dumps({
        "op": "subscribe",
        "args": ["kline.BTCUSDT.1m"]  # Подписка на 1-минутные свечи для BTC/USDT
    }))

# Установка WebSocket
ws = websocket.WebSocketApp(url, on_message=on_message, on_error=on_error, on_close=on_close)
ws.on_open = on_open

# Запуск WebSocket
ws.run_forever()
