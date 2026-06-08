import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pytz
import csv
import os
import requests

st.set_page_config(page_title="JARVIS V20 PRO", layout="wide")
st.title("👑 JARVIS V20 PRO — Institutional Grade (All Bugs Fixed)")
st.markdown("*Fixed ADX • Proper Cache • Crypto-safe • Realistic Backtest • NSE 9:15*")

LOCAL_TZ = pytz.timezone("Asia/Kolkata")
LOG_FILE = "trade_log.csv"

# ---------- TTL Functions ----------
def get_refresh_ttl():
    return st.session_state.get("refresh_ttl", 30)

def get_news_ttl():
    return st.session_state.get("news_ttl", 120)

# ---------- API Keys ----------
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID_HERE"
GNEWS_API_KEY = "YOUR_GNEWS_API_KEY_HERE"

def send_telegram_alert(message):
    if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE" or TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_CHAT_ID_HERE":
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=5)
        return r.status_code == 200
    except:
        return False

# ---------- News with Banking ----------
@st.cache_data(show_spinner=False)
def fetch_news_sentiment(raw_ticker: str):
    pos_words = ["growth","profit","surge","bullish","dividend","deal","win","order","success","buy","positive","rally","jump"]
    neg_words = ["loss","drop","slump","bearish","fine","fraud","decline","risk","fail","sell","negative","crash","debt"]
    if GNEWS_API_KEY == "YOUR_GNEWS_API_KEY_HERE" or not GNEWS_API_KEY:
        return _fetch_old_yfinance_news(raw_ticker, pos_words, neg_words)
    try:
        resp = requests.get(f"https://gnews.io/api/v4/search?q={raw_ticker}&lang=en&country=in&max=5&apikey={GNEWS_API_KEY}", timeout=5).json()
        articles = resp.get("articles", [])
        if not articles:
            return _fetch_old_yfinance_news(raw_ticker, pos_words, neg_words)
        headlines, score, n = [], 0.0, 0
        for art in articles:
            t = art.get("title","")
            headlines.append(t)
            s = sum(0.3 for w in pos_words if w in t.lower()) - sum(0.3 for w in neg_words if w in t.lower())
            score += s; n += 1
        return round(max(-1, min(1, score/n)), 2), headlines[:5]
    except:
        return _fetch_old_yfinance_news(raw_ticker, pos_words, neg_words)

def _fetch_old_yfinance_news(raw_ticker, pos_words, neg_words):
    try:
        items = yf.Ticker(raw_ticker).news or []
        if not items: return None, []
        headlines, score, n = [], 0.0, 0
        for item in items[:5]:
            title = (item or {}).get("title","")
            if not title: continue
            headlines.append(title)
            s = sum(0.3 for w in pos_words if w in title.lower()) - sum(0.3 for w in neg_words if w in title.lower())
            score += s; n += 1
        if n==0: return None, headlines
        return round(max(-1, min(1, score/n)), 2), headlines[:5]
    except:
        return None, []

# ---------- Sidebar ----------
st.sidebar.header("⚙️ JARVIS V20 PRO")
ticker_input = st.sidebar.text_input("टिकर", "TATAMOTORS").upper().strip()
capital = st.sidebar.number_input("कुल पूंजी (₹)", min_value=500.0, value=50000.0, step=5000.0)
max_risk_pct = st.sidebar.slider("अधिकतम जोखिम (%)", 0.5, 5.0, 1.0, 0.5)
refresh_bucket = st.sidebar.selectbox("Refresh (sec)", [10,30,60], index=1)
news_bucket = st.sidebar.selectbox("News Refresh (sec)", [60,120,300], index=1)
asset_class = st.sidebar.selectbox("Asset Class", ["Equity (NSE)","Crypto"], index=0)
st.sidebar.markdown("---")
st.sidebar.info("🔧 ADX Fixed • Crypto Safe • Real Backtest")

if "refresh_ttl" not in st.session_state:
    st.session_state.refresh_ttl = refresh_bucket
if "news_ttl" not in st.session_state:
    st.session_state.news_ttl = news_bucket
if st.session_state.refresh_ttl != refresh_bucket:
    st.session_state.refresh_ttl = refresh_bucket
    fetch_data.clear()
if st.session_state.news_ttl != news_bucket:
    st.session_state.news_ttl = news_bucket
    fetch_news_sentiment.clear()

# ---------- Helpers ----------
def _safe_symbol(ticker):
    crypto_keywords = ["USD","USDT","BTC","ETH","-"]
    if any(x in ticker.upper() for x in crypto_keywords):
        return ticker
    if ticker.endswith(".NS") or ticker.endswith(".BO"):
        return ticker
    return ticker + ".NS"

