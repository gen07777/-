import streamlit as st
import datetime
import math
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager
import requests
import numpy as np

# ---------------------------------------------------------
# アプリ設定
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="Onishi Port Construction Tide")
OWM_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"

# ---------------------------------------------------------
# CSS: レイアウト調整
# ---------------------------------------------------------
st.markdown("""
<style>
    div.stButton > button { width: 100%; height: 3.0rem; font-size: 1rem; margin-top: 0px; }
    [data-testid="column"] { min-width: 0px !important; flex: 1 !important; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    h5 { margin-bottom: 0px; }
</style>
""", unsafe_allow_html=True)

def configure_font():
    plt.rcParams['font.family'] = 'sans-serif'
configure_font()

# ---------------------------------------------------------
# セッション状態
# ---------------------------------------------------------
if 'view_date' not in st.session_state:
    now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    st.session_state['view_date'] = now_jst.date()

# ---------------------------------------------------------
# API: 気圧自動取得
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def get_current_pressure():
    lat, lon = 34.234, 132.831
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OWM_API_KEY}&units=metric"
    try:
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            return float(res.json()['main']['pressure'])
    except:
        pass
    return 1013.0

# ---------------------------------------------------------
# 月齢・潮名
# ---------------------------------------------------------
def get_moon_age(date_obj):
    base = datetime.date(2000, 1, 6)
    return ((date_obj - base).days) % 29.53059

def get_tide_name(moon_age):
    m = int(moon_age)
    if m >= 30: m -= 30
    if 0<=m<=2 or 14<=m<=17 or 29<=m<=30: return "大潮 (Spring)"
    elif 3<=m<=5 or 18<=m<=20: return "中潮 (Middle)"
    elif 6<=m<=9 or 21<=m<=24: return "小潮 (Neap)"
    elif 10<=m<=12: return "長潮 (Long)"
    elif m==13 or 25<=m<=28: return "若潮 (Young)"
    return "中潮 (Middle)"

# ---------------------------------------------------------
# 潮汐モデル (釣割基準)
# ---------------------------------------------------------
class ConstructionTideModel:
    def __init__(self, pressure_hpa):
        self.epoch_time = datetime.datetime(2026, 1, 7, 12, 39)
        self.msl = 180.0
        self.pressure_correction = (1013.0 - pressure_hpa) * 1.0
        self.base_amp_factor = (342.0 - 180.0) / 1.0

        self.consts = [
            {'name':'M2', 'speed':28.984104, 'amp':1.00, 'phase':0},
            {'name':'S2', 'speed':30.000000, 'amp':0.46, 'phase':0},
            {'name':'K1', 'speed':15.041069, 'amp':0.38, 'phase':0},
            {'name':'O1', 'speed':13.943036, '
