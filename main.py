from flask import Flask
import threading
import time
import requests
import pandas as pd
import logging
from telegram import Bot
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

# 🔐 Загрузка из .env
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = Bot(token=TOKEN)
app = Flask(__name__)

# 🪵 Логирование
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s — %(levelname)s — %(message)s')

COINS = ['BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT','PEPEUSDT','TRUMPUSDT','WIFUSDT','DOGEUSDT','FLOKIUSDT','BONKUSDT']
TIMEFRAMES = ['1m', '5m', '15m']

last_signals = {}  # {symbol_tf: timestamp}
last_check_time = datetime.utcnow()
signals_found = False

@app.route('/')
def home():
    return '✅ Scalping bot is running!'

@app.route('/test')
def test():
    try:
        bot.send_message(chat_id=CHAT_ID, text='✅ Тестовое сообщение от бота!')
        return 'Сообщение отправлено!'
    except Exception as e:
        return f'❌ Ошибка при отправке: {e}'

def get_klines(symbol, interval, limit=100):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=10)
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'time','o','h','l','c','v','x','q','n','taker_base_vol','taker_quote_vol','ignore'
        ])
        df = df.astype({'o': float, 'h': float, 'l': float, 'c': float})
        return df
    except Exception as e:
        logging.error(f"Ошибка загрузки данных {symbol} {interval}: {e}")
        return pd.DataFrame()

def calculate_rsi(df, period=14):
    delta = df['c'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def is_bullish_engulfing(df):
    if len(df) < 2:
        return False
    return (
        df.iloc[-2]['c'] < df.iloc[-2]['o'] and
        df.iloc[-1]['c'] > df.iloc[-1]['o'] and
        df.iloc[-1]['c'] > df.iloc[-2]['o'] and
        df.iloc[-1]['o'] < df.iloc[-2]['c']
    )

def is_bearish_engulfing(df):
    if len(df) < 2:
        return False
    return (
        df.iloc[-2]['c'] > df.iloc[-2]['o'] and
        df.iloc[-1]['c'] < df.iloc[-1]['o'] and
        df.iloc[-1]['c'] < df.iloc[-2]['o'] and
        df.iloc[-1]['o'] > df.iloc[-2]['c']
    )

def check_signals():
    global last_check_time, signals_found
    while True:
        signals_found = False
        logging.info("🔍 Проверка сигналов начата...")
        for symbol in COINS:
            for tf in TIMEFRAMES:
                try:
                    df = get_klines(symbol, tf)
                    if df is None or len(df) < 20:
                        continue

                    rsi_series = calculate_rsi(df)
                    if rsi_series.isnull().any():
                        continue

                    rsi = rsi_series.iloc[-1]
                    key = f"{symbol}_{tf}"

                    # Паттерны
                    bull = is_bullish_engulfing(df)
                    bear = is_bearish_engulfing(df)

                    # 🔍 Генерация сигналов (но только если они новые)
                    if bull and rsi < 40:
                        if last_signals.get(key) != 'BUY':
                            bot.send_message(chat_id=CHAT_ID,
                                text=f'✅ Сильный BUY сигнал: {symbol} ({tf})\nRSI = {rsi:.2f}\nПаттерн: бычье поглощение'
                            )
                            last_signals[key] = 'BUY'
                            signals_found = True

                    elif bear and rsi > 60:
                        if last_signals.get(key) != 'SELL':
                            bot.send_message(chat_id=CHAT_ID,
                                text=f'✅ Сильный SELL сигнал: {symbol} ({tf})\nRSI = {rsi:.2f}\nПаттерн: медвежье поглощение'
                            )
                            last_signals[key] = 'SELL'
                            signals_found = True

                except Exception as e:
                    logging.error(f"❌ Ошибка при анализе {symbol} {tf}: {e}")

        # ⏰ Сообщение "нет сигналов" раз в час
        now = datetime.utcnow()
        if now - last_check_time > timedelta(hours=1):
            if not signals_found:
                try:
                    bot.send_message(chat_id=CHAT_ID, text='ℹ️ За последний час не найдено сигналов.')
                    logging.info("ℹ️ Сообщение об отсутствии сигналов отправлено.")
                except Exception as e:
                    logging.error(f"Ошибка при отправке сообщения об отсутствии сигналов: {e}")
            last_check_time = now

        time.sleep(300)  # 5 минут

# ▶️ Поток
threading.Thread(target=check_signals, daemon=True).start()

# 🚀 Flask
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
