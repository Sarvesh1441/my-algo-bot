import streamlit as st
import time
import datetime
import pyotp
import requests
from SmartApi import SmartConnect
import json
import os

# ==========================================
# १. पेज, फाईल आणि कॅपिटल सेटिंग्ज (Risk Management)
# ==========================================
st.set_page_config(page_title="Algo Trading Dashboard", page_icon="📈", layout="wide")

# 💰 इथे तुमचे एकूण कॅपिटल टाका (उदा. ५०००० किंवा १०००००)
TOTAL_CAPITAL = 100000  

# 🛡️ रिस्क मॅनेजमेंट: एका ट्रेडमध्ये कॅपिटलच्या फक्त ५% रिस्क घेणे
RISK_PER_TRADE = TOTAL_CAPITAL * 0.05  
SL_POINTS = 15
NIFTY_LOT_SIZE = 65  # १ लॉट = ६५ क्वांटिटी

# 🎯 कॅपिटलनुसार ऑटोमॅटिक लॉट साईझ कॅल्क्युलेशन
calculated_lots = int(RISK_PER_TRADE / (SL_POINTS * NIFTY_LOT_SIZE))
if calculated_lots < 1:
    calculated_lots = 1  # कमीत कमी १ लॉट

LOT_SIZE = calculated_lots * NIFTY_LOT_SIZE

STATE_FILE = "trade_state.json"

def save_state(state_data):
    with open(STATE_FILE, "w") as f:
        json.dump(state_data, f)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "in_position": False, 
        "trade_type": None, 
        "selected_option": "", 
        "option_token": "",
        "premium_entry": 0.0, 
        "entry_spot_price": 0.0, 
        "total_day_pnl": 0.0,
        "day_over": False
    }

st.title("📊 My Live Capital-Based Algo Dashboard")
st.subheader(f"💰 कॅपिटल: ₹{TOTAL_CAPITAL:,} | 🎯 ऑटो लॉट साईझ: {calculated_lots} Lots (Qty: {LOT_SIZE})")

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
# ३. सर्वात जवळची एक्सपायरी शोधणे
# ==========================================
@st.cache_data(ttl=86400)
def fetch_latest_angel_token(strike_price, option_type):
    try:
        url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        res = requests.get(url).json()
        
        valid_options = []
        for item in res:
            if (item.get("exch_seg") == "NFO" and 
                item.get("name") == "NIFTY" and 
                item.get("instrumenttype") == "OPTIDX" and 
                float(item.get("strike", 0)) == (strike_price * 100) and 
                item.get("symbol", "").endswith(option_type)):
                
                expiry_str = item.get("expiry", "")
                if expiry_str:
                    try:
                        exp_date = datetime.datetime.strptime(expiry_str, "%d%b%Y").date()
                        if exp_date >= datetime.date.today():
                            valid_options.append((exp_date, item.get("token"), item.get("symbol")))
                    except:
                        pass
        
        if valid_options:
            valid_options.sort(key=lambda x: x[0])
            latest_expiry = valid_options[0] 
            return latest_expiry[1], latest_expiry[2], latest_expiry[0].strftime("%d-%b-%Y")
    except:
        pass
    return None, None, None

tc = 24433.33  
bc = 24400.00  

col1, col2 = st.columns(2)
col1.metric("📊 Top CPR (TC Level)", f"₹{tc}")
col2.metric("📊 Bottom CPR (BC Level)", f"₹{bc}")

st.markdown("---")

# पोझिशन स्टेट लोड करणे
saved_data = load_state()
if 'in_position' not in st.session_state:
    st.session_state.in_position = saved_data.get("in_position", False)
    st.session_state.trade_type = saved_data.get("trade_type", None)
    st.session_state.selected_option = saved_data.get("selected_option", "")
    st.session_state.option_token = saved_data.get("option_token", "")
    st.session_state.premium_entry = saved_data.get("premium_entry", 0.0)
    st.session_state.entry_spot_price = saved_data.get("entry_spot_price", 0.0)
    st.session_state.total_day_pnl = saved_data.get("total_day_pnl", 0.0)
    st.session_state.day_over = saved_data.get("day_over", False)

