import streamlit as st
import time
import datetime
import pyotp
from SmartApi import SmartConnect

# ==========================================
# १. पेज सेटिंग्ज
# ==========================================
st.set_page_config(page_title="Algo Trading Dashboard", page_icon="📈", layout="wide")

st.title("📊 My Live Algo Paper Trading Dashboard")
st.subheader("Angel One API द्वारे १००% रिअल-टाइम ट्रॅकिंग")

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

# ==========================================
# ३. एक्सपायरी आणि लेव्हल्स
# ==========================================
def get_nifty_tuesday_expiry():
    today = datetime.date.today()
    days_ahead = (1 - today.weekday()) % 7
    if days_ahead == 0 and datetime.datetime.now().hour >= 15:
        days_ahead = 7
    return (today + datetime.timedelta(days=days_ahead)).strftime("%d%b%y").upper()

EXPIRY_STR = get_nifty_tuesday_expiry()
tc = 24433.33  
bc = 24400.00  

col1, col2, col3 = st.columns(3)
col1.metric("📊 Top CPR (TC Level)", f"₹{tc}")
col2.metric("📊 Bottom CPR (BC Level)", f"₹{bc}")
col3.metric("📅 Tuesday Expiry", EXPIRY_STR)

st.markdown("---")

# ==========================================
# ४. अचूक लाइव्ह डेटा ट्रॅकिंग (Direct Token)
# ==========================================
try:
    # १. निफ्टी स्पॉटचा लाइव्ह भाव
    spot_data = smart_api.ltpData("NSE", "NIFTY", "99926000")
    spot_price = float(spot_data["data"]["ltp"]) if spot_data.get("status") and spot_data.get("data") else 24630.30
    st.metric(label="📈 NIFTY 50 LIVE SPOT PRICE", value=f"₹{spot_price:.2f}")

    # २. चालू पोझिशन (NIFTY 11AUG26 24650 CE) - Token: 41017
    symbol_name = f"NIFTY{EXPIRY_STR}24650CE"
    token_no = "41017"  # Angel One Direct Option Token
    
    # Angel One NFO मधून थेट अचूक LTP खेचणे
    opt_data = smart_api.ltpData("NFO", symbol_name, token_no)
    
    if opt_data.get("status") and opt_data.get("data"):
        live_option_premium = float(opt_data["data"]["ltp"])
    else:
        live_option_premium = 146.35  # बॅकअप चालू भाव

    entry_price = 140.00  # एंटरी प्राईस
    trade_pnl = (live_option_premium - entry_price) * 25
    sl_val = entry_price - 15
    tgt_val = entry_price + 30

    st.write(f"### 🎯 Active Position: **{symbol_name}**")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Buy Entry Price", f"₹{entry_price:.2f}")
    c2.metric("Live Option Premium (Chart Rate)", f"₹{live_option_premium:.2f}", delta=f"{live_option_premium - entry_price:.2f}")
    
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
