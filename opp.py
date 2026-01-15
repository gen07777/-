import streamlit as st
import datetime
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests
import numpy as np
import math
import re

# ==========================================
# 1. アプリ設定 & 定数定義
# ==========================================
st.set_page_config(layout="wide", page_title="大西港 潮汐予測")

# APIキー (OpenWeatherMap)
OWM_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"
STANDARD_PRESSURE = 1013

# ==========================================
# 2. 内蔵データ (1/15 - 2/14) - 頂いた正確なデータ
# ==========================================
MANUAL_TIDE_DATA = {
    "2026-01-15": [("01:00", 54, "L"), ("08:19", 287, "H"), ("14:10", 163, "L"), ("19:19", 251, "H")],
    "2026-01-16": [("02:00", 37, "L"), ("09:00", 309, "H"), ("15:00", 149, "L"), ("20:19", 260, "H")],
    "2026-01-17": [("02:59", 20, "L"), ("09:50", 327, "H"), ("15:50", 133, "L"), ("21:00", 272, "H")],
    "2026-01-18": [("03:39", 7, "L"), ("10:29", 340, "H"), ("16:29", 117, "L"), ("21:59", 284, "H")],
    "2026-01-19": [("04:19", 0, "L"), ("11:00", 348, "H"), ("17:00", 102, "L"), ("22:39", 293, "H")],
    "2026-01-20": [("04:59", 0, "L"), ("11:39", 350, "H"), ("17:39", 90, "L"), ("23:19", 299, "H")],
    "2026-01-21": [("05:30", 8, "L"), ("12:00", 346, "H"), ("18:10", 80, "L")],
    "2026-01-22": [("00:00", 299, "H"), ("06:09", 23, "L"), ("12:39", 337, "H"), ("18:49", 73, "L")],
    "2026-01-23": [("00:39", 295, "H"), ("06:49", 44, "L"), ("13:09", 325, "H"), ("19:20", 70, "L")],
    "2026-01-24": [("01:20", 285, "H"), ("07:20", 71, "L"), ("13:40", 309, "H"), ("20:00", 70, "L")],
    "2026-01-25": [("02:19", 271, "H"), ("08:00", 102, "L"), ("14:19", 290, "H"), ("20:59", 73, "L")],
    "2026-01-26": [("03:19", 256, "H"), ("08:59", 134, "L"), ("14:59", 271, "H"), ("21:49", 76, "L")],
    "2026-01-27": [("04:39", 246, "H"), ("10:00", 163, "L"), ("15:59", 252, "H"), ("23:00", 76, "L")],
    "2026-01-28": [("06:19", 251, "H"), ("11:59", 178, "L"), ("17:00", 239, "H")],
    "2026-01-29": [("00:19", 68, "L"), ("07:40", 269, "H"), ("13:30", 173, "L"), ("18:30", 237, "H")],
    "2026-01-30": [("01:29", 52, "L"), ("08:40", 293, "H"), ("14:39", 156, "L"), ("19:40", 246, "H")],
    "2026-01-31": [("02:20", 34, "L"), ("09:20", 314, "H"), ("15:20", 136, "L"), ("20:40", 262, "H")],
    "2026-02-01": [("03:10", 17, "L"), ("10:00", 331, "H"), ("16:00", 115, "L"), ("21:29", 279, "H")],
    "2026-02-02": [("03:59", 6, "L"), ("10:39", 342, "H"), ("16:39", 96, "L"), ("22:10", 295, "H")],
    "2026-02-03": [("04:30", 1, "L"), ("11:00", 348, "H"), ("17:09", 79, "L"), ("22:59", 306, "H")],
    "2026-02-04": [("05:00", 4, "L"), ("11:39", 347, "H"), ("17:40", 66, "L"), ("23:30", 311, "H")],
    "2026-02-05": [("05:40", 15, "L"), ("12:00", 341, "H"), ("18:10", 57, "L")],
    "2026-02-06": [("00:09", 310, "H"), ("06:19", 34, "L"), ("12:39", 331, "H"), ("18:49", 52, "L")],
    "2026-02-07": [("00:49", 302, "H"), ("06:59", 58, "L"), ("13:00", 316, "H"), ("19:20", 53, "L")],
    "2026-02-08": [("01:30", 288, "H"), ("07:29", 88, "L"), ("13:39", 298, "H"), ("20:00", 58, "L")],
    "2026-02-09": [("02:20", 270, "H"), ("08:10", 121, "L"), ("14:10", 278, "H"), ("20:59", 67, "L")],
    "2026-02-10": [("03:30", 252, "H"), ("09:00", 153, "L"), ("14:59", 256, "H"), ("21:59", 76, "L")],
    "2026-02-11": [("05:00", 244, "H"), ("10:39", 178, "L"), ("15:59", 236, "H"), ("23:19", 78, "L")],
    "2026-02-12": [("06:59", 254, "H"), ("12:40", 181, "L"), ("17:39", 226, "H")],
    "2026-02-13": [("00:40", 69, "L"), ("08:00", 277, "H"), ("14:09", 163, "L"), ("19:00", 233, "H")],
    "2026-02-14": [("01:59", 51, "L"), ("08:59", 300, "H"), ("14:59", 140, "L"), ("20:19", 252, "H")]
}

