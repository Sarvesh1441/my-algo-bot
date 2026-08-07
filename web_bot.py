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
    "ohlc_data": []
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

st.title("📊 Intraday & BTST Live Algo Dashboard")
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

# ⚙️ ट्रेडिंग मोड निवड
trade_mode = st.radio(
    "🔄 Select Trading Mode:", 
    ["Intraday (Square-off at 3:15 PM)", "BTST (Hold Overnight to Next Day)"], 
    horizontal=True
)
is_btst = "BTST" in trade_mode

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

now_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).time()
market_close_limit = datetime.time(15, 15)

if st.session_state.day_over:
    st.warning(f"🔒 आजचा सेटअप पूर्ण झाला आहे! | P&L: ₹{st.session_state.total_day_pnl:,.2f} | कॅपिटल: ₹{st.session_state.current_capital:,.2f}")
    if st.button("🔄 नवीन दिवसासाठी रीसेट करा"):
        st.session_state.day_over = False
        st.session_state.total_day_pnl = 0.0
        save_state(dict(st.session_state))
        st.rerun()
    st.stop()

current_ts = int(time.time()) + 19800
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

# 🎯 सर्वात वर ठळकपणे दिसणारी LIVE RUNNING P&L पट्टी
if is_active_trade:
    st.markdown("---")
    if trade_pnl >= 0:
        st.success(f"🟢 **LIVE RUNNING PROFIT: +₹{trade_pnl:,.2f}** (Entry: ₹{st.session_state.premium_entry:.2f} | Live: ₹{live_option_premium:.2f})")
    else:
        st.error(f"🔴 **LIVE RUNNING LOSS: -₹{abs(trade_pnl):,.2f}** (Entry: ₹{st.session_state.premium_entry:.2f} | Live: ₹{live_option_premium:.2f})")
    st.markdown("---")

# --- Waiting Mode ---
if not is_active_trade:
    st.info(f"⏳ {trade_mode} सिस्टीम CE किंवा PE ब्रेकआऊटच्या प्रतीक्षेत आहे...")
    
    if not st.session_state.ohlc_data:
        st.session_state.ohlc_data = []
        p = 135.0
        for i in range(35, 0, -1):
            o = p
            c = p + random.choice([-1.5, -0.5, 1.0, 2.0])
            h = max(o, c) + 0.8
            l = min(o, c) - 0.8
            st.session_state.ohlc_data.append({
                "time": current_ts - (i * 300), "open": round(o, 2),
                "high": round(h, 2), "low": round(l, 2), "close": round(c, 2)
            })
            p = c
            
    if spot_price > top_cpr or spot_price < bottom_cpr:
        trade_type = "CE" if spot_price > top_cpr else "PE"
        atm_strike = round(spot_price / 50) * 50
        itm_strike = atm_strike - 50 if trade_type == "CE" else atm_strike + 50
        
        token, symbol_name, _ = fetch_latest_angel_token(itm_strike, trade_type)
        if token and symbol_name:
            opt_data = smart_api.ltpData("NFO", symbol_name, str(token))
            entry_premium = 140.00
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
            p = entry_premium - 4.0
            for i in range(35, 0, -1):
                o = p
                c = p + random.choice([-1.0, 0.5, 1.2])
                h = max(o, c) + 0.5
                l = min(o, c) - 0.5
                st.session_state.ohlc_data.append({
                    "time": current_ts - (i * 300), "open": round(o, 2),
                    "high": round(h, 2), "low": round(l, 2), "close": round(c, 2)
                })
                p = c
            st.session_state.in_position = True
            save_state(dict(st.session_state))
            st.rerun()

# --- Active Position Mode ---
else:
    if not is_btst and now_time >= market_close_limit:
        st.warning("⏰ Intraday Square-off Time (3:15 PM) reached! Closing position...")
        st.session_state.total_day_pnl += trade_pnl
        st.session_state.current_capital += trade_pnl  
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

    # 🛑 **मोठी स्पाइक कॅन्डल कंट्रोल करणारी लॉजिक (Spike Limiter)**
    if st.session_state.ohlc_data:
        last_c = st.session_state.ohlc_data[-1]
        open_p = last_c.get("open", live_option_premium)
        
        # हाय आणि लो च्या मर्यादेवर कॅप (जास्तीत जास्त ±8 ते १० पॉईंट्सची मूव्हमेंट एका कॅन्डलमध्ये)
        max_allowed_high = open_p + 10.0
        min_allowed_low = open_p - 10.0
        
        calculated_high = float(max(last_c.get("high", live_option_premium), live_option_premium))
        calculated_low = float(min(last_c.get("low", live_option_premium), live_option_premium))
        
        last_c["high"] = min(calculated_high, max_allowed_high)
        last_c["low"] = max(calculated_low, min_allowed_low)
        last_c["close"] = float(live_option_premium)

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

    if live_option_premium >= st.session_state.current_tgt or live_option_premium <= st.session_state.current_sl:
        st.session_state.total_day_pnl += trade_pnl
        st.session_state.current_capital += trade_pnl  
        st.session_state.in_position = False
        st.session_state.day_over = True
        save_state(dict(st.session_state))
        st.rerun()

# ==========================================
# ५. प्राईस उजव्या बाजूला असलेला स्थिर Plotly चार्ट
# ==========================================
st.subheader("🕯️ Live Stable Trading Chart")

if st.session_state.ohlc_data:
    times = [datetime.datetime.fromtimestamp(d["time"] - 19800) for d in st.session_state.ohlc_data]
    opens = [d["open"] for d in st.session_state.ohlc_data]
    highs = [d["high"] for d in st.session_state.ohlc_data]
    lows = [d["low"] for d in st.session_state.ohlc_data]
    closes = [d["close"] for d in st.session_state.ohlc_data]

    fig = go.Figure(data=[go.Candlestick(
        x=times, open=opens, high=highs, low=lows, close=closes,
        increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    )])

    if is_active_trade:
        fig.add_hline(y=float(st.session_state.premium_entry), line_dash="solid", line_color="blue", annotation_text="ENTRY")
        fig.add_hline(y=float(st.session_state.current_tgt), line_dash="dash", line_color="green", annotation_text="TARGET")
        fig.add_hline(y=float(st.session_state.current_sl), line_dash="dash", line_color="red", annotation_text="SL")

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        height=420,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor='white',
        plot_bgcolor='white',
        yaxis=dict(side="right")
    )
    st.plotly_chart(fig, use_container_width=True)
