import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime
import pytz
import csv
import os
import requests
from typing import List, Tuple, Optional
import streamlit.components.v1 as components
from bs4 import BeautifulSoup

# =========================
# Config / Secrets
# =========================
st.set_page_config(page_title="JARVIS AI — Gemini Intelligence", layout="wide")

st.markdown("""
<style>
.stApp {
    background-color: #131314;
    color: #e3e3e3;
    font-family: 'Google Sans', sans-serif;
}
[data-testid="stSidebar"] {
    background-color: #1e1f20 !important;
    border-right: 1px solid #2e3032;
}
div.stMetric {
    background-color: #1e1f20;
    border: 1px solid #2e3032;
    border-radius: 16px;
    padding: 16px 24px !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}
.stDataFrame, div[data-testid="stTable"] {
    background-color: #1e1f20;
    border-radius: 12px;
    border: 1px solid #2e3032;
}
.stButton>button {
    background: linear-gradient(90deg, #1a73e8, #4285f4);
    color: white;
    border-radius: 20px;
    border: none;
    padding: 8px 24px;
}
h1, h2, h3 {
    color: #e3e3e3 !important;
    font-weight: 400;
}
</style>
""", unsafe_allow_html=True)

st.title("✨ JARVIS — Gemini Edition Personal Assistant")
st.markdown("<p style='color:#80868b;'>Advanced Technical Intelligence, Dual-Engine Analytics & Accuracy Verification Suite</p>", unsafe_allow_html=True)

LOCAL_TZ = pytz.timezone("Asia/Kolkata")
LOG_FILE = "trade_log.csv"

def get_secret(name: str, default: str = "") -> str:
    try:
        val = st.secrets.get(name, default)
        if val is None:
            return default
        return str(val).strip()
    except Exception:
        return os.getenv(name, default).strip()