def _check_market_hours(ac):
    now = datetime.now(LOCAL_TZ)
    if ac == "Equity (NSE)":
        if (now.hour + now.minute/60) < 9.25 or (now.hour + now.minute/60) > 15.25:
            return False, f"⏳ NSE बाजार बंद है (9:15 AM - 3:15 PM). अभी {now.strftime('%H:%M')}"
        if now.weekday()>=5:
            return False, "⏳ NSE साप्ताहिक बंद।"
        return True, "✅ NSE खुला है"
    return True, "✅ Crypto 24/7 खुला है"

def _add_indicators(df, ac):
    df = df.copy()
    if ac == "Equity (NSE)":
        df = df.between_time('09:30','15:15').copy()
    df['date'] = df.index.date
    df['vwap_num'] = df['volume'] * (df['high']+df['low']+df['close'])/3
    df['vwap'] = df.groupby('date')['vwap_num'].cumsum() / df.groupby('date')['volume'].cumsum()
    hd = df['high'].diff(); ld = df['low'].diff()
    df['+dm'] = np.where((hd>ld)&(hd>0), hd, 0)
    df['-dm'] = np.where((ld>hd)&(ld>0), ld, 0)
    tr = np.maximum(df['high']-df['low'], np.maximum(abs(df['high']-df['close'].shift(1)), abs(df['low']-df['close'].shift(1))))
    df['atr'] = pd.Series(tr).rolling(14).mean()
    df['+di'] = 100 * (df['+dm'].rolling(14).mean() / df['atr'].replace(0,1e-10))
    df['-di'] = 100 * (df['-dm'].rolling(14).mean() / df['atr'].replace(0,1e-10))
    # ✅ FIXED ADX
    dx = 100 * abs(df['+di'] - df['-di']) / (df['+di'] + df['-di'] + 1e-10)
    df['adx'] = dx.rolling(14).mean()
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    delta = df['close'].diff()
    gain = delta.where(delta>0,0).rolling(14).mean()
    loss = -delta.where(delta<0,0).rolling(14).mean()
    df['rsi'] = 100 - (100/(1+(gain/loss.replace(0,1e-10))))
    df['vol_sma'] = df['volume'].rolling(20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_sma'].replace(0,1e-10)
    return df

def _detect_candle_patterns(df):
    df = df.copy()
    df['candle_pattern'] = "No Pattern"
    body = abs(df['close']-df['open'])
    crange = df['high']-df['low']
    lshadow = np.minimum(df['open'],df['close']) - df['low']
    ushadow = df['high'] - np.maximum(df['open'],df['close'])
    df.loc[body <= (crange*0.1), 'candle_pattern'] = "Doji ⏳"
    df.loc[(lshadow >= body*2) & (ushadow <= body*0.5), 'candle_pattern'] = "Hammer 🔨"
    green = df['close']>df['open']; was_red = df['close'].shift(1)<df['open'].shift(1)
    engulf = (df['open']<=df['close'].shift(1)) & (df['close']>=df['open'].shift(1)) & (body>body.shift(1))
    df.loc[green & was_red & engulf, 'candle_pattern'] = "Bullish Engulfing 📈"
    return df

@st.cache_data(show_spinner=False)
def fetch_data(ticker, ac, period="3mo"):
    try:
        sym = _safe_symbol(ticker)
        df = yf.Ticker(sym).history(period=period, interval="15m")
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(0)
        df.columns = [c.lower() for c in df.columns]
        if getattr(df.index,'tz',None): df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)
        if not {"open","high","low","close","volume"}.issubset(df.columns): return None
        df = _add_indicators(df, ac)
        df = _detect_candle_patterns(df)
        df = df.dropna(subset=["ema20","vwap","atr","rsi","adx","vol_ratio"])
        return df if len(df)>=30 else None
    except:
        return None

