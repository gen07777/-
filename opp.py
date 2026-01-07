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
# 計算ロジック (標準港: 広島 + ユーザー調整機能)
# ---------------------------------------------------------
class OnishiTideCalculator:
    def __init__(self):
        # 広島港(宇品)の標準調和定数
        self.CONSTITUENTS = {
            'M2': {'amp': 132.0, 'phase': 206.5, 'speed': 28.9841042},
            'S2': {'amp': 48.0,  'phase': 242.6, 'speed': 30.0000000},
            'K1': {'amp': 37.0,  'phase': 191.0, 'speed': 15.0410686},
            'O1': {'amp': 30.0,  'phase': 172.6, 'speed': 13.9430356}
        }
        # 平均水面 (MSL): 240cm (広島標準)
        self.MSL = 240.0 
        
        # ユーザー補正値
        self.user_time_offset = 0
        self.user_height_offset = 0

    def set_user_offsets(self, time_offset_mins, height_offset_cm):
        self.user_time_offset = time_offset_mins
        self.user_height_offset = height_offset_cm

    def _calculate_astronomical_tide(self, target_datetime):
        base_date = datetime.datetime(target_datetime.year, 1, 1)
        delta_hours = (target_datetime - base_date).total_seconds() / 3600.0
        tide_height = self.MSL
        for name, const in self.CONSTITUENTS.items():
            theta = math.radians(const['speed'] * delta_hours - const['phase'])
            tide_height += const['amp'] * math.cos(theta)
        return tide_height

    def get_tide_level(self, dt):
        """指定日時の潮位計算"""
        # 時間ズレ補正
        calc_dt = dt - datetime.timedelta(minutes=self.user_time_offset)
        base_level = self._calculate_astronomical_tide(calc_dt)
        # 高さズレ補正
        return base_level + self.user_height_offset

    def get_period_data(self, year, month, start_day, end_day, interval_minutes=5):
        detailed_data = []
        start_dt = datetime.datetime(year, month, start_day)
        last_day_of_month = calendar.monthrange(year, month)[1]
        if end_day > last_day_of_month: end_day = last_day_of_month
        end_dt = datetime.datetime(year, month, end_day, 23, 55)

        current_dt = start_dt
        while current_dt <= end_dt:
            level = self.get_tide_level(current_dt)
            detailed_data.append({
                "raw_time": current_dt, 
                "Level_cm": level
            })
            current_dt += datetime.timedelta(minutes=interval_minutes)
        return detailed_data

# ---------------------------------------------------------
# メイン画面構成
# ---------------------------------------------------------
st.title("大西港 潮位ビジュアライザー (調整モード)")

# 現在時刻 (JST)
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
now_jst = now_jst.replace(tzinfo=None, second=0, microsecond=0)

st.markdown(f"**現在時刻 (JST):** `{now_jst.strftime('%Y/%m/%d %H:%M')}`")

# --- 設定エリア ---
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    st.markdown("##### 1. 期間設定")
    year_sel = st.number_input("年", value=now_jst.year)
    period_options = [f"{m}月前半" for m in range(1, 13)] + [f"{m}月後半" for m in range(1, 13)]
    # リストの並び順を月順に整理
    period_options = sorted(period_options, key=lambda x: int(x.split('月')[0]) + (0.5 if '後半' in x else 0))
    
    current_idx = (now_jst.month - 1) * 2
    if now_jst.day > 15: current_idx += 1
    selected_period = st.selectbox("期間", period_options, index=current_idx)

with col2:
    st.markdown("##### 2. ターゲット設定")
    target_cm = st.number_input("基準潮位(cm)", value=130, step=10)
    start_hour, end_hour = st.slider("活動時間", 0, 24, (7, 23), format="%d時")

with col3:
    st.markdown("##### 3. ズレ補正")
    # 初期値を110に変更
    offset_time = st.number_input("時間のズレ (分)", value=110, step=10)
    offset_height = st.number_input("高さのズレ (cm)", value=0, step=10)

st.divider()

# --- データ生成 ---
try:
    month_match = re.match(r"(\d+)月", selected_period)
    month_sel = int(month_match.group(1))
    is_first_half = "前半" in selected_period
except:
    month_sel = now_jst.month
    is_first_half = True

last_day = calendar.monthrange(year_sel, month_sel)[1]
if is_first_half:
    start_d, end_d = 1, 15
else:
    start_d, end_d = 16, last_day

calculator = OnishiTideCalculator()
calculator.set_user_offsets(offset_time, offset_height)
data = calculator.get_period_data(year_sel, month_sel, start_d, end_d)
df = pd.DataFrame(data)
current_tide_level = calculator.get_tide_level(now_jst)

if df.empty:
    st.error("データがありません。")
