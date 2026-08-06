import streamlit as st
import time
import datetime
import pyotp
import requests
from SmartApi import SmartConnect
import json
import os
import pandas as pd
import plotly.graph_objects as go

# ==========================================
# १. पेज आणि कॅपिटल सेटिंग्ज
# ==========================================
st.set_page_config(page_title="Algo Trading Dashboard", page_icon="📈", layout="wide")

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
st.subheader(f"💰 Capital: ₹{TOTAL_CAPITAL:,} | Lots: {calculated_lots} (Qty: {LOT_SIZE})")

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
        for item in res:
            if (item.get("exch_seg") == "NFO" and item.get("name") == "NIFTY" and 
                item.get("instrumenttype") == "OPTIDX" and float(item.get("strike", 0)) == (strike_price * 100) and 
                item.get("symbol", "").endswith(option_type)):
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
# ४. मुख्य ट्रॅकिंग आणि वेळेसह बारीक कॅन्डलस्टिक चार्ट
# ==========================================
try:
    spot_data = smart_api.ltpData("NSE", "NIFTY", "99926000")
    spot_price = float(spot_data["data"]["ltp"]) if spot_data.get("status") and spot_data.get("data") else 24630.00
    st.metric(label="📈 NIFTY 50 LIVE SPOT PRICE", value=f"₹{spot_price:.2f}")

    if st.session_state.day_over:
        st.warning(f"🔒 आजचा सेटअप पूर्ण झाला आहे! | P&L: ₹{st.session_state.total_day_pnl:.2f}")
        if st.button("🔄 उद्यासाठी रीसेट करा"):
            for k, v in defaults.items():
                st.session_state[k] = v
            save_state(dict(st.session_state))
            st.rerun()
        st.stop()

    # --- Waiting Mode ---
    if not st.session_state.in_position:
        st.info(f"⏳ ब्रेकआऊटची वाट पाहत आहे... | P&L: ₹{st.session_state.total_day_pnl:.2f}")
        
        if spot_price > tc or spot_price < bc:
            trade_type = "CE" if spot_price > tc else "PE"
            atm_strike = round(spot_price / 50) * 50
            itm_strike = atm_strike - 50 if trade_type == "CE" else atm_strike + 50
            
            token, symbol_name, _ = fetch_latest_angel_token(itm_strike, trade_type)
            if token and symbol_name:
                opt_data = smart_api.ltpData("NFO", symbol_name, token)
                entry_premium = float(opt_data["data"]["ltp"]) if opt_data.get("status") and opt_data.get("data") else 140.00
                
                # 🎯 २० सलग बारीक कॅन्डल्सचा बॅकअप डेटा जनरेट करणे
                now_time = datetime.datetime.now()
                base_data = []
                for i in range(25, 0, -1):
                    t_str = (now_time - datetime.timedelta(seconds=i*10)).strftime("%H:%M:%S")
                    base_data.append({
                        "Time": t_str, "Open": entry_premium, "High": entry_premium + 0.3, "Low": entry_premium - 0.3, "Close": entry_premium
                    })
                
                st.session_state.trade_type = trade_type
                st.session_state.selected_option = symbol_name
                st.session_state.option_token = token
                st.session_state.premium_entry = entry_premium
                st.session_state.current_sl = entry_premium - SL_POINTS
                st.session_state.current_tgt = entry_premium + 30
                st.session_state.sl_trailed_to_cost = False
                st.session_state.ohlc_data = base_data
                st.session_state.last_candle_time = int(time.time())
                st.session_state.in_position = True
                save_state(dict(st.session_state))
                st.rerun()
                
    # --- Active Tracking Mode ---
    else:
        live_option_premium = 0.0
        if st.session_state.option_token:
            opt_data = smart_api.ltpData("NFO", st.session_state.selected_option, st.session_state.option_token)
            if opt_data.get("status") and opt_data.get("data"):
                live_option_premium = float(opt_data["data"]["ltp"])
        
        if live_option_premium == 0.0:
            live_option_premium = st.session_state.premium_entry

        current_time_str = datetime.datetime.now().strftime("%H:%M:%S")
        current_ts = int(time.time())
        
        # जर डेटा कमी असेल तर २५ कॅन्डल्सचा संच तयार करणे
        if not st.session_state.ohlc_data or len(st.session_state.ohlc_data) < 10:
            now_time = datetime.datetime.now()
            st.session_state.ohlc_data = []
            for i in range(25, 0, -1):
                t_str = (now_time - datetime.timedelta(seconds=i*10)).strftime("%H:%M:%S")
                st.session_state.ohlc_data.append({
                    "Time": t_str, "Open": live_option_premium, "High": live_option_premium + 0.3, "Low": live_option_premium - 0.3, "Close": live_option_premium
                })
            st.session_state.last_candle_time = current_ts

        last_candle = st.session_state.ohlc_data[-1]
        last_candle["High"] = float(max(last_candle["High"], live_option_premium))
        last_candle["Low"] = float(min(last_candle["Low"], live_option_premium))
        last_candle["Close"] = float(live_option_premium)
        
        if current_ts - st.session_state.last_candle_time >= 10:
            st.session_state.ohlc_data.append({
                "Time": current_time_str, "Open": live_option_premium, "High": live_option_premium, "Low": live_option_premium, "Close": live_option_premium
            })
            st.session_state.last_candle_time = current_ts

        if len(st.session_state.ohlc_data) > 30:
            st.session_state.ohlc_data.pop(0)

        if not st.session_state.sl_trailed_to_cost:
            if (live_option_premium - st.session_state.premium_entry) >= 20:
                st.session_state.current_sl = st.session_state.premium_entry
                st.session_state.current_tgt = st.session_state.premium_entry + 65
                st.session_state.sl_trailed_to_cost = True
                save_state(dict(st.session_state))

        trade_pnl = (live_option_premium - st.session_state.premium_entry) * LOT_SIZE

        st.write(f"### 🎯 Active ITM Position: **{st.session_state.selected_option}**")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Buy Entry Price", f"₹{st.session_state.premium_entry:.2f}")
        c2.metric("Live Option Premium", f"₹{live_option_premium:.2f}")
        
        sl_delta_text = "Cost-to-Cost" if st.session_state.sl_trailed_to_cost else "Original SL"
        c3.metric("Current SL", f"₹{st.session_state.current_sl:.2f}", delta=sl_delta_text)
        
        tgt_delta_text = "1:3 Target" if st.session_state.sl_trailed_to_cost else "Primary Tgt"
        c4.metric("Dynamic Target", f"₹{st.session_state.current_tgt:.2f}", delta=tgt_delta_text)
        
        st.markdown("---")
        
        # 🕯️ **अत्यंत बारीक कॅन्डल्स आणि अचूक लाईव्ह टाइम लेआऊट**
        st.subheader("🕯️ Live Option Premium Candlestick Chart")
        df_candles = pd.DataFrame(st.session_state.ohlc_data)
        
        fig = go.Figure(data=[go.Candlestick(
            x=df_candles['Time'],
            open=df_candles['Open'],
            high=df_candles['High'],
            low=df_candles['Low'],
            close=df_candles['Close'],
            increasing=dict(line=dict(color='#26a69a', width=1), fillcolor='#26a69a'),
            decreasing=dict(line=dict(color='#ef5350', width=1), fillcolor='#ef5350'),
            whiskerwidth=0.0
        )])
        
        fig.update_layout(
            xaxis_rangeslider_visible=False,
            height=400,
            margin=dict(l=20, r=40, t=10, b=50),
            paper_bgcolor='#ffffff',  
            plot_bgcolor='#ffffff',
            bargap=0.75, # 🎯 ७५% गॅप ठेवली आहे ज्यामुळे कॅन्डल्स एकदम सुबक, बारीक दिसतील
            xaxis=dict(
                gridcolor='#f0f3fa', 
                type='category', 
                tickfont=dict(color='#333333', size=10),
                tickangle=-45, # 🎯 वेळेचे आकडे तिरके आणि नीट वाचता येण्यासारखे दिसायला
                showticklabels=True
            ),
            yaxis=dict(
                gridcolor='#f0f3fa', 
                side="right",    
                tickfont=dict(color='#333333', size=10),
                autorange=True  
            )
        )
        
        st.plotly_chart(fig, use_container_width=True)

        if trade_pnl >= 0:
            st.metric("Live Profit / Loss", f"+₹{trade_pnl:.2f}", delta=f"+₹{trade_pnl:.2f}")
        else:
            st.metric("Live Profit / Loss", f"-₹{abs(trade_pnl):.2f}", delta=f"-₹{abs(trade_pnl):.2f}", delta_color="inverse")
            
        st.caption(f"💼 आजचा एकूण बंद झालेला P&L: ₹{st.session_state.total_day_pnl:.2f}")
        
        # Exit Checks
        if live_option_premium >= st.session_state.current_tgt:
            st.balloons()
            st.session_state.total_day_pnl += trade_pnl
            st.session_state.in_position = False
            st.session_state.day_over = True
            save_state(dict(st.session_state))
            st.rerun()
        elif live_option_premium <= st.session_state.current_sl:
            st.session_state.total_day_pnl += trade_pnl
            st.session_state.in_position = False
            st.session_state.day_over = True
            save_state(dict(st.session_state))
            st.rerun()

except Exception as e:
    st.error(f"डेटा ट्रॅक करताना अडचण: {e}")

time.sleep(1)
st.rerun()
