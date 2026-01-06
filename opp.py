import streamlit as st
import datetime
import math
import calendar
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import re

# ---------------------------------------------------------
# アプリ設定
# ---------------------------------------------------------
st.set_page_config(layout="wide")

# ---------------------------------------------------------
# 計算ロジック (広島港ベース + 大西港補正)
# ---------------------------------------------------------
class OnishiTideCalculator:
    def __init__(self):
        # 広島港(宇品)の調和定数
        self.CONSTITUENTS = {
            'M2': {'amp': 132.0, 'phase': 206.5, 'speed': 28.9841042},
            'S2': {'amp': 48.0,  'phase': 242.6, 'speed': 30.0000000},
            'K1': {'amp': 37.0,  'phase': 191.0, 'speed': 15.0410686},
            'O1': {'amp': 30.0,  'phase': 172.6, 'speed': 13.9430356}
        }
        self.MSL = 180.0 
        self.TIME_OFFSET_MINUTES = 10 
        self.CORRECTION_RATIO = 0.98

    def _calculate_astronomical_tide(self, target_datetime):
        base_date = datetime.datetime(target_datetime.year, 1, 1)
        delta_hours = (target_datetime - base_date).total_seconds() / 3600.0
        tide_height = self.MSL
        for name, const in self.CONSTITUENTS.items():
            theta = math.radians(const['speed'] * delta_hours - const['phase'])
            tide_height += const['amp'] * math.cos(theta)
        return tide_height

    def get_period_data(self, year, month, start_day, end_day, interval_minutes=5):
        detailed_data = []
        start_dt = datetime.datetime(year, month, start_day)
        last_day_of_month = calendar.monthrange(year, month)[1]
        if end_day > last_day_of_month: end_day = last_day_of_month
        end_dt = datetime.datetime(year, month, end_day, 23, 55)

        current_dt = start_dt
        while current_dt <= end_dt:
            calc_time_offset = current_dt - datetime.timedelta(minutes=self.TIME_OFFSET_MINUTES)
            base_level = self._calculate_astronomical_tide(calc_time_offset)
            onishi_level = base_level * self.CORRECTION_RATIO
            detailed_data.append({"raw_time": current_dt, "Level_cm": onishi_level})
            current_dt += datetime.timedelta(minutes=interval_minutes)
        return detailed_data

# ---------------------------------------------------------
# メイン画面構成
# ---------------------------------------------------------
st.title("大西港 潮位ビジュアライザー")
st.caption("データ参照元: 広島港基準 + 大西港補正 (+10分)")

# --- 設定エリア ---
st.markdown("### 条件設定")
col1, col2 = st.columns(2)
with col1:
    year_sel = st.number_input("対象年", value=datetime.date.today().year)
with col2:
    period_options = [f"{m}月前半 (1日-15日)" for m in range(1, 13)] + [f"{m}月後半 (16日-末日)" for m in range(1, 13)]
    period_options.sort(key=lambda x: int(re.match(r"(\d+)", x).group(1)) + (0.5 if "後半" in x else 0))
    current_month = datetime.date.today().month
    default_index = (current_month - 1) * 2
    selected_period = st.selectbox("表示期間", period_options, index=default_index)

col3, col4 = st.columns(2)
with col3:
    target_cm = st.number_input("基準潮位 (cm)", value=120, step=10, help="これより低い時間を探します")
with col4:
    start_hour, end_hour = st.slider("活動時間 (この時間内のみ抽出)", 0, 24, (7, 23), format="%d時")

st.divider()

# --- データ生成 ---
match = re.match(r"(\d+)月(..)", selected_period)
month_sel = int(match.group(1)) if match else 1
period_type = match.group(2) if match else "前半"

last_day = calendar.monthrange(year_sel, month_sel)[1]
start_d, end_d = (1, 15) if "前半" in period_type else (16, last_day)

calculator = OnishiTideCalculator()
data = calculator.get_period_data(year_sel, month_sel, start_d, end_d)
df = pd.DataFrame(data)

if df.empty:
    st.error("データがありません。")
else:
    # ---------------------------------------------------------
    # グラフ描画
    # ---------------------------------------------------------
    st.subheader(f"潮位グラフ: {selected_period}")

    fig, ax = plt.subplots(figsize=(15, 9)) # 縦幅を広げて文字スペース確保

    # 潮位線 & 基準線
    ax.plot(df['raw_time'], df['Level_cm'], color='#1f77b4', linewidth=1.5, alpha=0.8, label="Tide Level")
    ax.axhline(y=target_cm, color='black', linestyle='--', linewidth=1, label=f"Target ({target_cm}cm)")

    # 塗りつぶし
    hours = df['raw_time'].dt.hour
    is_time_ok = (hours >= start_hour) & (hours < end_hour)
    is_level_ok = (df['Level_cm'] <= target_cm)
    
    ax.fill_between(df['raw_time'], df['Level_cm'], target_cm, 
                    where=(is_level_ok & is_time_ok), 
                    color='red', alpha=0.3, interpolate=True)

    # ラベル表示ロジック
    df['in_target'] = is_level_ok & is_time_ok
    df['change'] = df['in_target'].ne(df['in_target'].shift()).cumsum()
    groups = df[df['in_target']].groupby('change')
    
    label_offset_counter = 0

    for _, group in groups:
        start_t = group['raw_time'].iloc[0]
        end_t = group['raw_time'].iloc[-1]
        
        duration = end_t - start_t
        total_minutes = int(duration.total_seconds() / 60)
        
        if total_minutes < 10: continue

        # 高さオフセットを「3段階」で大きく回す (30, 70, 110)
        # これにより隣り合う文字が絶対に被らないようにする
        y_offset = 30 + (label_offset_counter % 3) * 40
        label_offset_counter += 1
