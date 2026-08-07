import streamlit as st
import time
import datetime
import pyotp
import requests
from SmartApi import SmartConnect
import json
import os
import random
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
import pandas as pd

# ==========================================
# १. पेज आणि डायनॅमिक कॅपिटल सेटिंग्ज
# ==========================================
st.set_page_config(
    page_title="Intraday & BTST Algo Dashboard", 
    page_icon="📈", 
    layout="wide"
)

STATE_FILE = "trade_state.json"
INITIAL_CAPITAL = 100000  

def save_state(state_data):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state_data, f)
    except Exception:
        pass

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

# 🔒 सुरक्षित स्टेट इनिशियलायझेशन
saved_data = load_state()

defaults = {
    "in_position": False,
    "trade_type": None,
    "selected_option": "",
    "option_token": "",
    "premium_entry": 0.0,
    "entry_spot_price": 0.0,
    "total_day_pnl": saved_data.get("total_day_pnl", 0.0),
    "current_capital": saved_data.get("current_capital", INITIAL_CAPITAL),
    "day_over": saved_data.get("day_over", False),
    "trade_count": saved_data.get("trade_count", 0),  # 🔢 आज झालेली ट्रेडची संख्या
    "current_sl": 0.0,
    "current_tgt": 0.0,
    "sl_trailed_to_cost": False,
    "ohlc_data": [],
    "trade_history": saved_data.get("trade_history", []),
    "selected_tf": "1-Min"
}

for key, default_val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = saved_data.get(key, default_val)

# 🔄 दर २ सेकंदाला लाईव्ह डेटा ऑटो-रिफ्रेश
st_autorefresh(interval=2000, limit=None, key="live_data_refresher")

CURRENT_CAPITAL = st.session_state.current_capital
RISK_PER_TRADE = CURRENT_CAPITAL * 0.05  
SL_POINTS = 15  
NIFTY_LOT_SIZE = 65  

calculated_lots = int(RISK_PER_TRADE / (SL_POINTS * NIFTY_LOT_SIZE))
if calculated_lots < 1:
    calculated_lots = 1
LOT_SIZE = calculated_lots * NIFTY_LOT_SIZE

# 🕒 लाईव्ह रिअल-टाइम घड्याळ (IST Time)
ist_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
current_time_str = ist_now.strftime("%H:%M:%S")
current_date_str = ist_now.strftime("%d-%b-%Y")

st.title("📊 Intraday & BTST Live Algo Dashboard")
st.markdown(f"🕒 **Live Market Time:** `{current_date_str} | {current_time_str} IST`")
st.subheader(
    f"💰 Current Capital: ₹{CURRENT_CAPITAL:,.2f} | "
    f"Lots: {calculated_lots} (Qty: {LOT_SIZE}) | "
    f"📊 Today's Trades: {st.session_state.trade_count}/2"
)

# ==========================================
# २. API लॉगिन
# ==========================================
@st.cache_resource
def init_api():
    API_KEY = "sucd13cz"
    CLIENT_ID = "S1826462"
    PIN = "1441"
    TOTP_SECRET = "WB2MKZTUH7CLPLDPUMU3LA542Y"
    
    try:
        smart_api = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        session_data = smart_api.generateSession(CLIENT_ID, PIN, totp)
        if session_data.get("status"):
            return smart_api
    except Exception:
        pass
    return None

smart_api = init_api()

if smart_api is None:
    st.error("❌ Angel One लॉगिन अयशस्वी!")
    st.stop()

# ==========================================
# ३. एक्सपायरी आणि टोकन अचूक शोधणे
# ==========================================
@st.cache_data(ttl=86400)
def fetch_latest_angel_token(strike_price, option_type):
    try:
        url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        res = requests.get(url).json()
        valid_options = []
        target_strike = float(strike_price * 100)
        
        for item in res:
            if item.get("exch_seg") == "NFO" and item.get("name") == "NIFTY":
                if item.get("instrumenttype") == "OPTIDX":
                    if float(item.get("strike", 0)) == target_strike:
                        if item.get("symbol", "").endswith(option_type):
                            expiry_str = item.get("expiry", "")
                            if expiry_str:
                                try:
                                    exp_date = datetime.datetime.strptime(expiry_str, "%d%b%Y").date()
                                    if exp_date >= datetime.date.today():
                                        valid_options.append((exp_date, item.get("token"), item.get("symbol")))
                                except Exception:
                                    pass
        if valid_options:
            valid_options.sort(key=lambda x: x[0])
            return valid_options[0][1], valid_options[0][2], valid_options[0][0].strftime("%d-%b-%Y")
    except Exception:
        pass
    return None, None, None

# ⏱️ टाईम फ्रेम आणि मोड सिलेक्टर
col_tf1, col_tf2 = st.columns(2)
with col_tf1:
    trade_mode = st.radio(
        "🔄 Select Trading Mode:", 
        ["Intraday (Square-off at 3:15 PM)", "BTST (Hold Overnight to Next Day)"], 
        horizontal=True
    )
with col_tf2:
    time_frame = st.radio(
        "⏱️ Select Time Frame:", 
        ["1-Min", "5-Min", "15-Min"], 
        key="tf_radio",
        horizontal=True
    )

is_btst = "BTST" in trade_mode

if time_frame != st.session_state.selected_tf:
    st.session_state.selected_tf = time_frame
    st.session_state.ohlc_data = []

if time_frame == "1-Min":
    tf_seconds = 60
elif time_frame == "15-Min":
    tf_seconds = 900
else:
    tf_seconds = 300  

# CPR Levels Setup
high_prev = 24650.00
low_prev = 24450.00
close_prev = 24580.00

pivot = round((high_prev + low_prev + close_prev) / 3, 2)
bc = round((high_prev + low_prev) / 2, 2)
tc = round
