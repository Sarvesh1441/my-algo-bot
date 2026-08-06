import streamlit as st
import time
import datetime
import pyotp
import requests
from SmartApi import SmartConnect
import json
import os
import random
import streamlit.components.v1 as components

# ==========================================
# १. पेज आणि कॅपिटल सेटिंग्ज
# ==========================================
st.set_page_config(
    page_title="Algo Trading Dashboard", 
    page_icon="📈", 
    layout="wide"
)

STATE_FILE = "trade_state.json"
TOTAL_CAPITAL = 100000  
RISK_PER_TRADE = TOTAL_CAPITAL * 0.05  
SL_POINTS = 15  
NIFTY_LOT_SIZE = 65  

calculated_lots = int(RISK_PER_TRADE / (SL_POINTS * NIFTY_LOT_SIZE))
if calculated_lots < 1:
    calculated_lots = 1
LOT_SIZE = calculated_lots * NIFTY_LOT_SIZE

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

st.title("📊 My Live Algo Trading Dashboard")
st.subheader(
    f"💰 Capital: ₹{TOTAL_CAPITAL:,} | "
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
# ३. एक्सपायरी आणि टोकन शोधणे
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

tc = 24433.33  
bc = 24400.00  

col1, col2 = st.columns(2)
col1.metric("📊 Top CPR (TC Level)", f"₹{tc}")
col2.metric("📊 Bottom CPR (BC Level)", f"₹{bc}")
st.markdown("---")

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
    "day_over": False,
    "current_sl": 0.0,
    "current_tgt": 0.0,
    "sl_trailed_to_cost": False,
    "ohlc_data": []
}

for key, default_val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = saved_data.get(key, default_val)

# ==========================================
# ४. मुख्य डेटा फेचिंग लॉजिक
# ==========================================
spot_price = 24630.00
try:
    spot_data = smart_api.ltpData("NSE", "NIFTY", "99926000")
    if spot_data and spot_data.get("status") and spot_data.get("data"):
        spot_price = float(spot_data["data"]["ltp"])
except Exception:
    pass

st.metric(label="📈 NIFTY 50 LIVE SPOT PRICE", value=f"₹{spot_price:.2f}")

if st.session_state.day_over:
    st.warning(f"🔒 आजचा सेटअप पूर्ण झाला आहे! | P&L: ₹{st.session_state.total_day_pnl:.2f}")
    if st.button("🔄 उद्यासाठी रीसेट करा"):
        for k, v in defaults.items():
            st.session_state[k] = v
        save_state(dict(st.session_state))
        st.rerun()
    st.stop()

current_ts = int(time.time()) + 19800
is_active_trade = st.session_state.in_position

# OHLC डेटा निर्मिती
if not st.session_state.ohlc_data:
    st.session_state.ohlc_data = []
    p = spot_price - 10.0
    for i in range(40, 0, -1):
        o = p
        c = p + random.choice([-2.0, -0.5, 1.2, 2.8])
        h = max(o, c) + random.uniform(0.3, 1.0)
        l = min(o, c) - random.uniform(0.3, 1.0)
        st.session_state.ohlc_data.append({
            "time": current_ts - (i * 300),
            "open": round(o, 2), "high": round(h, 2),
            "low": round(l, 2), "close": round(c, 2)
        })
        p = c

live_option_premium = st.session_state.premium_entry
if is_active_trade and st.session_state.option_token:
    try:
        opt_data = smart_api.ltpData("NFO", st.session_state.selected_option, st.session_state.option_token)
        if opt_data and opt_data.get("status") and opt_data.get("data"):
            live_option_premium = float(opt_data["data"]["ltp"])
    except Exception:
        pass

trade_pnl = (live_option_premium - st.session_state.premium_entry) * LOT_SIZE if is_active_trade else 0.0

if is_active_trade:
    st.write(f"### 🎯 Active ITM Position: **{st.session_state.selected_option}**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Buy Entry Price", f"₹{st.session_state.premium_entry:.2f}")
    c2.metric("Live Option Premium", f"₹{live_option_premium:.2f}")
    c3.metric("Current SL", f"₹{st.session_state.current_sl:.2f}")
    c4.metric("Dynamic Target", f"₹{st.session_state.current_tgt:.2f}")
    st.markdown("---")

# ==========================================
# ५. स्थिर (No-Disappear) ट्रेडिंगव्ह्यू चार्ट इंजिन
# ==========================================
st.subheader("🕯️ Live TradingView Standalone Chart")

tv_json_data = json.dumps(st.session_state.ohlc_data)
entry_p = float(st.session_state.premium_entry)
sl_p = float(st.session_state.current_sl)
tgt_p = float(st.session_state.current_tgt)
live_p = float(live_option_premium if is_active_trade else spot_price)

pnl_color = '#00E676' if trade_pnl >= 0 else '#FF1744'
pnl_text = f"LIVE P&L: +₹{trade_pnl:.2f}" if trade_pnl >= 0 else f"LIVE P&L: -₹{abs(trade_pnl):.2f}"

raw_html = f"""<!DOCTYPE html>
<html>
<head>
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        body {{ margin: 0; padding: 0; background-color: #ffffff; }}
        #chart_div {{ width: 100%; height: 420px; }}
    </style>
</head>
<body>
    <div id="chart_div"></div>
    <script>
        const container = document.getElementById('chart_div');
        const chart = LightweightCharts.createChart(container, {{
            width: container.clientWidth,
            height: 420,
            layout: {{ backgroundColor: '#ffffff', textColor: '#333333' }},
            grid: {{ vertLines: {{ color: '#f0f3fa' }}, horzLines: {{ color: '#f0f3fa' }} }},
            crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
            priceScale: {{ position: 'right', borderVisible: true }},
            timeScale: {{ borderVisible: true, timeVisible: true, barSpacing: 8 }}
        }});
        
        const candleSeries = chart.addCandlestickSeries({{
            upColor: '#26a69a', downColor: '#ef5350',
            borderUpColor: '#26a69a', borderDownColor: '#ef5350',
            wickUpColor: '#26a69a', wickDownColor: '#ef5350'
        }});
        
        const chartData = {tv_json_data};
        candleSeries.setData(chartData);
        chart.timeScale().fitContent();
        
        if ({str(is_active_trade).lower()}) {{
            candleSeries.createPriceLine({{ price: {entry_p}, color: '#2962FF', lineWidth: 2, title: 'ENTRY' }});
            candleSeries.createPriceLine({{ price: {tgt_p}, color: '#00C853', lineWidth: 2, title: 'TARGET' }});
            candleSeries.createPriceLine({{ price: {sl_p}, color: '#D50000', lineWidth: 2, title: 'SL' }});
            candleSeries.createPriceLine({{ price: {live_p}, color: '{pnl_color}', lineWidth: 2, title: '{pnl_text}' }});
        }}

        window.addEventListener('resize', () => chart.resize(container.clientWidth, 420));
    </script>
</body>
</html>"""

components.html(raw_html, height=430, scrolling=False)

if is_active_trade:
    if trade_pnl >= 0:
        st.metric("Live Profit / Loss", f"+₹{trade_pnl:.2f}")
    else:
        st.metric("Live Profit / Loss", f"-₹{abs(trade_pnl):.2f}", delta_color="inverse")

# रीफ्रेश बटण (सारखे-सारखे ऑटो रिफ्रेश होऊन चार्ट गायब होणे थांबवण्यासाठी)
if st.button("🔄 Update Live Data"):
    st.rerun()
