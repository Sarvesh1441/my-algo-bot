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
    "total_day_pnl": 0.0,
    "current_capital": saved_data.get("current_capital", INITIAL_CAPITAL),
    "day_over": False,
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
    f"Lots: {calculated_lots} (Qty: {LOT_SIZE})"
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
tc = round((pivot - bc) + pivot, 2)
top_cpr = max(tc, bc)
bottom_cpr = min(tc, bc)

c1, c2, c3 = st.columns(3)
c1.metric("📊 TC Level (Top)", f"₹{top_cpr:.2f}")
c2.metric("📊 Pivot Level (Center)", f"₹{pivot:.2f}")
c3.metric("📊 BC Level (Bottom)", f"₹{bottom_cpr:.2f}")
st.markdown("---")

# ==========================================
# ४. मुख्य ट्रॅकिंग आणि ऑर्डर एक्झिक्युशन लॉजिक
# ==========================================
spot_price = 24630.00
try:
    spot_data = smart_api.ltpData("NSE", "NIFTY", "99926000")
    if spot_data and spot_data.get("status") and spot_data.get("data"):
        spot_price = float(spot_data["data"]["ltp"])
except Exception:
    pass

st.metric(label="📈 NIFTY 50 LIVE SPOT PRICE", value=f"₹{spot_price:.2f}")

now_time = ist_now.time()
market_close_limit = datetime.time(15, 15)

if st.session_state.day_over:
    st.warning(f"🔒 आजचा सेटअप पूर्ण झाला आहे! | एकूण P&L: ₹{st.session_state.total_day_pnl:,.2f} | कॅपिटल: ₹{st.session_state.current_capital:,.2f}")
    if st.button("🔄 नवीन दिवसासाठी रीसेट करा"):
        st.session_state.day_over = False
        st.session_state.total_day_pnl = 0.0
        st.session_state.trade_history = []
        save_state(dict(st.session_state))
        st.rerun()
    st.stop()

current_ts = int(ist_now.timestamp())
is_active_trade = st.session_state.in_position

# --- Live Premium & PnL Calculation ---
live_option_premium = st.session_state.premium_entry
trade_pnl = 0.0

if is_active_trade:
    if st.session_state.option_token:
        try:
            opt_data = smart_api.ltpData("NFO", st.session_state.selected_option, str(st.session_state.option_token))
            if opt_data and opt_data.get("status") and opt_data.get("data"):
                live_option_premium = float(opt_data["data"]["ltp"])
        except Exception:
            pass
    trade_pnl = (live_option_premium - st.session_state.premium_entry) * LOT_SIZE

if is_active_trade:
    st.markdown("---")
    if trade_pnl >= 0:
        st.success(f"🟢 **LIVE RUNNING PROFIT: +₹{trade_pnl:,.2f}** (Entry: ₹{st.session_state.premium_entry:.2f} | Live: ₹{live_option_premium:.2f})")
    else:
        st.error(f"🔴 **LIVE RUNNING LOSS: -₹{abs(trade_pnl):,.2f}** (Entry: ₹{st.session_state.premium_entry:.2f} | Live: ₹{live_option_premium:.2f})")
    st.markdown("---")

# --- Waiting Mode ---
if not is_active_trade:
    st.info(f"⏳ {trade_mode} सिस्टीम [{time_frame}] ब्रेकआऊटच्या प्रतीक्षेत आहे...")
    
    if not st.session_state.ohlc_data:
        st.session_state.ohlc_data = []
        p = 181.15
        for i in range(25, 0, -1):
            o = p
            c = p + random.choice([-0.5, 0.5, 0.8, -0.6])
            h = max(o, c) + 0.4
            l = min(o, c) - 0.4
            st.session_state.ohlc_data.append({
                "time": current_ts - (i * tf_seconds),
                "open": round(o, 2), "high": round(h, 2),
                "low": round(l, 2), "close": round(c, 2)
            })
            p = c
            
    if spot_price > top_cpr or spot_price < bottom_cpr:
        trade_type = "CE" if spot_price > top_cpr else "PE"
        atm_strike = round(spot_price / 50) * 50
        itm_strike = atm_strike - 50 if trade_type == "CE" else atm_strike + 50
        
        token, symbol_name, _ = fetch_latest_angel_token(itm_strike, trade_type)
        if token and symbol_name:
            opt_data = smart_api.ltpData("NFO", symbol_name, str(token))
            entry_premium = 181.15
            if opt_data and opt_data.get("status") and opt_data.get("data"):
                entry_premium = float(opt_data["data"]["ltp"])
            
            st.session_state.trade_type = trade_type
            st.session_state.selected_option = symbol_name
            st.session_state.option_token = token
            st.session_state.premium_entry = entry_premium
            st.session_state.current_sl = entry_premium - SL_POINTS
            st.session_state.current_tgt = entry_premium + (45 if is_btst else 30)
            st.session_state.sl_trailed_to_cost = False
            
            st.session_state.ohlc_data = []
            p = entry_premium
            for i in range(25, 0, -1):
                o = p
                c = p + random.choice([-0.4, 0.4])
                h = max(o, c) + 0.3
                l = min(o, c) - 0.3
                st.session_state.ohlc_data.append({
                    "time": current_ts - (i * tf_seconds),
                    "open": round(o, 2), "high": round(h, 2),
                    "low": round(l, 2), "close": round(c, 2)
                })
                p = c
            st.session_state.in_position = True
            save_state(dict(st.session_state))
            st.rerun()

