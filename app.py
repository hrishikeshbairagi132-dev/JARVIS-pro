import streamlit as st
import pandas as pd
from nsetools import Nse
import requests
import plotly.graph_objects as go

# 1. पेज कॉन्फ़िगरेशन
st.set_page_config(page_title="JARVIS PRO", layout="wide")
st.title("✨ JARVIS PRO - Stable Engine")

# 2. सुरक्षित फंक्शन - यह कभी क्रैश नहीं होगा
def get_live_data(ticker):
    # इंजन 1: NSE
    try:
        nse = Nse()
        data = nse.get_quote(ticker)
        if data and 'lastPrice' in data:
            return pd.DataFrame([data]), "NSE"
    except:
        pass
    
    # इंजन 2: Alpha Vantage (बैकअप)
    try:
        key = st.secrets.get("ALPHA_VANTAGE_KEY")
        if key:
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}.BSE&apikey={key}"
            res = requests.get(url, timeout=5).json()
            if "Global Quote" in res:
                return pd.DataFrame([res["Global Quote"]]), "AlphaVantage"
    except:
        pass
    return None, None

# 3. मेन UI
ticker = st.text_input("स्टॉक सिंबल लिखें (जैसे TATAMOTORS):", "TATAMOTORS")

if st.button("एनालाइज करें"):
    with st.spinner("प्रोसेसिंग..."):
        df, source = get_live_data(ticker)
        if df is not None:
            st.success(f"डेटा मिला (स्रोत: {source})")
            st.dataframe(df, use_container_width=True)
        else:
            st.error("डेटा नहीं मिला। सिंबल चेक करें या इंटरनेट कनेक्शन देखें।")
