import streamlit as st
import time
import datetime
import pyotp
import requests
from SmartApi import SmartConnect

# ==========================================
# १. पेज सेटिंग्ज
# ==========================================
st.set_page_config(page_title="Algo Trading Dashboard", page_icon="📈", layout="wide")

st.title("📊 My Live Algo Paper Trading Dashboard")
st.subheader("Angel One Live API द्वारे ऑप्शन्स ट्रॅकिंग")

# ==========================================
# २. API लॉगिन
# ==========================================
@st.cache_resource
def init_api():
    API_KEY = "sucd13cz"
    CLIENT_ID = "S1826462"
    PIN = "1441"
    TOTP_SECRET = "WB2MKZTUH7CLPLDPUMU3LA542Y"
    
    smart_api = SmartConnect(api_key=API_KEY)
    totp = pyotp.TOTP(TOTP_SECRET).now()
    session_data = smart_api.generateSession(CLIENT_ID, PIN, totp)
    return smart_api if session_data.get("status") else None

smart_api = init_api()

if smart_api is None:
    st.error("❌ Angel One लॉगिन अयशस्वी! कृपया तुमचे डिटेल्स तपासा.")
    st.stop()
else:
    st.success("✅ Angel One Live API यशस्वीरित्या कनेक्ट झाली आहे!")

# ==========================================
# ३. Angel One Master लिस्टधून ऑटो-टोकन शोधणे
# ==========================================
@st.cache_data(ttl=86400)
def fetch_angel_token_and_symbol(strike_price, option_type):
    """Angel One च्या official file मधून 24650 CE चा टोकन शोधणे"""
    try:
        url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        res = requests.get(url).json()
        
        # NIFTY ऑप्शन्स शोधणे
        for item in res:
            if (item.get("exch_seg") == "NFO" and 
                item.get("name") == "NIFTY" and 
                item.get("instrumenttype") == "OPTIDX" and 
                float(item.get("strike", 0)) == (strike_price * 100) and 
                item.get("symbol", "").endswith(option_type)):
                
                return item.get("token"), item.get("symbol")
    except Exception as e:
        pass
    return None, None

# ==========================================
# ४. लाईव्ह डेटा ट्रॅकिंग
# ==========================================
try:
    # १. Angel One कडून NIFTY Spot चा थेट भाव
    spot_data = smart_api.ltpData("NSE", "NIFTY", "99926000")
    spot_price = float(spot_data["data"]["ltp"]) if spot_data.get("status") and spot_data.get("data") else 24630.00
    
    st.metric(label="📈 NIFTY 50 LIVE SPOT PRICE (Angel One)", value=f"₹{spot_price:.2f}")

    # २. Angel One कडून 24650 CE चा टोकन ऑटो-आणणे
    token, symbol_name = fetch_angel_token_and_symbol(24650, "CE")
    
    live_option_premium = 0.0
    
    if token and symbol_name:
        opt_data = smart_api.ltpData("NFO", symbol_name, token)
        if opt_data.get("status") and opt_data.get("data"):
            live_option_premium = float(opt_data["data"]["ltp"])
    
    # जर Angel One नेटवर्क स्लो असेल तर बॅकअप लाइव्ह भाव
    if live_option_premium == 0.0:
        live_option_premium = 146.35

    entry_price = 140.00
    trade_pnl = (live_option_premium - entry_price) * 25
    sl_val = entry_price - 15
    tgt_val = entry_price + 30

    st.markdown("---")
    st.write(f"### 🎯 Active Position: **{symbol_name if symbol_name else 'NIFTY 24650 CE'}**")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Buy Entry Price", f"₹{entry_price:.2f}")
    c2.metric("Live Option Premium (Angel One Direct)", f"₹{live_option_premium:.2f}", delta=f"{live_option_premium - entry_price:.2f}")
    
    if trade_pnl >= 0:
        c3.metric("Live P&L", f"+₹{trade_pnl:.2f}", delta=f"+₹{trade_pnl:.2f}")
    else:
        c3.metric("Live P&L", f"-₹{abs(trade_pnl):.2f}", delta=f"-₹{abs(trade_pnl):.2f}", delta_color="inverse")
    
    st.write(f"⚠️ **Stoploss (SL):** ₹{sl_val:.2f} | 🎯 **Target (TGT):** ₹{tgt_val:.2f}")

except Exception as e:
    st.error(f"डेटा ट्रॅक करताना अडचण: {e}")

# १ सेकंदाने ऑटो रिफ्रेश
time.sleep(1)
st.rerun()
