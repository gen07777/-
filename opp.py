import streamlit as st
import datetime
import math
import calendar
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import re

# ---------------------------------------------------------
# アプリ設定 (必ず一番最初に書く)
# ---------------------------------------------------------
st.set_page_config(layout="wide")

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
        detailed_data = []
        start_dt = datetime.datetime(year, month, start_day)
        
        last_day_of_month = calendar.monthrange(year, month)[1]
        if end_day > last_day_of_month:
            end_day = last_day_of_month

        end_dt = datetime.datetime(year, month, end_day, 23, 55)

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
# メイン画面構成
# ---------------------------------------------------------
st.title("大西港 潮位")

# --- サイドバー設定エリア ---
with st.sidebar:
    st.header("条件設定")
    
    # 1. 年の選択
    year_sel = st.number_input("対象年", value=datetime.date.today().year)
    
    # 2. 期間選択リスト (1月前半〜12月後半)
    period_options = []
    for m in range(1, 13):
        period_options.append(f"{m}月前半 (1日-15日)")
        period_options.append(f"{m}月後半 (16日-末日)")
    
    current_month = datetime.date.today().month
    default_index = (current_month - 1) * 2
    
    selected_period = st.selectbox(
        "表示する期間を選択",
        period_options,
        index=default_index
    )
    
    st.divider()
    
    # 3. 潮位設定 (初期値を120に変更)
    target_cm = st.number_input("基準潮位 (cm)", value=120, step=10, help="この高さより低い時間を探します")
    
    st.subheader("活動時間フィルタ")
    # 4. 時間設定 (初期値 7:00 - 23:00)
    start_hour, end_hour = st.slider(
        "グラフに色を塗る時間帯:",
        0, 24, (7, 23),
        format="%d時"
    )

# --- データ生成 ---
# 文字列から月と期間を判定
match = re.match(r"(\d+)月(..)", selected_period)
if match:
    month_sel = int(match.group(1))
    period_type = match.group(2)
else:
    month_sel = 1
    period_type = "前半"

last_day = calendar.monthrange(year_sel, month_sel)[1]
if "前半" in period_type:
    start_d, end_d = 1, 15
else:
    start_d, end_d = 16, last_day

calculator = OnishiTideCalculator()
data = calculator.get_period_data(year_sel, month_sel, start_d, end_d)
df = pd.DataFrame(data)

if df.empty:
    st.error("データがありません。日付を確認してください。")
else:
    # ---------------------------------------------------------
    # グラフ描画 (エラー回避のため、グラフ内文字は英語固定)
    # ---------------------------------------------------------
    st.subheader(f"潮位グラフ: {selected_period}")

    fig, ax = plt.subplots(figsize=(15, 8))

    # 1. 潮位線
    ax.plot(df['raw_time'], df['Level_cm'], color='#1f77b4', linewidth=1.5, alpha=0.8, label="Tide Level")

    # 2. 基準線
    ax.axhline(y=target_cm, color='black', linestyle='--', linewidth=1, label=f"Target ({target_cm}cm)")

    # 3. 塗りつぶし
    hours = df['raw_time'].dt.hour
    is_time_ok = (hours >= start_hour) & (hours <= (end_hour if end_hour < 24 else 24))
    is_level_ok = (df['Level_cm'] <= target_cm)
    
    ax.fill_between(df['raw_time'], df['Level_cm'], target_cm, 
                    where=(is_level_ok & is_time_ok), 
                    color='red', alpha=0.3, interpolate=True)

    # 4. 時間ラベルと継続時間
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

        y_offset = 20 + (label_offset_counter % 2) * 25
        label_offset_counter += 1

        # Start Time
        ax.annotate(
            start_t.strftime("%H:%M"), 
            xy=(start_t, target_cm), 
            xytext=(-15, y_offset),
            textcoords='offset points', ha='center', va='bottom', fontsize=9, color='blue',
            arrowprops=dict(arrowstyle='->', color='blue', linewidth=0.5)
        )

        # End Time
        ax.annotate(
            end_t.strftime("%H:%M"), 
            xy=(end_t, target_cm), 
            xytext=(15, y_offset),
            textcoords='offset points', ha='center', va='bottom', fontsize=9, color='blue',
            arrowprops=dict(arrowstyle='->', color='blue', linewidth=0.5)
        )

        # Duration
        hours_dur = total_minutes // 60
        mins_dur = total_minutes % 60
        dur_str = f"{hours_dur}h {mins_dur}m"
        mid_time = start_t + (duration / 2)
        
        ax.text(mid_time, target_cm - 15, dur_str, 
                ha='center', va='top', fontsize=9, fontweight='bold', color='#cc0000')

    # 5. レイアウト設定
    ax.set_ylabel("Level (cm)")
    ax.grid(True, which='both', linestyle='--', alpha=0.3)
    ax.legend(loc='upper right')
    
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d'))
    ax.set_xlim(df['raw_time'].iloc[0], df['raw_time'].iloc[-1])
    
    st.pyplot(fig)

    # 詳細リスト
    with st.expander("詳細データリスト"):
        export_df = df[df['in_target']].copy()
        if not export_df.empty:
            export_df['Date'] = export_df['raw_time'].dt.strftime('%m/%d')
            export_df['Time'] = export_df['raw_time'].dt.strftime('%H:%M')
            st.dataframe(export_df[['Date', 'Time', 'Level_cm']], use_container_width=True)
        else:
            st.write("条件に該当する時間帯はありません。")