# ==========================================
# ४. मुख्य डेटा ट्रॅकिंग
# ==========================================
try:
    spot_data = smart_api.ltpData("NSE", "NIFTY", "99926000")
    spot_price = float(spot_data["data"]["ltp"]) if spot_data.get("status") and spot_data.get("data") else 24630.00
    
    st.metric(label="📈 NIFTY 50 LIVE SPOT PRICE", value=f"₹{spot_price:.2f}")

    if st.session_state.day_over:
        st.warning(f"🔒 आजचा सेटअप पूर्ण झाला आहे! नवीन एन्ट्री ब्लॉक केली आहे. | आजचा एकूण P&L: ₹{st.session_state.total_day_pnl:.2f}")
        if st.button("🔄 उद्यासाठी सिस्टीम रीसेट करा (Reset)"):
            st.session_state.in_position = False
            st.session_state.trade_type = None
            st.session_state.selected_option = ""
            st.session_state.option_token = ""
            st.session_state.premium_entry = 0.0
            st.session_state.entry_spot_price = 0.0
            st.session_state.total_day_pnl = 0.0
            st.session_state.day_over = False
            save_state(dict(st.session_state))
            st.rerun()
        st.stop()

    # --- Waiting Mode ---
    if not st.session_state.in_position:
        st.info(f"⏳ बॉट ब्रेकआऊटची वाट पाहत आहे... | आजचा एकूण P&L: ₹{st.session_state.total_day_pnl:.2f}")
        
        # 🟢 CALL TRIGGER
        if spot_price > tc:
            atm_strike = round(spot_price / 50) * 50
            itm_strike = atm_strike - 50  
            token, symbol_name, expiry_date = fetch_latest_angel_token(itm_strike, "CE")
            
            if token and symbol_name:
                opt_data = smart_api.ltpData("NFO", symbol_name, token)
                entry_premium = float(opt_data["data"]["ltp"]) if opt_data.get("status") and opt_data.get("data") else 140.00
                
                st.session_state.trade_type = "CE"
                st.session_state.selected_option = symbol_name
                st.session_state.option_token = token
                st.session_state.entry_spot_price = spot_price
                st.session_state.premium_entry = entry_premium
                st.session_state.in_position = True
                save_state(dict(st.session_state))
                st.rerun()
            
        # 🔴 PUT TRIGGER
        elif spot_price < bc:
            atm_strike = round(spot_price / 50) * 50
            itm_strike = atm_strike + 50  
            token, symbol_name, expiry_date = fetch_latest_angel_token(itm_strike, "PE")
            
            if token and symbol_name:
                opt_data = smart_api.ltpData("NFO", symbol_name, token)
                entry_premium = float(opt_data["data"]["ltp"]) if opt_data.get("status") and opt_data.get("data") else 140.00
                
                st.session_state.trade_type = "PE"
                st.session_state.selected_option = symbol_name
                st.session_state.option_token = token
                st.session_state.entry_spot_price = spot_price
                st.session_state.premium_entry = entry_premium
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
            if st.session_state.trade_type == "CE":
                spot_change = spot_price - st.session_state.entry_spot_price
            else:
                spot_change = st.session_state.entry_spot_price - spot_price
            live_option_premium = st.session_state.premium_entry + (spot_change * 0.60)

        trade_pnl = (live_option_premium - st.session_state.premium_entry) * LOT_SIZE
        sl_val = st.session_state.premium_entry - SL_POINTS
        tgt_val = st.session_state.premium_entry + (SL_POINTS * 2)

        st.write(f"### 🎯 Active ITM Position: **{st.session_state.selected_option}** ({calculated_lots} Lots - Qty: {LOT_SIZE})")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Buy Entry Price", f"₹{st.session_state.premium_entry:.2f}")
        c2.metric("Live Option Premium", f"₹{live_option_premium:.2f}", delta=f"{live_option_premium - st.session_state.premium_entry:.2f}")
        
        if trade_pnl >= 0:
            c3.metric("Live P&L", f"+₹{trade_pnl:.2f}", delta=f"+₹{trade_pnl:.2f}")
        else:
            c3.metric("Live P&L", f"-₹{abs(trade_pnl):.2f}", delta=f"-₹{abs(trade_pnl):.2f}", delta_color="inverse")
        
        st.write(f"⚠️ **Stoploss (SL):** ₹{sl_val:.2f} | 🎯 **Target (TGT):** ₹{tgt_val:.2f}")
        st.caption(f"💼 आजचा एकूण बंद झालेला P&L: ₹{st.session_state.total_day_pnl:.2f}")
        
        if live_option_premium >= tgt_val:
            st.balloons()
            st.session_state.total_day_pnl += trade_pnl
            st.session_state.in_position = False
            st.session_state.day_over = True
            save_state(dict(st.session_state))
            st.success(f"🎯 TARGET HIT! नफा बुक झाला: ₹{trade_pnl:.2f}")
            time.sleep(2)
            st.rerun()
            
        elif live_option_premium <= sl_val:
            st.session_state.total_day_pnl += trade_pnl
            st.session_state.in_position = False
            st.session_state.day_over = True
            save_state(dict(st.session_state))
            st.error(f"🛑 STOPLOSS HIT! तोटा बुक झाला: ₹{trade_pnl:.2f}")
            time.sleep(2)
            st.rerun()

except Exception as e:
    st.error(f"डेटा ट्रॅक करताना अडचण: {e}")

time.sleep(1)
st.rerun()
