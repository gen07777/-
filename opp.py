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
    period_options = []
    for m in range(1, 13):
        period_options.append(f"{m}月前半 (1日-15日)")
        period_options.append(f"{m}月後半 (16日-末日)")
    
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
try:
    month_str = selected_period.split('月')[0]
    month_sel = int(month_str)
    is_first_half = "前半" in selected_period
except:
    month_sel = 1
    is_first_half = True

last_day = calendar.monthrange(year_sel, month_sel)[1]
if is_first_half:
    start_d, end_d = 1, 15
else:
    start_d, end_d = 16, last_day

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

    # 縦幅を大きく確保
    fig, ax = plt.subplots(figsize=(15, 10))

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

        # 重なり防止用のジグザグ係数 (0 or 1)
        stagger = (label_offset_counter % 2) * 20
        label_offset_counter += 1

        # フォント設定
        font_size = 8
        
        # -------------------------------------------------
        # 1. 開始時間 (Start) -> 青色 / 上に表示
        # -------------------------------------------------
        # 基準線より「上」に配置 + ジグザグ補正
        y_pos_start = target_cm + 15 + stagger
        
        ax.annotate(
            start_t.strftime("%H:%M"), 
            xy=(start_t, target_cm),
            xytext=(0, y_pos_start - target_cm),
            textcoords='offset points', 
            ha='center', va='bottom', 
            fontsize=font_size, color='blue', fontweight='bold',
            arrowprops=dict(arrowstyle='-', color='blue', linewidth=0.5, linestyle=':')
        )

        # -------------------------------------------------
        # 2. 終了時間 (End) -> 緑色 / 下に表示
        # -------------------------------------------------
        # 基準線より「下」に配置 + ジグザグ補正
        y_pos_end = target_cm - 15 - stagger
        
        ax.annotate(
            end_t.strftime("%H:%M"), 
            xy=(end_t, target_cm), 
            xytext=(0, y_pos_end - target_cm), 
            textcoords='offset points', 
            ha='center', va='top', 
            fontsize=font_size, color='green', fontweight='bold',
            arrowprops=dict(arrowstyle='-', color='green', linewidth=0.5, linestyle=':')
        )

        # -------------------------------------------------
        # 3. 継続時間 (Duration) -> 赤色 / さらに下に表示
        # -------------------------------------------------
        hours_dur = total_minutes // 60
        mins_dur = total_minutes % 60
        dur_str = f"{hours_dur}h{mins_dur}m"
        
        mid_time = start_t + (duration / 2)
        
        # 終了時間よりさらに下に配置 (緑文字と被らないように)
        y_pos_dur = y_pos_end - 15 

        # ax.text で配置 (シンプル化)
        ax.text(
            mid_time, y_pos_dur, dur_str, 
            ha='center', va='top', 
            fontsize=font_size, fontweight='bold', color='#cc0000',
            bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.6)
        )

    # レイアウト
    ax.set_ylabel("Level (cm)")
    ax.grid(True, which='both', linestyle='--', alpha=0.3)
    ax.legend(loc='upper right')
    
    # 日付表示
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d'))
    ax.set_xlim(df['raw_time'].iloc[0], df['raw_time'].iloc[-1])
    
    st.pyplot(fig)