# --- Active Position Mode ---
else:
    if not is_btst and now_time >= market_close_limit:
        st.warning("⏰ Intraday Square-off Time (3:15 PM) reached! Closing position...")
        closed_pnl = trade_pnl
        st.session_state.total_day_pnl += closed_pnl
        st.session_state.current_capital += closed_pnl  
        
        # 📜 ट्रेड हिस्ट्रीमध्ये ॲड करणे
        st.session_state.trade_history.append({
            "Time": current_time_str,
            "Symbol": st.session_state.selected_option,
            "Type": st.session_state.trade_type,
            "Entry": st.session_state.premium_entry,
            "Exit": live_option_premium,
            "P&L (₹)": round(closed_pnl, 2)
        })
        
        st.session_state.in_position = False
        st.session_state.day_over = True
        save_state(dict(st.session_state))
        st.rerun()

    if not st.session_state.sl_trailed_to_cost:
        if (live_option_premium - st.session_state.premium_entry) >= 20:
            st.session_state.current_sl = st.session_state.premium_entry
            st.session_state.current_tgt = st.session_state.premium_entry + (80 if is_btst else 65)
            st.session_state.sl_trailed_to_cost = True
            save_state(dict(st.session_state))

    if not st.session_state.ohlc_data:
        base_v = float(st.session_state.premium_entry)
        st.session_state.ohlc_data = [{
            "time": current_ts, "open": base_v,
            "high": base_v + 0.5, "low": base_v - 0.5, "close": base_v
        }]
    else:
        last_c = st.session_state.ohlc_data[-1]
        last_c["close"] = float(live_option_premium)
        last_c["high"] = float(max(last_c.get("high", live_option_premium), live_option_premium + 0.3))
        last_c["low"] = float(min(last_c.get("low", live_option_premium), live_option_premium - 0.3))

    mode_badge = "🌙 BTST (Overnight Hold)" if is_btst else "⚡ Intraday (Square-off at 3:15)"
    st.write(f"### 🎯 Active Position [{mode_badge}]: **{st.session_state.selected_option}**")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Buy Entry Price", f"₹{st.session_state.premium_entry:.2f}")
    c2.metric("⚡ Live Premium", f"₹{live_option_premium:.2f}", delta=f"{live_option_premium - st.session_state.premium_entry:.2f} pts")
    
    sl_lbl = "Cost-to-Cost" if st.session_state.sl_trailed_to_cost else "Original SL"
    c3.metric("Current SL", f"₹{st.session_state.current_sl:.2f}", delta=sl_lbl)
    
    tgt_lbl = "1:3 Target" if st.session_state.sl_trailed_to_cost else "Primary Tgt"
    c4.metric("Dynamic Target", f"₹{st.session_state.current_tgt:.2f}", delta=tgt_lbl)
    
    st.markdown("---")

    # Target or Stoploss Hit
    if live_option_premium >= st.session_state.current_tgt or live_option_premium <= st.session_state.current_sl:
        closed_pnl = trade_pnl
        st.session_state.total_day_pnl += closed_pnl
        st.session_state.current_capital += closed_pnl  
        
        # 📜 ट्रेड हिस्ट्रीमध्ये ॲड करणे
        st.session_state.trade_history.append({
            "Time": current_time_str,
            "Symbol": st.session_state.selected_option,
            "Type": st.session_state.trade_type,
            "Entry": st.session_state.premium_entry,
            "Exit": live_option_premium,
            "P&L (₹)": round(closed_pnl, 2)
        })
        
        st.session_state.in_position = False
        st.session_state.day_over = True
        save_state(dict(st.session_state))
        st.rerun()

# ==========================================
# ५. चार्ट आणि ट्रेड हिस्ट्री सेक्शन
# ==========================================
st.subheader(f"📈 Live Instant Price Chart ({time_frame})")

try:
    if not st.session_state.ohlc_data:
        base_val = float(st.session_state.premium_entry) if is_active_trade else 181.15
        st.session_state.ohlc_data = [{
            "time": current_ts, "open": base_val, "high": base_val + 1, "low": base_val - 1, "close": base_val
        }]
    
    df_chart = pd.DataFrame(st.session_state.ohlc_data)
    df_chart["Time"] = pd.to_datetime(df_chart["time"], unit="s") + pd.Timedelta(hours=5, minutes=30)
    df_chart.set_index("Time", inplace=True)
    
    st.line_chart(df_chart["close"], height=380, color="#26a69a")
    
    if is_active_trade:
        st.info(f"🔵 **Trade Levels** ➔ Entry: ₹{st.session_state.premium_entry} | Target: ₹{st.session_state.current_tgt} | StopLoss: ₹{st.session_state.current_sl}")
except Exception as e:
    st.info("📊 चार्ट अपडेट होत आहे...")

# 📜 **Trade History Table Section**
st.markdown("---")
st.subheader("📜 Today's Trade History & P&L Log")

if st.session_state.trade_history:
    df_history = pd.DataFrame(st.session_state.trade_history)
    st.dataframe(df_history, use_container_width=True)
    
    total_pnl_val = sum([t["P&L (₹)"] for t in st.session_state.trade_history])
    if total_pnl_val >= 0:
        st.success(f"🎉 **Total Day Realized P&L: +₹{total_pnl_val:,.2f}**")
    else:
        st.error(f"⚠️ **Total Day Realized P&L: -₹{abs(total_pnl_val):,.2f}**")
else:
    st.info("📭 आज अद्याप कोणतीही ट्रेड हिस्ट्री उपलब्ध नाही (ट्रेड पूर्ण झाल्यावर इथे रेकॉर्ड दिसेल).")