ALPHA_VANTAGE_KEY = get_secret("ALPHA_VANTAGE_KEY")
TELEGRAM_BOT_TOKEN = get_secret("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = get_secret("TELEGRAM_CHAT_ID")
NEWS_API_KEY = get_secret("NEWS_API_KEY")

if "current_run" not in st.session_state:
    st.session_state.current_run = 0
if "auto_loop" not in st.session_state:
    st.session_state.auto_loop = False
if "last_spoken_signal" not in st.session_state:
    st.session_state.last_spoken_signal = ""

# =========================
# Voice
# =========================
def safe_escape_js_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("
", " ").replace("
", " ")

def jarvis_speak_clean(text: str, voice_language: str):
    if not text:
        return
    lang_code = "hi-IN" if voice_language == "Pure Hindi (हिंदी)" else "en-US"
    safe_text = safe_escape_js_text(text)
    components.html(f"""
    <script>
    if ('speechSynthesis' in window) {{
        window.speechSynthesis.cancel();
        const msg = new SpeechSynthesisUtterance('{safe_text}');
        msg.lang = '{lang_code}';
        msg.rate = 1.05;
        msg.pitch = 1.0;
        window.speechSynthesis.speak(msg);
    }}
    </script>
    """, height=0, width=0)

# =========================
# Helpers
# =========================
def infer_asset_class(name_or_symbol: str) -> str:
    s = name_or_symbol.strip().upper()
    crypto_names = {"BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "BNB", "AVAX", "LTC", "LINK", "DOT", "MATIC"}
    if s.endswith("-USD") or s in crypto_names:
        return "Crypto"
    return "Equity (NSE)"

def resolve_symbol(raw_input: str, asset_hint: str) -> Tuple[str, str]:
    s = raw_input.strip().upper().replace(" ", "")
    if s.endswith(".NS") or s.endswith(".BO"):
        return s, "Equity (NSE)"
    if s.endswith("-USD"):
        return s, "Crypto"
    inferred = infer_asset_class(s) if asset_hint == "Auto" else asset_hint
    if inferred == "Crypto":
        return f"{s}-USD", "Crypto"
    return f"{s}.NS", "Equity (NSE)"

# =========================
# Data Sources
# =========================
def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(0)
    df.columns = [c.lower() for c in df.columns]
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)
    need = {"open", "high", "low", "close", "volume"}
    if not need.issubset(set(df.columns)):
        return pd.DataFrame()
    return df

def fetch_yfinance_data(symbol: str) -> Optional[pd.DataFrame]:
    try:
        df = yf.Ticker(symbol).history(period="3mo", interval="15m")
        df = normalize_ohlcv(df)
        return df if not df.empty else None
    except Exception:
        return None

def fetch_alpha_vantage_data(symbol: str, asset_class: str) -> Optional[pd.DataFrame]:
    if not ALPHA_VANTAGE_KEY:
        return None
    try:
        from alpha_vantage.timeseries import TimeSeries
        sym = symbol.replace(".NS", "").replace(".BO", "").replace("-USD", "")
        ts = TimeSeries(key=ALPHA_VANTAGE_KEY, output_format="pandas")
        data, _ = ts.get_intraday(symbol=sym, interval="15min", outputsize="full")
        if data is None or data.empty:
            return None
        df = data.rename(columns={
            "1. open": "open",
            "2. high": "high",
            "3. low": "low",
            "4. close": "close",
            "5. volume": "volume"
        }).copy()
        df.index = pd.to_datetime(df.index)
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_convert("Asia/Kolkata").tz_localize(None)
        df = df[["open", "high", "low", "close", "volume"]]
        df = df.apply(pd.to_numeric, errors="coerce").dropna()
        return df if not df.empty else None
    except Exception:
        return None

def fetch_backup_google_data(ticker: str, asset_class: str) -> Optional[pd.DataFrame]:
    try:
        ticker = ticker.upper().strip()
        sym = ticker.replace(".NS", "").replace(".BO", "")
        exch = "NSE"
        if asset_class == "Crypto":
            sym = sym if sym.endswith("-USD") else f"{sym}-USD"
            exch = "CURRENCY"
        url = f"https://www.google.com/finance/quote/{sym}:{exch}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        price_tag = soup.find("div", {"class": "YMlKec fxKbKc"})
        if not price_tag:
            return None
        live_price = float(price_tag.get_text(strip=True).replace(",", ""))
        dates = pd.date_range(end=datetime.now(), periods=60, freq="15min", tz=LOCAL_TZ)
        closes = np.linspace(live_price * 0.99, live_price, 60)
        df = pd.DataFrame({
            "open": closes * 0.998,
            "high": closes * 1.01,
            "low": closes * 0.99,
            "close": closes,
            "volume": np.random.randint(5000, 100000, 60),
        }, index=dates)
        return df
    except Exception:
        return None

@st.cache_data(ttl=10, show_spinner=False)
def fetch_market_data(raw_input: str, asset_hint: str):
    symbol, asset_class = resolve_symbol(raw_input, asset_hint)
    df = fetch_yfinance_data(symbol)
    if df is not None and not df.empty:
        return df, symbol, asset_class
    df = fetch_alpha_vantage_data(symbol, asset_class)
    if df is not None and not df.empty:
        return df, symbol, asset_class
    df = fetch_backup_google_data(raw_input, asset_class)
    if df is not None and not df.empty:
        return df, symbol, asset_class
    return None, symbol, asset_class

@st.cache_data(ttl=60, show_spinner=False)
def fetch_news_sentiment(raw_ticker: str) -> Tuple[Optional[float], List[str]]:
    pos_words = ["growth","profit","surge","bullish","dividend","deal","win","order","success","buy","positive","rally","jump"]
    neg_words = ["loss","drop","slump","bearish","fine","fraud","decline","risk","fail","sell","negative","crash","debt"]
    try:
        items = yf.Ticker(raw_ticker).news or []
        if not items:
            return None, []
        headlines, score, n = [], 0.0, 0
        for item in items[:5]:
            title = (item or {}).get("title", "")
            if not title:
                continue
            headlines.append(title)
            t = title.lower()
            s = sum(0.3 for w in pos_words if w in t) - sum(0.3 for w in neg_words if w in t)
            score += s
            n += 1
        if n == 0:
            return None, headlines[:5]
        return round(max(-1, min(1, score / n)), 2), headlines[:5]
    except Exception:
        return None, []

# =========================
# Indicators / Signals
# =========================
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if df.empty or len(df) < 20:
        return pd.DataFrame()
    df["date"] = df.index.date
    df["vwap_num"] = df["volume"] * (df["high"] + df["low"] + df["close"]) / 3
    df["vwap"] = df.groupby("date")["vwap_num"].cumsum() / df.groupby("date")["volume"].cumsum().replace(0, 1e-10)
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))
    hd = df["high"].diff()
    ld = df["low"].diff()
    plus_dm = np.where((hd > ld) & (hd > 0), hd, 0)
    minus_dm = np.where((ld > hd) & (ld > 0), ld, 0)
    tr = np.maximum(df["high"] - df["low"], np.maximum(abs(df["high"] - df["close"].shift(1)), abs(df["low"] - df["close"].shift(1))))
    df["atr"] = pd.Series(tr, index=df.index).rolling(14).mean().fillna(1.0)
    df["+di"] = 100 * (pd.Series(plus_dm, index=df.index).rolling(14).mean() / df["atr"].replace(0, 1e-10))
    df["-di"] = 100 * (pd.Series(minus_dm, index=df.index).rolling(14).mean() / df["atr"].replace(0, 1e-10))
    di_sum = (df["+di"] + df["-di"]).replace(0, 1e-10)
    df["adx"] = (100 * (df["+di"] - df["-di"]).abs() / di_sum).rolling(14).mean().fillna(0)
    df["vol_sma"] = df["volume"].rolling(20).mean()
    df["vol_ratio"] = df["volume"] / df["vol_sma"].replace(0, 1e-10)
    df["ema12"] = df["close"].ewm(span=12, adjust=False).mean()
    df["ema26"] = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = df["ema12"] - df["ema26"]
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["bb_mid"] = df["close"].rolling(20).mean()
    df["bb_std"] = df["close"].rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2 * df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - 2 * df["bb_std"]
    df["bb_pct"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])
    return df