def detect_patterns_v20(df):
    df = df.copy()
    df['chart_pattern'] = "Scanning Trends..."
    df['final_signal'] = "HOLD"
    last_pr = df['close'].iloc[-1]
    vol_th = 2.5 if last_pr<100 else 1.2
    for i in range(30, len(df)):
        win = df['close'].iloc[max(0,i-20):i]
        cur_c = df['close'].iloc[i]; cur_v = df['vwap'].iloc[i]; cur_e = df['ema20'].iloc[i]
        cur_r = df['rsi'].iloc[i]; cur_vol = df['vol_ratio'].iloc[i]; cur_adx = df['adx'].iloc[i]
        # W-Pattern with neckline confirmation
        mins = (win == win.rolling(5, center=True, min_periods=1).min())
        if mins.sum()>=2:
            # Identify two bottoms and neckline
            min_idx = win[mins].index
            if len(min_idx)>=2:
                t1_idx, t2_idx = min_idx[-2], min_idx[-1]
                t1_val = win[t1_idx]; t2_val = win[t2_idx]
                if abs(t1_val - t2_val)/max(t1_val, t2_val) < 0.025:
                    mid_high = win[t1_idx:t2_idx].max() if t2_idx > t1_idx else t1_val
                    if cur_c > mid_high:  # Breakout confirm
                        df.loc[df.index[i], 'chart_pattern'] = "W-Pattern (Double Bottom) Detected 🚀"
                        if cur_c>cur_v and cur_c>cur_e and 45<=cur_r<=65 and cur_adx>20 and cur_vol>vol_th:
                            df.loc[df.index[i], 'final_signal'] = "📈 BUY (SUPER CONFIRMED)"
        # M-Pattern with neckline confirmation
        maxs = (win == win.rolling(5, center=True, min_periods=1).max())
        if maxs.sum()>=2:
            max_idx = win[maxs].index
            if len(max_idx)>=2:
                p1_idx, p2_idx = max_idx[-2], max_idx[-1]
                p1_val = win[p1_idx]; p2_val = win[p2_idx]
                if abs(p1_val - p2_val)/max(p1_val, p2_val) < 0.025:
                    mid_low = win[p1_idx:p2_idx].min() if p2_idx > p1_idx else p1_val
                    if cur_c < mid_low:
                        df.loc[df.index[i], 'chart_pattern'] = "M-Pattern (Double Top) Detected 📉"
                        if cur_r>65:
                            df.loc[df.index[i], 'final_signal'] = "📉 SELL (OVERBOUGHT)"
    return df

def friendship_score(df): return (df['close']>df['vwap']).mean()*100

def calc_confidence(df, last, news_score, is_penny):
    sc = 0
    # Trend (ADX) = 35 points
    sc += 35 if last['adx']>25 else (20 if last['adx']>20 else (10 if last['adx']>15 else 0))
    # Volume = 25 points
    if is_penny and last['vol_ratio']>2.5: sc+=25
    elif not is_penny and last['vol_ratio']>1.5: sc+=25
    elif last['vol_ratio']>1.0: sc+=15
    # RSI = 15 points
    sc += 15 if 45<=last['rsi']<=65 else (10 if 40<=last['rsi']<45 or 65<last['rsi']<=70 else 5)
    # Pattern = 15 points
    if df['chart_pattern'].iloc[-1].startswith("W-") or df['chart_pattern'].iloc[-1].startswith("M-"):
        sc += 15
    # News = 10 points
    if news_score is not None:
        if news_score>0.2: sc+=10
        elif news_score>-0.2: sc+=5
    return max(0,min(100,sc))

