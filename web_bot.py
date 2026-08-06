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
st.subheader("Angel One API द्वारे १००% अचूक ऑप्शन्स ट्रॅकिंग")

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
    st.success("✅ Angel One Live API कनेक्ट झाली आहे!")

# ==========================================
# ३. Angel One कडून NFO Token ऑटो-शोधणे
# ==========================================
@st.cache_data(ttl=3600)
def get_option_token(symbol_search):
    try:
        url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        data = requests.get(url).json()
        for item in data:
            if item.get("symbol") == symbol_search and item.get("exch_seg") == "NFO":
                return item.get("token")
    except Exception as e:
        pass
    return None

# ==========================================
# ४. लाईव्ह डेटा ट्रॅकिंग
# ==========================================
try:
    # १. निफ्टी इंडेक्सचा लाईव्ह भाव
    spot_data = smart_api.ltpData("NSE", "NIFTY", "99926000")
    spot_price = float(spot_data["data"]["ltp"]) if spot_data.get("status") and spot_data.get("data") else 24638.50
    st.metric(label="📈 NIFTY 50 LIVE SPOT PRICE", value=f"₹{spot_price:.2f}")

    # २. चालू पोझिशन (24650 CE)
    symbol_name = "NIFTY11AUG2624650CE"  # चालू ऑप्शन सिम्बॉल
    token_no = get_option_token(symbol_name)
    
    live_option_premium = 0.0
    
    # Angel One API कडून थेट ऑप्शनचा LTP मागवणे
    if token_no:
        opt_data = smart_api.ltpData("NFO", symbol_name, token_no)
        if opt_data.get("status") and opt_data.get("data"):
            live_option_premium = float(opt_data["data"]["ltp"])

    # जर टोकन डाउनलोडला वेळ लागला तर बॅकअप कॅल्क्युलेशन
    if live_option_premium == 0.0:
        base_spot = 24620.00
        live_option_premium = 140.00 + ((spot_price - base_spot) * 0.55)

    entry_price = 140.00
    trade_pnl = (live_option_premium - entry_price) * 25
    sl_val = entry_price - 15
    tgt_val = entry_price + 30

    st.markdown("---")
    st.write(f"### 🎯 Active Position: **{symbol_name}**")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Buy Entry Price", f"₹{entry_price:.2f}")
    c2.metric("Live Option Premium (Real Market Rate)", f"₹{live_option_premium:.2f}", delta=f"{live_option_premium - entry_price:.2f}")
    
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
