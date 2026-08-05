import streamlit as st
import time
import datetime
import pyotp
from SmartApi import SmartConnect
import requests
import json
import os

# ==========================================
# १. पेज आणि फाईल सेटिंग्ज (Cloud Friendly)
# ==========================================
st.set_page_config(page_title="Algo Trading Dashboard", page_icon="📈", layout="wide")

# क्लाउड सर्व्हरसाठी लोकल D: ड्राईव्हचा पाथ काढून फक्त फाईलचे नाव ठेवले आहे
STATE_FILE = "trade_state.json"

# डेटा फाईलमध्ये सेव्ह करण्याचे फंक्शन्स
def save_state(state_data):
    with open(STATE_FILE, "w") as f:
        json.dump(state_data, f)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"in_position": False, "trade_type": None, "selected_option": "", "premium_entry": 0.0, "entry_spot_price": 0.0, "total_day_pnl": 0.0}

st.title("📊 My Live Algo Paper Trading Dashboard")
st.subheader("Angel One API द्वारे लाईव्ह賦 मार्केट ट्रॅकिंग")

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