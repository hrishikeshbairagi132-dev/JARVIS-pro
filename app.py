import streamlit as st
import pandas as pd
from nsetools import Nse
import requests
import plotly.graph_objects as go

# 1. पेज कॉन्फ़िगरेशन
st.set_page_config(page_title="JARVIS PRO - Production Engine", layout="wide")
st.title("✨ JARVIS PRO — Trading Suite")

# 2. सुरक्षित तरीके से की लोड करें (Streamlit Secrets का उपयोग करें)
# Note: अपनी API Key को Streamlit Dashboard के 'Secrets' टैब में रखें
def get_api_key():
    try:
        return st.secrets["ALPHA_VANTAGE_KEY"]
    except:
        return None

# 3. डुअल-इंजन डेटा फेचिंग (NSE + AlphaVantage)
def get_live_data(ticker):
    # इंजन 1: NSE (प्राइमरी)
    try:
        nse = Nse()
        data = nse.get_quote(ticker)
        if data and 'lastPrice' in data:
            return pd.DataFrame([data]), "NSE (Live)"
    except:
        pass
    
    # इंजन 2: Alpha Vantage (बैकअप)
    key = get_api_key()
    if key:
        try:
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}.BSE&apikey={key}"
            res = requests.get(url, timeout=5).json()
            if "Global Quote" in res:
                return pd.DataFrame([res["Global Quote"]]), "AlphaVantage (Backup)"
        except:
            pass
            
    return None, None

# 4. यूजर इंटरफेस
query = st.text_input("स्टॉक सिंबल लिखें (जैसे TATAMOTORS):", "TATAMOTORS")

if st.button("डेटा एनालाइज करें"):
    with st.spinner("JARVIS डेटा ढूँढ रहा है..."):
        df, source = get_live_data(query)
        
        if df is not None:
            st.success(f"सफलता! डेटा स्रोत: {source}")
            st.dataframe(df, use_container_width=True)
            
            # विजुअलाइजेशन
            st.subheader("मार्केट इंडिकेटर")
            fig = go.Figure(go.Indicator(
                mode = "gauge+number",
                value = float(df.iloc[0]['lastPrice'] if 'lastPrice' in df.columns else 0),
                title = {'text': "Current Price"}))
            st.plotly_chart(fig)
        else:
            st.error("डेटा नहीं मिला! दोनों सर्वर (NSE और Backup) डाउन हैं या सिंबल गलत है।")
