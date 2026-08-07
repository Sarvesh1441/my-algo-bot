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
# १. पेज कॉन्फिगरेशन आणि स्टेट मॅनेजर
# ==========================================
st.set_page_config(
    page_title="Algo Trading Dashboard", 
    page_icon="🚀", 
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

saved_data = load_state()

defaults = {
    "in_position": False,
    "trade_type": None,
    "selected_option": "",
    "option_token": "",
    "premium_entry": 0.0,
    "total_day_pnl": saved_data.get("total_day_pnl", 0.0),
    "current_capital": saved_data.get("current_capital", INITIAL_CAPITAL),
    "day_over": saved_data.get("day_over", False),
    "trade_count": saved_data.get("trade_count", 0),
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

# 🔄 ऑटोरिफ्रेश दर २ सेकंदाला
st_autorefresh(interval=2000, limit=None, key="main_auto_refresh")

CURRENT_CAPITAL = st.session_state.current_capital
RISK_PER_TRADE = CURRENT_CAPITAL * 0.05  
SL_POINTS = 15  
NIFTY_LOT_SIZE = 65  

calculated_lots = int(RISK_PER_TRADE / (SL_POINTS * NIFTY_LOT_SIZE))
if calculated_lots < 1:
    calculated_lots = 1
LOT_SIZE = calculated_lots * NIFTY_LOT_SIZE

# 🕒 लाईव्ह घड्याळ
ist_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
current_time_str = ist_now.strftime("%H:%M:%S")
current_date_str = ist_now.strftime("%d-%b-%Y")

st.title("🚀 Advanced Intraday & BTST Algo Dashboard")
st.markdown(f"🕒 **Market Time (IST):** `{current_date_str} | {current_time_str}`")
st.subheader(
    f"💰 Capital: ₹{CURRENT_CAPITAL:,.2f} | "
    f"Lots: {calculated_lots} (Qty: {LOT_SIZE}) | "
    f"🎯 Trades Today: {st.session_state.trade_count}/2"
)

# ==========================================
# २. API कनेक्शन
# ==========================================
@st.cache_resource
def init_bot_api():
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

smart_api = init_bot_api()

if smart_api is None:
    st.error("❌ Angel One API कनेक्शन अयशस्वी झाले!")
    st.stop()

# ==========================================
# ३. टोकन आणि सिस्टीम सेटिंग्स
# ==========================================
@st.cache_data(ttl=86400)
def get_angel_token(strike_price, option_type):
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
            return valid_options[0][1], valid_options[0][2]
    except Exception:
        pass
    return None, None

col1, col2 = st.columns(2)
with col1:
    trade_mode = st.radio("🔄 Trading Mode:", ["Intraday (Square-off 3:15 PM)", "BTST (Overnight Hold)"], horizontal=True)
with col2:
    time_frame = st.radio("⏱️ Time Frame:", ["1-Min", "5-Min", "15-Min"], horizontal=True)

is_btst = "BTST" in trade_mode
if time_frame == "1-Min": tf_sec = 60
elif time_frame == "15-Min": tf_sec = 900
else: tf_sec = 300

st.markdown("---")

# ==========================================
# ४. ट्रेड कंट्रोल आणि एक्झिक्युशन लॉजिक
# ==========================================
spot_price = 24630.00
try:
    spot_data = smart_api.ltpData("NSE", "NIFTY", "99926000")
    if spot_data and spot_data.get("status"):
        spot_price = float(spot_data["data"]["ltp"])
except Exception:
    pass

st.metric(label="📈 NIFTY 50 SPOT PRICE", value=f"₹{spot_price:,.2f}")

# 🛑 मॅक्स २ ट्रेड मर्यादा तपासणी
if st.session_state.trade_count >= 2 or st.session_state.day_over:
    st.warning(f"🔒 आजचे दोन्ही ट्रेड पूर्ण झाले आहेत (Max Limit Reached)! | एकूण P&L: ₹{st.session_state.total_day_pnl:,.2f}")
    if st.button("🔄 नवीन दिवसासाठी रीसेट करा"):
        st.session_state.day_over = False
        st.session_state.trade_count = 0
        st.session_state.total_day_pnl = 0.0
        st.session_state.trade_history = []
        save_state(dict(st.session_state))
        st.rerun()
    
    st.markdown("---")
    st.subheader("📜 Today's Trade History")
    if st.session_state.trade_history:
        st.dataframe(pd.DataFrame(st.session_state.trade_history), use_container_width=True)
    st.stop()

current_ts = int(ist_now.timestamp())
is_active = st.session_state.in_position

live_premium = st.session_state.premium_entry
current_pnl = 0.0

if is_active:
    if st.session_state.option_token:
        try:
            opt_res = smart_api.ltpData("NFO", st.session_state.selected_option, str(st.session_state.option_token))
            if opt_res and opt_res.get("status"):
                live_premium = float(opt_res["data"]["ltp"])
        except Exception:
            pass
    current_pnl = (live_premium - st.session_state.premium_entry) * LOT_SIZE

if is_active:
    if current_pnl >= 0:
        st.success(f"🟢 **LIVE RUNNING PROFIT: +₹{current_pnl:,.2f}** (Entry: ₹{st.session_state.premium_entry:.2f} | Live: ₹{live_premium:.2f})")
    else:
        st.error(f"🔴 **LIVE RUNNING LOSS: -₹{abs(current_pnl):,.2f}** (Entry: ₹{st.session_state.premium_entry:.2f} | Live: ₹{live_premium:.2f})")
    st.markdown("---")

# 🔍 सिग्नलची प्रतीक्षा
if not is_active:
    st.info(f"⏳ सिस्टीम मार्केट ब्रेकआऊटच्या प्रतीक्षेत आहे... (Trade {st.session_state.trade_count + 1} of 2)")
    
    if not st.session_state.ohlc_data:
        p = 181.15
        for i in range(20, 0, -1):
            o = p
            c = p + random.choice([-0.5, 0.5])
            st.session_state.ohlc_data.append({
                "time": current_ts - (i * tf_sec),
                "open": o, "high": max(o, c)+0.3, "low": min(o, c)-0.3, "close": c
            })
            p = c

    # डमी ब्रेकआऊट ट्रिगर (किंवा CPR लेव्हल्स)
    if spot_price > 24600 or spot_price < 24500:
        trade_type = "CE" if spot_price > 24600 else "PE"
        atm = round(spot_price / 50) * 50
        strike = atm - 50 if trade_type == "CE" else atm + 50
        
        token, symbol = get_angel_token(strike, trade_type)
        if token and symbol:
            entry_p = 181.15
            try:
                op_data = smart_api.ltpData("NFO", symbol, str(token))
                if op_data and op_data.get("status"):
                    entry_p = float(op_data["data"]["ltp"])
            except Exception:
                pass
            
            st.session_state.trade_type = trade_type
            st.session_state.selected_option = symbol
            st.session_state.option_token = token
            st.session_state.premium_entry = entry_p
            st.session_state.current_sl = entry_p - SL_POINTS
            st.session_state.current_tgt = entry_p + (45 if is_btst else 30)
            st.session_state.sl_trailed_to_cost = False
            st.session_state.in_position = True
            save_state(dict(st.session_state))
            st.rerun()

else:
    # 🛑 टार्गेट किंवा एसएल हिट तपासणे
    if live_premium >= st.session_state.current_tgt or live_premium <= st.session_state.current_sl or (not is_btst and ist_now.time() >= datetime.time(15, 15)):
        closed_pnl = current_pnl
        st.session_state.total_day_pnl += closed_pnl
        st.session_state.current_capital += closed_pnl
        st.session_state.trade_count += 1
        
        st.session_state.trade_history.append({
            "Time": current_time_str,
            "Symbol": st.session_state.selected_option,
            "Type": st.session_state.trade_type,
            "Entry": st.session_state.premium_entry,
            "Exit": live_premium,
            "P&L (₹)": round(closed_pnl, 2)
        })
        
        st.session_state.in_position = False
        if st.session_state.trade_count >= 2:
            st.session_state.day_over = True
            
        save_state(dict(st.session_state))
        st.rerun()

    st.write(f"### 🎯 Active Position: **{st.session_state.selected_option}**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entry Price", f"₹{st.session_state.premium_entry:.2f}")
    c2.metric("Live Premium", f"₹{live_premium:.2f}", delta=f"{live_premium - st.session_state.premium_entry:.2f}")
    c3.metric("Stop Loss", f"₹{st.session_state.current_sl:.2f}")
    c4.metric("Target", f"₹{st.session_state.current_tgt:.2f}")
    st.markdown("---")

# ==========================================
# ५. कॅन्डलस्टिक चार्ट आणि हिस्ट्री टेबल
# ==========================================
st.subheader(f"🕯️ Live Candlestick Chart ({time_frame})")

if not st.session_state.ohlc_data:
    base = float(st.session_state.premium_entry) if is_active else 181.15
    st.session_state.ohlc_data = [{"time": current_ts, "open": base, "high": base+1, "low": base-1, "close": base}]
else:
    last = st.session_state.ohlc_data[-1]
    last["close"] = float(live_premium if is_active else last["close"])
    last["high"] = max(last["high"], last["close"] + 0.3)
    last["low"] = min(last["low"], last["close"] - 0.3)

df_c = pd.DataFrame(st.session_state.ohlc_data)
df_c["Time"] = pd.to_datetime(df_c["time"], unit="s") + pd.Timedelta(hours=5, minutes=30)

fig = go.Figure(data=[go.Candlestick(
    x=df_c["Time"], open=df_c["open"], high=df_c["high"], low=df_c["low"], close=df_c["close"],
    increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
)])

if is_active:
    fig.add_hline(y=st.session_state.premium_entry, line_color="blue", annotation_text="ENTRY")
    fig.add_hline(y=st.session_state.current_tgt, line_dash="dash", line_color="green", annotation_text="TARGET")
    fig.add_hline(y=st.session_state.current_sl, line_dash="dash", line_color="red", annotation_text="SL")

fig.update_layout(xaxis_rangeslider_visible=False, height=420, margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(fig, use_container_width=True)

# 📜 ट्रेड हिस्ट्री
st.markdown("---")
st.subheader("📜 Trade History & Log")
if st.session_state.trade_history:
    st.dataframe(pd.DataFrame(st.session_state.trade_history), use_container_width=True)
    tot = sum([t["P&L (₹)"] for t in st.session_state.trade_history])
    if tot >= 0: st.success(f"🎉 **Total Realized P&L: +₹{tot:,.2f}**")
    else: st.error(f"⚠️ **Total Realized P&L: -₹{abs(tot):,.2f}**")
else:
    st.info("📭 आज पूर्ण झालेला कोणताही ट्रेड रेकॉर्ड उपलब्ध नाही.")
