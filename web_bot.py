import streamlit as st
import time
import datetime
import pyotp
import requests
from SmartApi import SmartConnect

# ==========================================
# १. पेज सेटिंग्ज
# ==========================================
st.set_page_config(page_title="Algo Trading Dashboard", page_icon="📈", layout="wide")

st.title("📊 My Live Algo Paper Trading Dashboard")
st.subheader("Angel One Live API द्वारे ऑप्शन्स ट्रॅकिंग")

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
    st.success("✅ Angel One Live API यशस्वीरित्या कनेक्ट झाली आहे!")

# ==========================================
# ३. सर्वात जवळची (Latest Current) एक्सपायरी शोधणारे फंक्शन
# ==========================================
@st.cache_data(ttl=86400)
def fetch_latest_angel_token(strike_price, option_type):
    """Angel One च्या मास्टर लिस्टधून चालू महिन्याची सर्वात जवळची एक्सपायरी शोधणे"""
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
                
                # एक्सपायरी डेट फॉरमॅट करून लिस्टमध्ये ठेवणे (उदा. 11AUG26 किंवा 20AUG26)
                expiry_str = item.get("expiry", "")
                if expiry_str:
                    try:
                        # Angel One चा एक्सपायरी फॉरमॅट DDMMMYYYY असा असतो
                        exp_date = datetime.datetime.strptime(expiry_str, "%d%b%Y").date()
                        # फक्त आजच्या किंवा आजच्या नंतरच्या एक्सपायरी गोळा करणे
                        if exp_date >= datetime.date.today():
                            valid_options.append((exp_date, item.get("token"), item.get("symbol")))
                    except:
                        pass
        
        # सर्व व्हॅलिड ऑप्शन्सना एक्सपायरी तारखेनुसार चढत्या क्रमाने (Ascending) सॉर्ट करणे
        # यामुळे सर्वात जवळची (Latest) एक्सपायरी पहिली येईल
        if valid_options:
            valid_options.sort(key=lambda x: x[0])
            latest_expiry = valid_options[0] # पहिली तारीख म्हणजेच सर्वात जवळची एक्सपायरी
            return latest_expiry[1], latest_expiry[2], latest_expiry[0].strftime("%d-%b-%Y")
            
    except Exception as e:
        pass
    return None, None, None

# ==========================================
# ४. लाईव्ह डेटा ट्रॅकिंग
# ==========================================
try:
    # १. Angel One कडून NIFTY Spot चा थेट भाव
    spot_data = smart_api.ltpData("NSE", "NIFTY", "99926000")
    spot_price = float(spot_data["data"]["ltp"]) if spot_data.get("status") and spot_data.get("data") else 24630.00
    
    st.metric(label="📈 NIFTY 50 LIVE SPOT PRICE (Angel One)", value=f"₹{spot_price:.2f}")

    # २. २४६५० CE चा चालू आठवड्याचा सर्वात जवळचा टोकन शोधणे
    token, symbol_name, expiry_date = fetch_latest_angel_token(24650, "CE")
    
    live_option_premium = 0.0
    
    if token and symbol_name:
        opt_data = smart_api.ltpData("NFO", symbol_name, token)
        if opt_data.get("status") and opt_data.get("data"):
            live_option_premium = float(opt_data["data"]["ltp"])
    
    # जर काही कारणाने API ला डेटा मिळाला नाही तर शेवटचा चालू भाव
    if live_option_premium == 0.0:
        live_option_premium = 146.35

    entry_price = 140.00
    trade_pnl = (live_option_premium - entry_price) * 25
    sl_val = entry_price - 15
    tgt_val = entry_price + 30

    st.markdown("---")
    st.write(f"### 🎯 Active Position: **{symbol_name if symbol_name else 'NIFTY 24650 CE'}**")
    if expiry_date:
        st.info(f"📅 डिटेक्ट झालेली सर्वात जवळची एक्सपायरी तारीख: **{expiry_date}**")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Buy Entry Price", f"₹{entry_price:.2f}")
    c2.metric("Live Option Premium (Angel One Current Expiry)", f"₹{live_option_premium:.2f}", delta=f"{live_option_premium - entry_price:.2f}")
    
    if trade_pnl >= 0:
        c3.metric("Live P&L", f"+₹{trade_pnl:.2f}", delta=f"+₹{trade_pnl:.2f}")
    else:
        c3.metric("Live P&L", f"-₹{abs(trade_pnl):.2f}", delta=f"-₹{abs(trade_pnl):.2f}", delta_color="inverse")
    
    st.write(f"⚠️ **Stoploss (SL):** ₹{sl_val:.2f} | 🎯 **Target (TGT):** ₹{tgt_val:.2f}")

except Exception as e:
    st.error(f"डेटा ट्रॅक करताना अडचण: {e}")

# १ सेकंदाने ऑटो रिफ्रेश
time.sleep(1)
st.rerun()
