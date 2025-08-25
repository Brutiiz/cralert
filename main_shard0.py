import ccxt
import requests
import pandas as pd
import time
import os
import json
import base64
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

# Хранилище состояния в GitHub (через Contents API)
GH_TOKEN = os.getenv("GH_STATE_TOKEN") or os.getenv("GITHUB_TOKEN")
STATE_REPO = os.getenv("STATE_REPO") or os.getenv("GITHUB_REPOSITORY")  # owner/repo
STATE_PATH = os.getenv("STATE_PATH", "state/alert_state.json")          # путь в репозитории
STATE_BRANCH = os.getenv("STATE_BRANCH", "main")                        # ветка

# Локальный фоллбэк (если токена нет — например, локальный запуск)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_STATE_FILE = os.path.join(BASE_DIR, "alert_state.json")
# =======================================================


# ---------- GitHub Contents API: загрузка/сохранение состояния ----------
def _gh_headers():
    return {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

def _gh_contents_url():
    if not STATE_REPO or "/" not in STATE_REPO:
        raise RuntimeError("STATE_REPO должен быть в формате owner/repo")
    owner, repo = STATE_REPO.split("/", 1)
    return f"https://api.github.com/repos/{owner}/{repo}/contents/{STATE_PATH}"

def load_state():
    """
    Пытается прочитать состояние из GitHub (ветка STATE_BRANCH).
    Если нет токена/доступа — читает локальный файл (если есть).
    Возвращает (dict state, sha) — sha нужен для безопасной записи в GitHub.
    """
    # Попытка из GitHub
    if GH_TOKEN and STATE_REPO:
        try:
            url = _gh_contents_url()
            params = {"ref": STATE_BRANCH}
            r = requests.get(url, headers=_gh_headers(), params=params, timeout=30)
            if r.status_code == 200:
                data = r.json()
                content_b64 = data.get("content", "")
                content = base64.b64decode(content_b64.encode()).decode("utf-8")
                state = json.loads(content) if content.strip() else {}
                sha = data.get("sha")
                print(f"Состояние загружено из GitHub: {STATE_REPO}/{STATE_PATH}@{STATE_BRANCH}")
                return state, sha
            elif r.status_code == 404:
                print("Файл состояния в GitHub отсутствует — начну с пустого.")
                return {}, None
            else:
                print(f"Не удалось получить состояние из GitHub: {r.status_code} {r.text}")
        except Exception as e:
            print(f"Ошибка GitHub-загрузки: {e}")

    # Фоллбэк — локально
    try:
        if os.path.exists(LOCAL_STATE_FILE) and os.path.getsize(LOCAL_STATE_FILE) > 0:
            with open(LOCAL_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
                print(f"Состояние загружено локально: {LOCAL_STATE_FILE}")
                return state, None
    except Exception as e:
        print(f"Ошибка чтения локального состояния: {e}")
    print("Состояние пустое (по умолчанию).")
    return {}, None

def save_state(state, prev_sha=None):
    """
    Пишет состояние в GitHub (коммитит файл).
    Использует prev_sha для оптимистичной блокировки (если sha изменился — будет 409).
    Если нет токена/репо — сохраняет локально.
    """
    body = json.dumps(state, ensure_ascii=False, sort_keys=True, indent=0)

    # Путь GitHub
    if GH_TOKEN and STATE_REPO:
        try:
            url = _gh_contents_url()
            message = f"chore(state): update {STATE_PATH} {datetime.utcnow().isoformat()}Z"
            content_b64 = base64.b64encode(body.encode("utf-8")).decode("utf-8")
            payload = {
                "message": message,
                "content": content_b64,
                "branch": STATE_BRANCH,
            }
            if prev_sha:
                payload["sha"] = prev_sha
            r = requests.put(url, headers=_gh_headers(), json=payload, timeout=30)
            if r.status_code in (200, 201):
                new_sha = r.json().get("content", {}).get("sha")
                print(f"Состояние сохранено в GitHub: sha={new_sha}")
                return new_sha
            elif r.status_code == 409:
                print("⚠️ Конфликт SHA при записи состояния (кто-то обновил файл параллельно). Перечитай и повтори при необходимости.")
                return prev_sha
            else:
                print(f"Не удалось записать состояние в GitHub: {r.status_code} {r.text}")
        except Exception as e:
            print(f"Ошибка GitHub-сохранения: {e}")

    # Фоллбэк — локальная запись
    try:
        os.makedirs(os.path.dirname(LOCAL_STATE_FILE), exist_ok=True)
        tmp = LOCAL_STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, LOCAL_STATE_FILE)
        print(f"Состояние сохранено локально: {LOCAL_STATE_FILE}")
    except Exception as e:
        print(f"Ошибка локального сохранения состояния: {e}")
    return prev_sha


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

def analyze_symbols(exchange, symbols, state, state_sha):
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

        updated = False
        # Сигнал «пересекли линию»
        if price <= lower2 and state.get(f"{symbol}_crossed", "") != today:
            matched.append(symbol)
            matched_count += 1
            state[symbol] = today
            state[f"{symbol}_crossed"] = today
            updated = True

        # Сигнал «приближение»
        elif 0 < diff_percent <= NEAR_PCT and state.get(f"{symbol}_near", "") != today:
            near.append(symbol)
            near_count += 1
            state[symbol] = today
            state[f"{symbol}_near"] = today
            updated = True

        if updated:
            # сохраняем сразу (GitHub commit или локально); обновляем sha если успешно
            new_sha = save_state(state, state_sha)
            if new_sha:
                state_sha = new_sha

        # Пауза для бережного обращения к API биржи
        time.sleep(exchange.rateLimit / 1000.0 if getattr(exchange, "rateLimit", None) else 0.2)

    # финальная запись (на всякий случай)
    new_sha = save_state(state, state_sha)
    if new_sha:
        state_sha = new_sha

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
    print("STATE_REPO:", STATE_REPO)
    print("STATE_PATH:", STATE_PATH)
    print("STATE_BRANCH:", STATE_BRANCH)
    print("LOCAL_STATE_FILE:", LOCAL_STATE_FILE)

    # 1) Загружаем состояние (GitHub или локально)
    state, state_sha = load_state()

    # 2) Подключаемся к бирже и собираем список доступных спотовых пар
    exchange = make_exchange()
    base_to_symbol = pick_crypto_com_symbols(exchange)
    print(f"Найдено базовых активов (с USD/USDT): {len(base_to_symbol)}")

    # 3) Получаем все монеты и начинаем анализ
    symbols = sorted(set(base_to_symbol.values()))
    print(f"К анализу отобрано {len(symbols)} инструментов.")

    if not symbols:
        send_message("⚠️ На Crypto.com не найдено спотовых монет для анализа.")
        return

    # 4) Аналитика и уведомления
    analyze_symbols(exchange, symbols, state, state_sha)


if __name__ == "__main__":
    main()
