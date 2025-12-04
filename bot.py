import time, requests, traceback
import pandas as pd, numpy as np
from datetime import datetime, timezone
import sqlite3
from okx import MarketAPI
from telebot import TeleBot
from config import *

# ===== Telegram =====
bot = TeleBot(TELEGRAM_BOT_TOKEN)

def send_telegram(text: str):
    if PAPER_MODE:
        print("[PAPER] Telegram message suppressed:\n", text)
        return True
    try:
        bot.send_message(TELEGRAM_CHAT_ID, text, parse_mode="HTML")
        return True
    except Exception as e:
        print("Telegram exception:", e)
        return False

# ===== При запуске бот сразу сообщает =====
send_telegram("🚀 Бот запущен и работает!")

# ===== Обработчик команды /start =====
@bot.message_handler(commands=['start'])
def start_command(message):
    bot.reply_to(message, "✅ Бот работает, сигналы включены!")

# ====== База данных для сигналов ======
conn = sqlite3.connect("signals.db", check_same_thread=False)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS sent_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                timeframe TEXT,
                direction TEXT,
                entry REAL,
                confidence INTEGER,
                sent_at INTEGER
            )""")
conn.commit()

def record_sent(symbol, tf, direction, entry, confidence):
    ts = int(time.time())
    c.execute("INSERT INTO sent_signals (symbol,timeframe,direction,entry,confidence,sent_at) VALUES (?,?,?,?,?,?)",
              (symbol, tf, direction, entry, confidence, ts))
    conn.commit()

def last_sent_for(symbol, tf, direction):
    cur = c.execute("SELECT entry, sent_at FROM sent_signals WHERE symbol=? AND timeframe=? AND direction=? ORDER BY sent_at DESC LIMIT 1",
                    (symbol, tf, direction))
    return cur.fetchone()

# ====== Методы анализа ======
def ema(s: pd.Series, n: int):
    return s.ewm(span=n, adjust=False).mean()

def rsi(s: pd.Series, n: int = 14):
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(alpha=1/n, adjust=False).mean()
    ma_down = down.ewm(alpha=1/n, adjust=False).mean()
    rs = ma_up / (ma_down + 1e-10)
    return 100 - (100 / (1 + rs))

def macd(series: pd.Series, fast=12, slow=26, sig=9):
    ef = ema(series, fast)
    es = ema(series, slow)
    mc = ef - es
    sl = mc.ewm(span=sig, adjust=False).mean()
    return mc, sl, mc - sl

def atr(df: pd.DataFrame, n: int = 14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def analyze_df(df):
    out = {'signal':'HOLD','confidence':0,'entry':None,'stop':None,'take1':None,'take2':None,'leverage':1}
    if df is None or len(df)<80: return out
    c = df['close']
    ema20, ema50, ema200 = ema(c,20), ema(c,50), ema(c,200)
    r = rsi(c,14)
    atr_val = atr(df,14).iloc[-1]
    macd_line, mac_sig, mac_hist = macd(c)
    if np.isnan(atr_val) or atr_val<=0: return out

    score, short_score = 0,0
    if (ema20.iloc[-2]<=ema50.iloc[-2] and ema20.iloc[-1]>ema50.iloc[-1]) and c.iloc[-1]>ema200.iloc[-1] and mac_hist.iloc[-1]>0 and r.iloc[-1]>30 and r.iloc[-1]<80:
        score+=40
    if (ema20.iloc[-2]>=ema50.iloc[-2] and ema20.iloc[-1]<ema50.iloc[-1]) and c.iloc[-1]<ema200.iloc[-1] and mac_hist.iloc[-1]<0 and r.iloc[-1]<70 and r.iloc[-1]>20:
        short_score+=40

    if score>=MIN_CONFIDENCE and score>=short_score: out['signal']='LONG'; out['confidence']=int(score)
    elif short_score>=MIN_CONFIDENCE and short_score>score: out['signal']='SHORT'; out['confidence']=int(short_score)
    else: out['signal']='HOLD'; out['confidence']=int(max(score,short_score))

    if out['signal']=='HOLD': return out

    last_price = float(c.iloc[-1])
    stop_dist = atr_val*1.5
    if out['signal']=='LONG':
        stop = last_price-stop_dist
        take1 = last_price+stop_dist*1.5
        take2 = last_price+stop_dist*3.0
    else:stop = last_price+stop_dist
        take1 = last_price-stop_dist*1.5
        take2 = last_price-stop_dist*3.0
    out.update({'entry':round(last_price,8),'stop':round(stop,8),'take1':round(take1,8),'take2':round(take2,8)})

    lev = 1
    if out['confidence']>75: lev=5
    elif out['confidence']>65: lev=3
    elif out['confidence']>55: lev=2
    out['leverage']=lev

    return out

# ====== OKX API ======
market = MarketAPI(API_KEY, API_SECRET, API_PASSPHRASE, flag='0')

def fetch_ohlcv(symbol, timeframe='1h', limit=200):
    try:
        data = market.get_candlesticks(symbol, timeframe, limit)
        df = pd.DataFrame(data['data'], columns=['ts','open','high','low','close','vol'])
        df = df.astype(float)
        df['ts'] = pd.to_datetime(df['ts'], unit='ms')
        df.set_index('ts', inplace=True)
        return df
    except:
        return None

def fetch_top_symbols(n=50):
    tickers = market.get_ticker()
    symbols = [t['instId'] for t in tickers['data'] if t['instId'].endswith("USDT")]
    return symbols[:n]

def format_msg(symbol, tf, analysis):
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    return (
        f"💹 <b>Сигнал</b>\n"
        f"<b>Монета:</b> {symbol}\n"
        f"<b>ТФ:</b> {tf}\n"
        f"<b>Направление:</b> {analysis['signal']}\n"
        f"<b>Вход:</b> {analysis['entry']}\n"
        f"<b>Стоп:</b> {analysis['stop']}\n"
        f"<b>Тейк1:</b> {analysis['take1']}\n"
        f"<b>Тейк2:</b> {analysis['take2']}\n"
        f"<b>Плечо:</b> {analysis['leverage']}x\n"
        f"<b>Уверенность:</b> {analysis['confidence']}%\n"
        f"<i>Время: {ts}</i>\n\n⚠️ Проверяй риск-менеджмент."
    )

# ====== MAIN LOOP ======
def main_loop():
    short_tf, long_tf = TIMEFRAMES[0], TIMEFRAMES[1]
    print("SMART SIGNAL BOT START (PAPER_MODE={})".format(PAPER_MODE))
    while True:
        try:
            symbols = fetch_top_symbols(TOP_N)
            for sym in symbols:
                df_short = fetch_ohlcv(sym, short_tf, limit=400)
                df_long = fetch_ohlcv(sym, long_tf, limit=400)
                if df_short is None or df_long is None: continue
                analysis_short = analyze_df(df_short)
                analysis_long = analyze_df(df_long)

                if analysis_short['signal'] in ('LONG','SHORT') and analysis_short['signal']==analysis_long['signal']:
                    final_conf = min(analysis_short['confidence'],analysis_long['confidence'])
                    analysis = analysis_short.copy(); analysis['confidence']=final_conf
                    entry = analysis['entry']
                    if final_conf>=MIN_CONFIDENCE and True:  # can_send_again simplified
                        msg = format_msg(sym,f"{short_tf}/{long_tf}",analysis)
                        ok = send_telegram(msg)
                        if ok: record_sent(sym, short_tf, analysis['signal'], entry, final_conf)
            time.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:
            print("Interrupted by user")
            break
        except Exception as e:
            print("MAIN LOOP EXCEPTION:", e)
            traceback.print_exc()
            time.sleep(5)

if __name__=="__main__":
    import threading
    # Запуск Telegram бота в отдельном потоке
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    # Запуск основного цикла сигналов
    main_loop()
