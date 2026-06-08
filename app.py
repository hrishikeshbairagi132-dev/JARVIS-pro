import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime
import numpy as np

st.set_page_config(layout="wide")
st.title("🚀 JARVIS PRO - Google Finance Engine")

# Google Finance से डेटा निकालने वाला परमानेंट फंक्शन
def get_google_finance_data(ticker):
    try:
        # Ticker को URL के लिए तैयार करें (जैसे TATAMOTORS)
        sym = ticker.replace(".NS", "").replace(".BO", "").strip()
        url = f"https://www.google.com/finance/quote/{sym}:NSE"
        
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return None, "Google Finance सर्वर से रिस्पॉन्स नहीं मिला।"

        # यहाँ हम सीधे HTML से 'data-last-price' निकाल रहे हैं
        if 'data-last-price="' in response.text:
            start = response.text.find('data-last-price="') + len('data-last-price="')
            end = response.text.find('"', start)
            live_price = float(response.text[start:end])
            
            # चूंकि Google Finance API नहीं देता, हम एक बेसिक चार्ट के लिए डेटा सिम्युलेट कर रहे हैं
            dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
            prices = live_price + np.random.normal(0, live_price * 0.01, 30).cumsum()
            df = pd.DataFrame({'Close': prices}, index=dates)
            return df, live_price
        else:
            return None, "सिंबल मिला लेकिन भाव नहीं मिल पाया।"
            
    except Exception as e:
        return None, str(e)

# मेन UI
query = st.text_input("NSE स्टॉक सिंबल (जैसे TATAMOTORS):", "TATAMOTORS")

if st.button("डेटा एनालाइज करें"):
    with st.spinner("Google Finance से डेटा लिया जा रहा है..."):
        df, price_or_error = get_google_finance_data(query)
        
        if df is not None:
            st.success(f"लाइव भाव: ₹{price_or_error}")
            
            # चार्ट
            fig = go.Figure(data=[go.Scatter(x=df.index, y=df['Close'], mode='lines', name='Price')])
            fig.update_layout(template="plotly_dark", title=f"{query} का अनुमानित चार्ट")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error(f"एरर: {price_or_error}")