else:
    # ---------------------------------------------------------
    # グラフ描画
    # ---------------------------------------------------------
    st.subheader(f"{selected_period}の潮位")
    
    if offset_time != 0 or offset_height != 0:
        st.info(f"🔧 補正中: 時間 **{offset_time:+d}分**, 高さ **{offset_height:+d}cm**")

    fig, ax = plt.subplots(figsize=(15, 10))

    # メイン線
    ax.plot(df['raw_time'], df['Level_cm'], color='#1f77b4', linewidth=1.5, alpha=0.9, label="Tide Level")
    ax.axhline(y=target_cm, color='black', linestyle='--', linewidth=1, label=f"Target ({target_cm}cm)")

    # 塗りつぶし
    hours = df['raw_time'].dt.hour
    is_time_ok = (hours >= start_hour) & (hours < end_hour)
    is_level_ok = (df['Level_cm'] <= target_cm)
    ax.fill_between(df['raw_time'], df['Level_cm'], target_cm, 
                    where=(is_level_ok & is_time_ok), 
                    color='red', alpha=0.3, interpolate=True)

    # -----------------------------------------------------
    # ★満潮・干潮の検出と表示 (New)
    # -----------------------------------------------------
    levels = df['Level_cm'].values
    times = df['raw_time'].tolist()
    
    # ピーク検出 (単純な前後比較)
    for i in range(1, len(levels) - 1):
        # 満潮 (High Tide)
        if levels[i-1] < levels[i] and levels[i] > levels[i+1]:
            # ピークの上に表示
            ax.scatter(times[i], levels[i], color='red', s=30, zorder=5, marker='^')
            ax.annotate(f"{times[i].strftime('%H:%M')}\n{levels[i]:.0f}cm",
                        xy=(times[i], levels[i]), xytext=(0, 10),
                        textcoords='offset points', ha='center', va='bottom',
                        fontsize=8, color='#880000')

        # 干潮 (Low Tide)
        elif levels[i-1] > levels[i] and levels[i] < levels[i+1]:
            # ピークの下に表示 (これによりターゲットライン付近の文字と被らない)
            ax.scatter(times[i], levels[i], color='blue', s=30, zorder=5, marker='v')
            ax.annotate(f"{times[i].strftime('%H:%M')}\n{levels[i]:.0f}cm",
                        xy=(times[i], levels[i]), xytext=(0, -25),
                        textcoords='offset points', ha='center', va='top',
                        fontsize=8, color='#000088')

    # -----------------------------------------------------
    # 現在時刻 (黄色点)
    # -----------------------------------------------------
    graph_start = df['raw_time'].iloc[0]
    graph_end = df['raw_time'].iloc[-1]
    
    if graph_start <= now_jst <= graph_end:
        ax.scatter(now_jst, current_tide_level, color='yellow', s=180, zorder=10, edgecolors='black', linewidth=1.5)
        ax.annotate(f"Now\n{now_jst.strftime('%H:%M')}\n{current_tide_level:.0f}cm", 
                    xy=(now_jst, current_tide_level), xytext=(0, 45),
                    textcoords='offset points', ha='center', va='bottom',
                    fontsize=10, fontweight='bold', color='black',
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", alpha=0.9),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0', color='black'))

    # -----------------------------------------------------
    # ターゲットエリア情報 (Start/End/Duration)
    # -----------------------------------------------------
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

        stagger = (label_offset_counter % 2) * 20
        label_offset_counter += 1
        font_size = 8
        
        # Start (青/上) - 基準線付近
        y_pos_start = target_cm + 15 + stagger
        ax.annotate(start_t.strftime("%H:%M"), 
                    xy=(start_t, target_cm), xytext=(0, y_pos_start - target_cm),
                    textcoords='offset points', ha='center', va='bottom', 
                    fontsize=font_size, color='blue', fontweight='bold',
                    arrowprops=dict(arrowstyle='-', color='blue', linewidth=0.5, linestyle=':'))

        # End (緑/下) - 基準線付近
        y_pos_end = target_cm - 15 - stagger
        ax.annotate(end_t.strftime("%H:%M"), 
                    xy=(end_t, target_cm), xytext=(0, y_pos_end - target_cm), 
                    textcoords='offset points', ha='center', va='top', 
                    fontsize=font_size, color='green', fontweight='bold',
                    arrowprops=dict(arrowstyle='-', color='green', linewidth=0.5, linestyle=':'))

        # Duration (赤/さらに下) - 基準線より下
        # ※干潮ラベルはもっと下(谷底)に出るので被りにくい
        hours_dur = total_minutes // 60
        mins_dur = total_minutes % 60
        dur_str = f"{hours_dur}h{mins_dur}m"
        mid_time = start_t + (duration / 2)
        y_pos_dur = y_pos_end - 30 
        
        ax.text(mid_time, y_pos_dur, dur_str, 
                ha='center', va='top', 
                fontsize=font_size, fontweight='bold', color='#cc0000',
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.6))

    ax.set_ylabel("Level (cm)")
    ax.grid(True, which='both', linestyle='--', alpha=0.3)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d'))
    ax.set_xlim(df['raw_time'].iloc[0], df['raw_time'].iloc[-1])
    
    st.pyplot(fig)
