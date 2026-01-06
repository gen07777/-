import streamlit as st
import datetime
import math
import calendar
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ---------------------------------------------------------
# 計算ロジック
# ---------------------------------------------------------
class OnishiTideCalculator:
    def __init__(self):
        self.CORRECTION_RATIO = 1.0
        self.TIME_OFFSET_MINUTES = 0
        self.MSL = 250.0 
        self.CONSTITUENTS = {
            'M2': {'amp': 130.0, 'phase': 200.0, 'speed': 28.9841042},
            'S2': {'amp': 50.0,  'phase': 230.0, 'speed': 30.0000000},
            'K1': {'amp': 35.0,  'phase': 180.0, 'speed': 15.0410686},
            'O1': {'amp': 30.0,  'phase': 160.0, 'speed': 13.9430356}
        }

    def _calculate_astronomical_tide(self, target_datetime):
        base_date = datetime.datetime(target_datetime.year, 1, 1)
        delta_hours = (target_datetime - base_date).total_seconds() / 3600.0
        tide_height = self.MSL
        for name, const in self.CONSTITUENTS.items():
            theta = math.radians(const['speed'] * delta_hours - const['phase'])
            tide_height += const['amp'] * math.cos(theta)
        return tide_height

    def get_period_data(self, year, month, start_day, end_day, interval_minutes=5):
        """指定期間のデータを生成 (精度を上げるため5分刻み)"""
        detailed_data = []
        
        start_dt = datetime.datetime(year, month, start_day)
        if end_day == calendar.monthrange(year, month)[1]:
            end_dt = datetime.datetime(year, month, end_day, 23, 55)
        else:
            end_dt = datetime.datetime(year, month, end_day + 1) - datetime.timedelta(minutes=interval_minutes)

        current_dt = start_dt
        while current_dt <= end_dt:
            calc_time_offset = current_dt - datetime.timedelta(minutes=self.TIME_OFFSET_MINUTES)
            base_level = self._calculate_astronomical_tide(calc_time_offset)
            onishi_level = base_level * self.CORRECTION_RATIO
            
            detailed_data.append({
                "raw_time": current_dt,
                "Level_cm": onishi_level
            })
            current_dt += datetime.timedelta(minutes=interval_minutes)
            
        return detailed_data

# ---------------------------------------------------------
# アプリ設定
# ---------------------------------------------------------
st.set_page_config(layout="wide")
st.title("大西港 潮位ビジュアライザー")

# --- サイドバー設定 ---
with st.sidebar:
    st.header("設定")
    target_cm = st.number_input("基準潮位 (cm)", value=150, step=10, help="この高さより低くなる時間を探します")
    
    st.subheader("活動時間フィルタ")
    # 時間範囲選択 (初期値 7:00 - 23:00)
    start_hour, end_hour = st.slider(
        "表示する時間帯:",
        0, 24, (7, 23),
        format="%d時"
    )

# --- メイン操作エリア ---
col1, col2, col3 = st.columns([1, 1, 3])
with col1:
    year_sel = st.number_input("年", value=datetime.date.today().year)
with col2:
    month_sel = st.number_input("月", value=datetime.date.today().month, min_value=1, max_value=12)

# 期間計算
last_day = calendar.monthrange(year_sel, month_sel)[1]

# 前半・後半ボタンの作成
with col3:
    period_label = st.radio(
        "表示期間", # ラベルは隠せないのでシンプルに
        [f"{month_sel}月前半 (1日-15日)", f"{month_sel}月後半 (16日-{last_day}日)"],
        horizontal=True,
        label_visibility="collapsed" # ラベルを隠す設定
    )

# 選択に基づき日付範囲を決定
if "前半" in period_label:
    start_d, end_d = 1, 15
else:
    start_d, end_d = 16, last_day

# データ計算
calculator = OnishiTideCalculator()
data = calculator.get_period_data(year_sel, month_sel, start_d, end_d)
df = pd.DataFrame(data)

# ---------------------------------------------------------
# グラフ描画
# ---------------------------------------------------------
st.subheader(f"潮位グラフ: {period_label}")

# グラフ作成
fig, ax = plt.subplots(figsize=(15, 8)) # 少し縦に大きく

# 1. 潮位線
ax.plot(df['raw_time'], df['Level_cm'], color='#1f77b4', linewidth=1.5, alpha=0.7)

# 2. ターゲットライン
ax.axhline(y=target_cm, color='black', linestyle='--', linewidth=1)

# 3. 塗りつぶし & 時間検出ロジック
# 条件: 指定潮位以下 かつ 指定時間内
hours = df['raw_time'].dt.hour
