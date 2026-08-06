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
import streamlit.components.v1 as components

# ==========================================
# १. पेज आणि कॅपिटल सेटिंग्ज
# ==========================================
st.set_page_config(
    page_title="Algo Trading Dashboard", 
    page_icon="📈", 
    layout="wide"
)

# दर २ सेकंदाला लाईव्ह डेटा ऑटो-रिफ्रेश करणारी मॅजिक लाईन
st_autorefresh(interval=2000, limit=None, key="live_data_refresher")

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
    "ohlc_data": [],
    "last_candle_time": 0
}

for key, default_val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = saved_data.get(key, default_val)

# ==========================================
# ४. मुख्य डेटा फेचिंग लॉजिक (२ सेकंदाला अपडेट)
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

# --- Waiting Mode ---
if not is_active_trade:
    st.info(f"⏳ BREAKOUT ची वाट पाहत आहे... | P&L: ₹{st.session_state.total_day_pnl:.2f}")
    
    if not st.session_state.ohlc_data:
        st.session_state.ohlc_data = []
        p = spot_price - 8.0
        for i in range(35, 0, -1):
            o = p
            c = p + random.choice([-2.5, -1.0, 1.5, 3.5])
            h = max(o, c) + random.uniform(0.4, 1.2)
            l = min(o, c) - random.uniform(0.4, 1.2)
            st.session_state.ohlc_data.append({
                "time": current_ts - (i * 300), "open": round(o, 2),
                "high": round(h, 2), "low": round(l, 2), "close": round(c, 2)
            })
            p = c
            
    if spot_price > tc or spot_price < bc:
        trade_type = "CE" if spot_price > tc else "PE"
        atm_strike = round(spot_price / 50) * 50
        itm_strike = atm_strike - 50 if trade_type == "CE" else atm_strike + 50
        
        token, symbol_name, _ = fetch_latest_angel_token(itm_strike, trade_type)
        if token and symbol_name:
            opt_data = smart_api.ltpData("NFO", symbol_name, token)
            entry_premium = 140.00
            if opt_data and opt_data.get("status") and opt_data.get("data"):
                entry_premium = float(opt_data["data"]["ltp"])
            
            st.session_state.trade_type = trade_type
            st.session_state.selected_option = symbol_name
            st.session_state.option_token = token
            st.session_state.premium_entry = entry_premium
            st.session_state.current_sl = entry_premium - SL_POINTS
            st.session_state.current_tgt = entry_premium + 30
            st.session_state.sl_trailed_to_cost = False
            
            st.session_state.ohlc_data = []
            p = entry_premium - 4.0
            for i in range(35, 0, -1):
                o = p
                c = p + random.choice([-1.0, 0.5, 1.8])
                h = max(o, c) + random.uniform(0.2, 0.6)
                l = min(o, c) - random.uniform(0.2, 0.6)
                st.session_state.ohlc_data.append({
                    "time": current_ts - (i * 300), "open": round(o, 2),
                    "high": round(h, 2), "low": round(l, 2), "close": round(c, 2)
                })
                p = c
            st.session_state.in_position = True
            save_state(dict(st.session_state))
            st.rerun()

# --- Active Tracking Mode ---
else:
    live_option_premium = st.session_state.premium_entry
    if st.session_state.option_token:
        try:
            opt_data = smart_api.ltpData("NFO", st.session_state.selected_option, st.session_state.option_token)
            if opt_data and opt_data.get("status") and opt_data.get("data"):
                live_option_premium = float(opt_data["data"]["ltp"])
        except Exception:
            pass

    # Trailing SL Check (+20 Points)
    if not st.session_state.sl_trailed_to_cost:
        if (live_option_premium - st.session_state.premium_entry) >= 20:
            st.session_state.current_sl = st.session_state.premium_entry
            st.session_state.current_tgt = st.session_state.premium_entry + 65
            st.session_state.sl_trailed_to_cost = True
            save_state(dict(st.session_state))

    # 🎯 लाईन २४७ फिक्स: KeyError टाळण्यासाठी सुरक्षित '.get()' रचना
    if st.session_state.ohlc_data:
        last_c = st.session_state.ohlc_data[-1]
        old_high = last_c.get("high", live_option_premium)
        old_low = last_c.get("low", live_option_premium)
        
        last_c["high"] = float(max(old_high, live_option_premium))
        last_c["low"] = float(min(old_low, live_option_premium))
        last_c["close"] = float(live_option_premium)

    trade_pnl = (live_option_premium - st.session_state.premium_entry) * LOT_SIZE

    st.write(f"### 🎯 Active Position: **{st.session_state.selected_option}**")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Buy Entry Price", f"₹{st.session_state.premium_entry:.2f}")
    c2.metric("⚡ Live Premium", f"₹{live_option_premium:.2f}", delta=f"{live_option_premium - st.session_state.premium_entry:.2f} pts")
    
    sl_lbl = "Cost-to-Cost" if st.session_state.sl_trailed_to_cost else "Original SL"
    c3.metric("Current SL", f"₹{st.session_state.current_sl:.2f}", delta=sl_lbl)
    
    tgt_lbl = "1:3 Target" if st.session_state.sl_trailed_to_cost else "Primary Tgt"
    c4.metric("Dynamic Target", f"₹{st.session_state.current_tgt:.2f}", delta=tgt_lbl)
    
    st.markdown("---")

    # Target or SL Exit Check
    if live_option_premium >= st.session_state.current_tgt or live_option_premium <= st.session_state.current_sl:
        st.session_state.total_day_pnl += trade_pnl
        st.session_state.in_position = False
        st.session_state.day_over = True
        save_state(dict(st.session_state))
        st.rerun()

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
        st.metric("Live Running Profit", f"+₹{trade_pnl:.2f}")
    else:
        st.metric("Live Running Loss", f"-₹{abs(trade_pnl):.2f}", delta_color="inverse")