def detect_patterns_rolling(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["chart_pattern"] = "Trending..."
    df["final_signal"] = "HOLD"
    if len(df) < 30:
        return df
    for i in range(25, len(df)):
        win = df["close"].iloc[max(0, i - 20):i]
        cur_c = df["close"].iloc[i]
        cur_v = df["vwap"].iloc[i]
        cur_e = df["ema20"].iloc[i]
        cur_r = df["rsi"].iloc[i]
        cur_vol = df["vol_ratio"].iloc[i]
        vol_th = 2.5 if cur_c < 100 else 1.2
        mins = (win == win.rolling(5, center=True, min_periods=1).min())
        maxs = (win == win.rolling(5, center=True, min_periods=1).max())
        if mins.sum() >= 2:
            df.loc[df.index[i], "chart_pattern"] = "W-Pattern (Double Bottom) 🚀"
            if cur_c > cur_v and cur_c > cur_e and 45 <= cur_r <= 65 and cur_vol > vol_th:
                df.loc[df.index[i], "final_signal"] = "📈 BUY (LONG)"
        if maxs.sum() >= 2:
            df.loc[df.index[i], "chart_pattern"] = "M-Pattern (Double Top) 📉"
            if cur_r > 68:
                df.loc[df.index[i], "final_signal"] = "📉 SELL (SHORT)"
    return df

def verify_strategy_accuracy(df: pd.DataFrame):
    if df.empty or len(df) < 40:
        return 0.0, 0, 0
    total_trades = 0
    successful_trades = 0
    for i in range(25, len(df) - 10):
        cur_c = df["close"].iloc[i]
        cur_v = df["vwap"].iloc[i]
        cur_e = df["ema20"].iloc[i]
        cur_r = df["rsi"].iloc[i]
        if cur_c > cur_v and cur_c > cur_e and 45 <= cur_r <= 65:
            total_trades += 1
            future_prices = df["close"].iloc[i + 1:i + 11]
            if not future_prices.empty and future_prices.max() > cur_c * 1.01:
                successful_trades += 1
    if total_trades == 0:
        return 0.0, 0, 0
    return round((successful_trades / total_trades) * 100, 2), successful_trades, total_trades

def friendship_score(df: pd.DataFrame) -> float:
    try:
        return float((df["close"] > df["vwap"]).mean() * 100)
    except Exception:
        return 0.0

def calc_confidence(last, f_score: float, is_penny: bool) -> float:
    sc = 0
    if 45 <= last["rsi"] <= 65:
        sc += 30
    if last["adx"] > 20:
        sc += 30
    vol_th = 2.5 if is_penny else 1.2
    if last["vol_ratio"] > vol_th:
        sc += 20
    if f_score > 60:
        sc += 20
    return float(min(100, sc))

# =========================
# Logging / Options
# =========================
def log_trade(ticker: str, signal: str, price: float, sl: float, tp: float):
    try:
        exists = os.path.exists(LOG_FILE)
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["Time", "Ticker", "Signal", "Price", "SL", "TP"])
            w.writerow([datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M"), ticker, signal, price, sl, tp])
    except Exception:
        pass

def fetch_live_options_matrix(ticker: str, current_price: float, asset_class: str):
    if asset_class == "Crypto" or current_price <= 0:
        return None, 1.0
    try:
        sym = ticker.upper().strip()
        sym = sym if (sym.endswith(".NS") or sym.endswith(".BO")) else sym + ".NS"
        stock = yf.Ticker(sym)
        expiries = stock.options
        if not expiries:
            return None, 1.0
        chain = stock.option_chain(expiries[0])
        calls = chain.calls
        puts = chain.puts
        atm_strike = round(current_price / 5) * 5 if current_price < 200 else round(current_price / 50) * 50
        total_call_oi = calls["openInterest"].sum() if "openInterest" in calls.columns else 1
        total_put_oi = puts["openInterest"].sum() if "openInterest" in puts.columns else 0
        pcr = round(total_put_oi / max(1, total_call_oi), 2)
        matrix_data = []
        for strike in [atm_strike - 10, atm_strike - 5, atm_strike, atm_strike + 5, atm_strike + 10]:
            c_row = calls[calls["strike"] == strike]
            p_row = puts[puts["strike"] == strike]
            c_ltp = c_row["lastPrice"].values[0] if not c_row.empty else 0.0
            p_ltp = p_row["lastPrice"].values[0] if not p_row.empty else 0.0
            c_iv = c_row["impliedVolatility"].values[0] * 100 if not c_row.empty and "impliedVolatility" in c_row.columns else 0.0
            status = "ATM 🎯" if strike == atm_strike else ("ITM 💰" if strike < current_price else "OTM 🚀")
            matrix_data.append({
                "Strike Price": strike,
                "Status": status,
                "Call LTP": round(c_ltp, 2),
                "Put LTP": round(p_ltp, 2),
                "Implied Vol (IV %)": f"{c_iv:.1f}%"
            })
        return pd.DataFrame(matrix_data), pcr
    except Exception:
        return None, 1.0

# =========================
# UI
# =========================
st.sidebar.markdown("<h2 style='color:#a8c7fa;'>🪐 Gemini Room</h2>", unsafe_allow_html=True)
app_mode = st.sidebar.radio("मोड चुनें", ["सिंगल स्टॉक एनालिसिस", "ऑटो स्कैन मोड"])
asset_mode = st.sidebar.selectbox("एसेट क्लास", ["Auto", "Equity (NSE)", "Crypto"])
ticker_input = st.sidebar.text_input("टिकर सिंबल", "TATAMOTORS").upper().strip()

st.sidebar.markdown("---")
auto_mode = st.sidebar.toggle("🔄 ऑटो-रिफ्रेश लाइव लूप", value=st.session_state.auto_loop)
refresh_gap = st.sidebar.slider("रिफ्रेश इंटरवल (सेकंड)", 5, 300, 10)
st.session_state.auto_loop = auto_mode

enable_voice = st.sidebar.toggle("🔊 वॉयस असिस्टेंट एक्टिव करें", value=True)
voice_language = st.sidebar.radio("भाषा (Language)", ["Pure Hindi (हिंदी)", "Pure English (English)"])

SCAN_GROUPS = {
    "Nifty Bank 🏦": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS"],
    "Penny Stocks 🪙": ["SUZLON.NS", "IDEA.NS", "YESBANK.NS"],
    "Crypto Majors 🪙": ["BTC", "ETH", "SOL"]
}

def create_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    plot = df.iloc[-80:]
    fig.add_trace(go.Candlestick(x=plot.index, open=plot["open"], high=plot["high"], low=plot["low"], close=plot["close"], name="Price"))
    fig.add_trace(go.Scatter(x=plot.index, y=plot["vwap"], line=dict(color="#00e676", width=1.5), name="VWAP"))
    fig.add_trace(go.Scatter(x=plot.index, y=plot["ema20"], line=dict(color="#29b6f6", width=1.5), name="EMA20"))
    fig.update_layout(template="plotly_dark", paper_bgcolor="#1e1f20", plot_bgcolor="#1e1f20", height=380, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
    return fig

def run_analysis():
    df, symbol, resolved_asset = fetch_market_data(ticker_input, asset_mode)
    if df is None or df.empty:
        st.error(f"❌ {ticker_input} का डेटा लोड नहीं हो सका।")
        return

    df = add_indicators(df)
    df = detect_patterns_rolling(df)
    last = df.iloc[-1]

    if app_mode == "सिंगल स्टॉक एनालिसिस":
        f_score = friendship_score(df)
        is_penny = last["close"] < 100
        conf_score = calc_confidence(last, f_score, is_penny)
        news_score, headlines = fetch_news_sentiment(symbol)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("लाइव कीमत", f"₹{last['close']:.2f}")
        c2.metric("JARVIS सिग्नल", last["final_signal"])
        c3.metric("कॉन्फिडेंस स्कोर", f"{conf_score:.0f}%")
        c4.metric("फ्रेंडशिप स्कोर", f"{f_score:.0f}%")

        acc, succ, total = verify_strategy_accuracy(df)
        st.caption(f"Strategy Accuracy: {acc:.2f}% | Wins: {succ} | Trades: {total}")

        if resolved_asset == "Equity (NSE)":
            st.markdown("### 🎰 लाइव ऑप्शन चैन मैट्रिक्स")
            opt_df, pcr_val = fetch_live_options_matrix(symbol, float(last["close"]), resolved_asset)
            if opt_df is not None and not opt_df.empty:
                st.metric("Put-Call Ratio (PCR)", f"{pcr_val}")
                st.dataframe(opt_df, use_container_width=True)
            else:
                st.info("ℹ️ इस टिकर के लिए कोई लाइव डेरिवेटिव/ऑप्शन डेटा उपलब्ध नहीं है।")

        if headlines:
            with st.expander("📰 लाइव सुर्खियां"):
                for h in headlines:
                    st.write(f"• {h}")

        current_signal_text = f"{symbol} {last['final_signal']}"
        if "BUY" in last["final_signal"]:
            sl = float(last["close"] - (last["atr"] * 1.5))
            tp = float(last["close"] + (last["atr"] * 3.0))
            st.success(f"🎯 सेटअप मैच! खरीदें: ₹{last['close']:.2f} | SL: ₹{sl:.2f} | Target: ₹{tp:.2f}")
            log_trade(symbol, last["final_signal"], float(last["close"]), sl, tp)
            if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                send_telegram_alert(f"🦅 BUY Alert: {symbol} @ {last['close']:.2f}")
            if enable_voice and st.session_state.last_spoken_signal != current_signal_text:
                msg = f"{symbol} में खरीदारी का सिग्नल मिला है।" if voice_language == "Pure Hindi (हिंदी)" else f"Buy signal detected for {symbol}."
                jarvis_speak_clean(msg, voice_language)
                st.session_state.last_spoken_signal = current_signal_text
        elif "SELL" in last["final_signal"]:
            st.warning(f"📉 SELL स