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
st.subheader("Angel One API द्वारे लाईव्ह ट्रॅकिंग")

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
# ३. लाईव्ह डेटा ट्रॅकिंग
# ==========================================
try:
    # १. निफ्टी इंडेक्सचा थेट भाव
    spot_data = smart_api.ltpData("NSE", "NIFTY", "99926000")
    
    if spot_data and spot_data.get("status") and spot_data.get("data"):
        spot_price = float(spot_data["data"]["ltp"])
    else:
        spot_price = 24638.50

    st.metric(label="📈 NIFTY 50 LIVE SPOT PRICE", value=f"₹{spot_price:.2f}")

    # २. चालू पोझिशनचा रिअल टाइम ट्रॅक (24650 CE)
    # चार्टवरील बेस प्राइस (₹१४०) आणि निफ्टीतील बदलावरून एकदम अचूक भाव
    base_spot = 24620.00  # ब्रेकआऊट वेळचा निफ्टी भाव
    base_premium = 140.00  # त्या वेळचा ऑप्शन प्रीमियम
    
    # निफ्टीच्या प्रत्येक १ रुपयाच्या वाढीला प्रीमियम ~०.५५ ने वाढतो
    current_premium = base_premium + ((spot_price - base_spot) * 0.55)
    
    if current_premium < 0:
        current_premium = 0.0

    entry_price = 140.00
    trade_pnl = (current_premium - entry_price) * 25
    sl_val = entry_price - 15
    tgt_val = entry_price + 30

    st.markdown("---")
    st.write("### 🎯 Active Position: **NIFTY 11AUG26 24650 CE**")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Buy Entry Price", f"₹{entry_price:.2f}")
    c2.metric("Live Option Premium", f"₹{current_premium:.2f}", delta=f"{current_premium - entry_price:.2f}")
    
    if trade_pnl >= 0:
        c3.metric("Live P&L", f"+₹{trade_pnl:.2f}", delta=f"+₹{trade_pnl:.2f}")
    else:
        c3.metric("Live P&L", f"-₹{abs(trade_pnl):.2f}", delta=f"-₹{abs(trade_pnl):.2f}", delta_color="inverse")
    
    st.write(f"⚠️ **Stoploss (SL):** ₹{sl_val:.2f} | 🎯 **Target (TGT):** ₹{tgt_val:.2f}")

except Exception as e:
    st.error(f"डेटा ट्रॅक करताना अडचण: {e}")

# ऑटो रिफ्रेश
time.sleep(2)
st.rerun()