# ==========================================
# 3. スタイル & フォント設定
# ==========================================
st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 3rem; }
    h5 { margin-bottom: 0px; }
    /* スマホ対策 */
    @media (max-width: 640px) {
        div[data-testid="stHorizontalBlock"] {
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            gap: 8px !important;
            padding-right: 0px !important;
        }
        div[data-testid="column"] {
            width: calc(50% - 4px) !important;
            flex: 0 0 calc(50% - 4px) !important;
            min-width: 0 !important;
        }
        div.stButton > button {
            width: 100% !important;
            font-size: 0.9rem !important;
            padding: 0px !important;
            height: 2.8rem !important;
            white-space: nowrap !important;
            margin: 0px !important;
        }
    }
    div.stButton > button { width: 100%; margin-top: 0px; }
</style>
""", unsafe_allow_html=True)

def configure_font():
    plt.rcParams.update(plt.rcParamsDefault)
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans', 'Verdana']
configure_font()

# ==========================================
# 4. データ処理ロジック
# ==========================================
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

@st.cache_data(ttl=3600)
def fetch_jma_data_map(year):
    """気象庁から年間データを取得 (もし公開されていれば自動適用)"""
    url = f"https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt/{year}/344311.txt"
    headers = {"User-Agent": "Mozilla/5.0"}
    data_map = {}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            lines = res.text.splitlines()
            for line in lines:
                parts = line.split()
                if len(parts) < 28 or not parts[0].isdigit(): continue
                m, d = int(parts[2]), int(parts[3])
                date_str = f"{year}-{m:02d}-{d:02d}"
                levels = [int(h) for h in parts[4:28]]
                data_map[date_str] = levels
    except:
        pass
    return data_map

def get_moon_age(date_obj):
    base = datetime.date(2000, 1, 6)
    return ((date_obj - base).days) % 29.53059

def get_tide_name(moon_age):
    m = int(moon_age)
    if m >= 30: m -= 30
    if m >= 28 or m <= 2: return "大潮"
    if 13 <= m <= 17: return "大潮"
    if 3 <= m <= 5: return "中潮"
    if 18 <= m <= 20: return "中潮"
    if 6 <= m <= 9: return "小潮"
    if 21 <= m <= 24: return "小潮"
    if 10 <= m <= 12: return "長潮"
    if m == 25: return "長潮"
    if m == 13 or 26 <= m <= 27: return "若潮"
    return "中潮"

class OnishiTideModel:
    def __init__(self, pressure_hpa, year, manual_input=""):
        # 1. 気象庁データ取得 (あれば)
        self.jma_map = fetch_jma_data_map(year)
        # 2. 気圧補正
        self.pressure_correction = int(STANDARD_PRESSURE - pressure_hpa)
        # 3. 手動入力データの解析
        self.user_data = self.parse_user_input(manual_input)

    def parse_user_input(self, text):
        """ユーザー入力(CSV形式等)を解析して辞書にする"""
        data = {}
        if not text: return data
        
        # 簡易フォーマット: YYYY-MM-DD HH:MM Level
        # 例: 2026-02-15 09:00 300
        lines = text.splitlines()
        for line in lines:
            try:
                parts = line.split()
                if len(parts) >= 3:
                    d_str = parts[0] # 2026-02-15
                    t_str = parts[1] # 09:00
                    lvl = int(parts[2])
                    
                    if d_str not in data: data[d_str] = []
                    # タイプ判定(簡易)
                    ptype = "H" if lvl > 150 else "L" 
                    data[d_str].append((t_str, lvl, ptype))
            except:
                pass
        return data

    def generate_daily_curve(self, date_str):
        # 優先順位: 1.ユーザー入力 -> 2.内蔵手動データ -> 3.気象庁データ
        
        times = []
        levels = []
        base_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        
        # A. ピーク情報がある場合 (ユーザー入力 or 内蔵)
        peaks = []
        if date_str in self.user_data:
            peaks = self.user_data[date_str]
        elif date_str in MANUAL_TIDE_DATA:
            peaks = MANUAL_TIDE_DATA[date_str]
            
        if peaks:
            for p_time, p_level, _ in peaks:
                h, m = map(int, p_time.split(":"))
                dt = base_date.replace(hour=h, minute=m)
                levels.append(p_level + self.pressure_correction)
                times.append(dt)
            return times, levels

        # B. 気象庁データ (毎時) がある場合
        if date_str in self.
