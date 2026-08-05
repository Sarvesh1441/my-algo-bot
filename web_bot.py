import streamlit as st
import time
import datetime
import pyotp
from SmartApi import SmartConnect
import requests
import json
import os

# ==========================================
# १. पेज आणि फाईल सेटिंग्ज
# ==========================================
st.set_page_config(page_title="Algo Trading Dashboard", page_icon="📈", layout="wide")

STATE_FILE = "trade_state.json"

def save_state(state_data):
    with open(STATE_FILE, "w") as f:
        json.dump(state_data, f)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"in_position": False, "trade_type": None, "selected_option": "", "premium_entry": 0.0, "entry_spot_price": 0.0, "total_day_pnl": 0.0}

st.title("📊 My Live Algo Paper Trading Dashboard")
st.subheader("Angel One API द्वारे लाईव्ह मार्केट ट्रॅकिंग")

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

# फाईल मधून जुनी पोझिशन लोड करणे
saved_data = load_state()
if 'in_position' not in st.session_state:
    st.session_state.in_position = saved_data["in_position"]
    st.session_state.trade_type = saved_data["trade_type"]
    st.session_state.selected_option = saved_data["selected_option"]
    st.session_state.premium_entry = saved_data["premium_entry"]
    st.session_state.entry_spot_price = saved_data["entry_spot_price"]
    st.session_state.total_day_pnl = saved_data.get("total_day_pnl", 0.0)

# ==========================================
# ४. डेटा दाखवणे
# ==========================================
try:
    spot_data = smart_api.ltpData("NSE", "NIFTY", "99926000")
    
    if spot_data.get("status") and spot_data.get("data") is not None:
        spot_price = float(spot_data["data"]["ltp"])
    else:
        spot_price = 24624.65  # मार्केट बंद असतानाचा फॉलबॅक रेट
        
    st.metric(label="📈 NIFTY 50 LIVE PRICE", value=f"₹{spot_price:.2f}")
    
    # --- Waiting Mode ---
    if not st.session_state.in_position:
        st.info(f"⏳ बॉट सध्या ब्रेकआऊटची वाट पाहत आहे... | आजचा एकूण P&L: ₹{st.session_state.total_day_pnl:.2f}")
        
        if spot_price > tc:
            st.session_state.trade_type = "CE"
            atm_strike = round(spot_price / 50) * 50
            st.session_state.selected_option = f"NIFTY{EXPIRY_STR}{atm_strike}CE"
            st.session_state.entry_spot_price = spot_price
            st.session_state.premium_entry = 166.00  
            st.session_state.in_position = True
            save_state(dict(st.session_state))
            st.rerun()
            
        elif spot_price < bc:
            st.session_state.trade_type = "PE"
            atm_strike = round(spot_price / 50) * 50
            st.session_state.selected_option = f"NIFTY{EXPIRY_STR}{atm_strike}PE"
            st.session_state.entry_spot_price = spot_price
            st.session_state.premium_entry = 145.00  
            st.session_state.in_position = True
            save_state(dict(st.session_state))
            st.rerun()
            
    # --- Active Tracking Mode ---
    else:
        if st.session_state.trade_type == "CE":
            spot_change = spot_price - st.session_state.entry_spot_price
        else:
            spot_change = st.session_state.entry_spot_price - spot_price
            
        current_premium = st.session_state.premium_entry + (spot_change * 0.5)
        trade_pnl = (current_premium - st.session_state.premium_entry) * 25
        
        sl_val = st.session_state.premium_entry - 15
        tgt_val = st.session_state.premium_entry + 30
        
        st.write(f"### 🎯 Active Position: **{st.session_state.selected_option}**")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Buy Entry Price", f"₹{st.session_state.premium_entry:.2f}")
        c2.metric("Current Live Premium", f"₹{current_premium:.2f}")
        
        if trade_pnl >= 0:
            c3.metric("Live P&L", f"+₹{trade_pnl:.2f}", delta=f"+₹{trade_pnl:.2f}")
        else:
            c3.metric("Live P&L", f"-₹{abs(trade_pnl):.2f}", delta=f"-₹{abs(trade_pnl):.2f}", delta_color="inverse")
        
        st.write(f"⚠️ **Stoploss (SL):** ₹{sl_val:.2f} | 🎯 **Target (TGT):** ₹{tgt_val:.2f}")
        st.caption(f"💼 आजचा एकूण बंद झालेला P&L: ₹{st.session_state.total_day_pnl:.2f}")
        
        if current_premium >= tgt_val:
            st.balloons()
            st.session_state.total_day_pnl += trade_pnl
            st.session_state.in_position = False
            save_state(dict(st.session_state))
            st.success(f"🎯 TARGET HIT! नफा बुक झाला: ₹{trade_pnl:.2f}")
            
        elif current_premium <= sl_val:
            st.session_state.total_day_pnl += trade_pnl
            st.session_state.in_position = False
            save_state(dict(st.session_state))
            st.error(f"🛑 STOPLOSS HIT! तोटा बुक झाला: ₹{trade_pnl:.2f}")

except Exception as e:
    st.error(f"डेटा लोड करताना अडचण: {e}")

# ऑटो रिफ्रेश (प्रत्येक २ सेकंदाला)
time.sleep(2)
st.rerun()