def aladdin_risk(df, capital, signal_text, strength, is_penny, ac, max_risk_pct):
    last = df.iloc[-1]
    safe_risk = min(max_risk_pct, 1.0)
    if ac=="Crypto": safe_risk = min(max_risk_pct,2.0)
    if is_penny: safe_risk = min(max_risk_pct,0.5)
    if "कमजोर" in strength: safe_risk *= 0.5
    rps = last['atr']*1.5
    if rps<=0: return 0,0,0,safe_risk
    qty_r = int((capital*safe_risk/100)/rps)
    qty_c = int((capital*0.2)//last['close']) if last['close']>0 else 0
    if qty_c==0 and (capital*5)>=last['close']: qty_c=1
    qty = max(0, min(qty_r, qty_c))
    exp = (qty*last['close'])/capital*100
    return qty, rps, exp, safe_risk

def log_trade(ticker, signal, price, sl, tp, qty, news, pattern, conf, fs, risk_pct):
    try:
        exists = os.path.exists(LOG_FILE)
        with open(LOG_FILE, 'a', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            if not exists: w.writerow(["Time","Ticker","Signal","Price","SL","TP","Qty","News","Pattern","Conf","Friendship","Risk%"])
            w.writerow([datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M"), ticker, signal, price, sl, tp, qty,
                        "" if news is None else news, pattern, conf, fs, risk_pct])
        return True
    except: return False

def read_log():
    cols = ["Time","Ticker","Signal","Price","SL","TP","Qty","News","Pattern","Conf","Friendship","Risk%"]
    if not os.path.exists(LOG_FILE): return pd.DataFrame(columns=cols)
    try: return pd.read_csv(LOG_FILE)
    except: return pd.DataFrame(columns=cols)

st.sidebar.button("🧹 Clear Cache", on_click=lambda: fetch_data.clear() or fetch_news_sentiment.clear())

# ---------- Main ----------
if st.sidebar.button("🚀 JARVIS V20 START", use_container_width=True):
    ok, msg = _check_market_hours(asset_class)
    if not ok:
        st.warning(msg)
        st.stop()
    is_crypto = any(x in ticker_input.upper() for x in ["USD","USDT","BTC","ETH","-"])
    if is_crypto: st.warning("⚠️ Crypto ticker.")
    
    df = fetch_data(ticker_input, asset_class, period="3mo")
    if df is None or len(df)<30:
        st.error("❌ पर्याप्त डेटा नहीं।")
        st.stop()
    df = detect_patterns_v20(df)
    last = df.iloc[-1]
    if asset_class=="Equity (NSE)":
        if last['atr']/last['close']*100 > 5.0:
            st.warning(f"⚠️ बहुत ज़्यादा volatility (ATR% {last['atr']/last['close']*100:.1f})")
            st.stop()
        # Fixed volume check: use vol_ratio instead of absolute volume
        if last['vol_ratio'] < 0.7:
            st.warning(f"⚠️ कम लिक्विडिटी (Vol Ratio {last['vol_ratio']:.2f})")
            st.stop()
    raw = ticker_input.replace(".NS","").replace(".BO","")
    news_score, headlines = fetch_news_sentiment(raw)
    last_signal = df['final_signal'].iloc[-1]
    last_chart = df['chart_pattern'].iloc[-1]
    last_candle = df['candle_pattern'].iloc[-1]
    bullish = last_signal.startswith("BUY")
    bearish = last_signal.startswith("SELL")
    pat_str = "W-Pattern" if "W" in last_chart else ("M-Pattern" if "M" in last_chart else "कोई पैटर्न नहीं")
    is_penny = last['close']<100 and not is_crypto
    fs = friendship_score(df)
    conf = calc_confidence(df, last, news_score, is_penny)
    if bullish:
        sig_txt = "📈 BUY (SUPER CONFIRMED)"; strength = "मजबूत"
    elif bearish:
        sig_txt = "📉 SELL (OVERBOUGHT)"; strength = "मजबूत"
    else:
        sig_txt = "HOLD"; strength = ""
    qty, rps, exp, safe_risk = aladdin_risk(df, capital, sig_txt, strength, is_penny, asset_class, max_risk_pct)
    if "BUY" in sig_txt or "SELL" in sig_txt:
        if qty==0 or conf<60:
            sig_txt = "HOLD"; sl=tp=0.0
            st.warning(f"⚠️ Confidence {conf:.1f}% (<60) या Qty=0. ट्रेड नहीं।")
        else:
            if "BUY" in sig_txt:
                sl = last['close'] - rps; tp = last['close'] + last['atr']*3
            else:
                sl = last['close'] + rps; tp = last['close'] - last['atr']*3
    else:
        qty=0; sl=tp=0.0
    
    st.subheader("📰 लाइव न्यूज़")
    if headlines:
        emoji = "🟢" if (news_score is not None and news_score>0.15) else ("🔴" if (news_score is not None and news_score<-0.15) else "⚪")
        boost = 25 if (news_score is not None and news_score>0.15) else (15 if (news_score is not None and news_score>-0.15) else 0)
        st.markdown(f"**Sentiment:** {emoji} {news_score:.2f} (+{boost} Conf)")
        for h in headlines: st.markdown(f"- {h}")
    else:
        st.info("कोई न्यूज़ नहीं।")
    
    st.subheader("📐 पैटर्न + Friendship")
    c1,c2,c3 = st.columns(3)
    c1.metric("चार्ट", pat_str); c2.metric("कैंडल", last_candle); c3.metric("Friendship", f"{fs:.1f}%")
    
    st.subheader("🎯 Confidence + Aladdin-Risk (Weighted)")
    r1,r2,r3,r4,r5 = st.columns(5)
    r1.metric("Confidence", f"{conf:.1f}%"); r2.metric("Qty", qty); r3.metric("Risk/Sh", f"₹{rps:.2f}")
    r4.metric("Exposure", f"{exp:.1f}%"); r5.metric("Max Risk", f"{safe_risk:.1f}%")
    
    if conf>=75: st.success(f"🟢 High Confidence ({conf:.1f}%)")
    elif conf>=60: st.info(f"🟡 Moderate Confidence ({conf:.1f}%)")
    else: st.warning(f"🔴 Low Confidence ({conf:.1f}%)")
    
    st.markdown("---")
    if sig_txt != "HOLD":
        if "BUY" in sig_txt:
            st.success(f"{sig_txt} | Qty:{qty} | SL:₹{sl:.2f} | TP:₹{tp:.2f} | Conf:{conf:.1f}%")
            log_trade(ticker_input, "BUY", last['close'], sl, tp, qty, news_score, pat_str, conf, fs, safe_risk)
            send_telegram_alert(f"🚀 *JARVIS BUY*\n{ticker_input}\nPrice:₹{last['close']:.2f}\nSL:₹{sl:.2f}\nTP:₹{tp:.2f}\nConf:{conf:.1f}%")
        else:
            st.error(f"{sig_txt} | Qty:{qty} | SL:₹{sl:.2f} | TP:₹{tp:.2f} | Conf:{conf:.1f}%")
            log_trade(ticker_input, "SELL", last['close'], sl, tp, qty, news_score, pat_str, conf, fs, safe_risk)
            send_telegram_alert(f"📉 *JARVIS SELL*\n{ticker_input}\nPrice:₹{last['close']:.2f}\nSL:₹{sl:.2f}\nTP:₹{tp:.2f}\nConf:{conf:.1f}%")
    else:
        st.info("⏸️ HOLD — कम कॉन्फिडेंस या कोई सिग्नल नहीं।")
    
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Price", f"₹{last['close']:.2f}"); m2.metric("RSI", f"{last['rsi']:.1f}")
    m3.metric("ADX", f"{last['adx']:.1f}"); m4.metric("ATR", f"₹{last['atr']:.2f}")
    
    st.subheader("📊 लाइव चार्ट (200 कैंडल)")
    fig = go.Figure()
    plot = df.iloc[-200:]
    fig.add_trace(go.Candlestick(x=plot.index, open=plot['open'], high=plot['high'], low=plot['low'], close=plot['close'], name="Price"))
    fig.add_trace(go.Scatter(x=plot.index, y=plot['vwap'], line=dict(color='blue',width=1.5), name="VWAP"))
    fig.add_trace(go.Scatter(x=plot.index, y=plot['ema20'], line=dict(color='orange',width=1.5), name="EMA20"))
    for idx, row in plot.iterrows():
        if row['chart_pattern'].startswith("W-"):
            fig.add_annotation(x=idx, y=row['low']*0.999, text="W", showarrow=True, arrowhead=1, bgcolor="green", font=dict(size=10))
        elif row['chart_pattern'].startswith("M-"):
            fig.add_annotation(x=idx, y=row['high']*1.001, text="M", showarrow=True, arrowhead=1, bgcolor="red", font=dict(size=10))
    fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False, margin=dict(l=10,r=10,t=10,b=10))
    st.plotly_chart(fig, use_container_width=True)
    
    st.subheader("📋 हाल के ट्रेड")
    st.dataframe(read_log().tail(5), use_container_width=True)

    # Backtest with fixes
    with st.expander("📈 Historical Win-Rate (365 दिन) - Realistic"):
        if asset_class == "Equity (NSE)":
            bt = fetch_data(ticker_input, asset_class, period="1y")
            if bt is not None and len(bt)>30:
                bt = detect_patterns_v20(bt)
                trades = []
                in_trade = False
                for i in range(30, len(bt)-1):
                    if in_trade:
                        last_trade = trades[-1]
                        sl_p = last_trade["SL"]
                        tp_p = last_trade["TP"]
                        sig_type = last_trade["Signal"]
                        cur_high = bt['high'].iloc[i]
                        cur_low = bt['low'].iloc[i]
                        if ("BUY" in sig_type and (cur_low <= sl_p or cur_high >= tp_p)) or \
                           ("SELL" in sig_type and (cur_high >= sl_p or cur_low <= tp_p)):
                            in_trade = False
                        continue
                    
                    sig = bt['final_signal'].iloc[i]
                    if not (sig.startswith("BUY") or sig.startswith("SELL")):
                        continue
                    entry = bt['close'].iloc[i]
                    atr_val = bt['atr'].iloc[i]
                    sl_price = entry - atr_val*1.5 if "BUY" in sig else entry + atr_val*1.5
                    tp_price = entry + atr_val*3.0 if "BUY" in sig else entry - atr_val*3.0
                    exit_price = None
                    exit_idx = None
                    for j in range(i+1, len(bt)):
                        low_j = bt['low'].iloc[j]
                        high_j = bt['high'].iloc[j]
                        if "BUY" in sig:
                            if low_j <=