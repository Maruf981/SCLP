from flask import Flask
import threading
import time
import requests
import pandas as pd
from telegram import Bot
import traceback
from datetime import datetime, timedelta
from collections import defaultdict

app = Flask(__name__)

TOKEN = '8127035277:AAGTYZB_0IfIiSCnjL4bUD0KeOIerSWg-eg'
CHAT_ID = '443841357'
bot = Bot(token=TOKEN)

COINS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'PEPEUSDT',
    'TRUMPUSDT', 'WIFUSDT', 'DOGEUSDT', 'FLOKIUSDT', 'BONKUSDT'
]
TIMEFRAMES = ['1m', '5m', '15m']

# Счетчики для статистики
strong_signals = 0
simple_signals = 0
signals_per_coin = defaultdict(int)
last_stat_time = datetime.utcnow()

@app.route('/')
def home():
    return '✅ Scalping bot is running!'

def get_klines(symbol, interval, limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    data = response.json()
    df = pd.DataFrame(data, columns=[
        'time','o','h','l','c','v','x','q','n',
        'taker_base_vol','taker_quote_vol','ignore'
    ])
    df['c'] = df['c'].astype(float)
    df['h'] = df['h'].astype(float)
    df['l'] = df['l'].astype(float)
    df['o'] = df['o'].astype(float)
    return df

def calculate_rsi(df, period=14):
    delta = df['c'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def is_bullish_engulfing(df):
    return (
        df.iloc[-2]['c'] < df.iloc[-2]['o'] and
        df.iloc[-1]['c'] > df.iloc[-1]['o'] and
        df.iloc[-1]['c'] > df.iloc[-2]['o'] and
        df.iloc[-1]['o'] < df.iloc[-2]['c']
    )

def is_bearish_engulfing(df):
    return (
        df.iloc[-2]['c'] > df.iloc[-2]['o'] and
        df.iloc[-1]['c'] < df.iloc[-1]['o'] and
        df.iloc[-1]['c'] < df.iloc[-2]['o'] and
        df.iloc[-1]['o'] > df.iloc[-2]['c']
    )

def check_signals():
    global strong_signals, simple_signals, signals_per_coin, last_stat_time
    last_signal_time = datetime.utcnow()
    signals_found = False

    while True:
        print("▶️ Проверка сигналов...")
        signals_this_round = False

        for symbol in COINS:
            for tf in TIMEFRAMES:
                try:
                    df = get_klines(symbol, tf)
                    if len(df) < 2:
                        print(f"Мало данных для {symbol} {tf}")
                        continue

                    rsi = calculate_rsi(df).iloc[-1]

                    # Сигнал по паттерну и rsi
                    if is_bullish_engulfing(df) and rsi < 40:
                        bot.send_message(chat_id=CHAT_ID,
                            text=f'🟢 **СИЛЬНЫЙ BUY сигнал**: {symbol} ({tf})\nRSI = {rsi:.2f}\nПаттерн: бычье поглощение'
                        )
                        signals_found = True
                        signals_this_round = True
                        strong_signals += 1
                        signals_per_coin[symbol] += 1
                        print(f"СИЛЬНЫЙ BUY сигнал: {symbol} ({tf}), RSI={rsi:.2f}")

                    elif is_bearish_engulfing(df) and rsi > 60:
                        bot.send_message(chat_id=CHAT_ID,
                            text=f'🔴 **СИЛЬНЫЙ SELL сигнал**: {symbol} ({tf})\nRSI = {rsi:.2f}\nПаттерн: медвежье поглощение'
                        )
                        signals_found = True
                        signals_this_round = True
                        strong_signals += 1
                        signals_per_coin[symbol] += 1
                        print(f"СИЛЬНЫЙ SELL сигнал: {symbol} ({tf}), RSI={rsi:.2f}")

                    # Сигнал только по RSI
                    elif rsi < 30:
                        bot.send_message(chat_id=CHAT_ID,
                            text=f'🟢 BUY сигнал: {symbol} ({tf})\nТолько по RSI = {rsi:.2f}'
                        )
                        signals_found = True
                        signals_this_round = True
                        simple_signals += 1
                        signals_per_coin[symbol] += 1
                        print(f"BUY сигнал по RSI: {symbol} ({tf}), RSI={rsi:.2f}")

                    elif rsi > 70:
                        bot.send_message(chat_id=CHAT_ID,
                            text=f'🔴 SELL сигнал: {symbol} ({tf})\nТолько по RSI = {rsi:.2f}'
                        )
                        signals_found = True
                        signals_this_round = True
                        simple_signals += 1
                        signals_per_coin[symbol] += 1
                        print(f"SELL сигнал по RSI: {symbol} ({tf}), RSI={rsi:.2f}")

                except Exception as e:
                    print(f"Ошибка для {symbol} {tf}: {e}")
                    traceback.print_exc()

        now = datetime.utcnow()
        # Раз в час сообщение что нет сигналов
        if (now - last_signal_time > timedelta(hours=1)):
            if not signals_found:
                try:
                    bot.send_message(
                        chat_id=CHAT_ID,
                        text='ℹ️ За последний час не найдено сигналов.'
                    )
                    print("ℹ️ Сообщение об отсутствии сигналов отправлено.")
                except Exception as e:
                    print(f"Ошибка при отправке сообщения об отсутствии сигналов: {e}")
                    traceback.print_exc()
            last_signal_time = now
            signals_found = False  # Сбросить для следующего часа

        # Раз в сутки — статистика
        if (now - last_stat_time > timedelta(days=1)):
            try:
                coin_stats = '\n'.join([f'{coin}: {count}' for coin, count in sorted(signals_per_coin.items(), key=lambda x: -x[1])])
                stat_text = (
                    f"📊 Статистика за сутки:\n"
                    f"Сильных сигналов: {strong_signals}\n"
                    f"Обычных сигналов (только RSI): {simple_signals}\n"
                    f"По монетам:\n{coin_stats if coin_stats else 'Нет сигналов'}"
                )
                bot.send_message(chat_id=CHAT_ID, text=stat_text)
                print("Статистика за сутки отправлена")
            except Exception as e:
                print(f"Ошибка при отправке статистики: {e}")
                traceback.print_exc()
            # Сбросить статистику
            strong_signals = 0
            simple_signals = 0
            signals_per_coin = defaultdict(int)
            last_stat_time = now

        time.sleep(300)

threading.Thread(target=check_signals, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
