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
st.set_page_config(layout="wide", page_title="大西港 潮汐計算機 (標準リセット版)")

# ---------------------------------------------------------
# 物理計算ロジック
# ---------------------------------------------------------
class HarmonicTideModel:
    def __init__(self):
        self.SPEEDS = {
            'M2': 28.9841042, 'S2': 30.0000000,
            'K1': 15.0410686, 'O1': 13.9430356
        }
        self.base_consts = {
            'M2': {'amp': 130.0, 'phase': 200.0},
            'S2': {'amp': 50.0,  'phase': 230.0},
            'K1': {'amp': 38.0,  'phase': 190.0},
            'O1': {'amp': 32.0,  'phase': 170.0}
        }
        self.msl = 240.0 
        self.phase_offset = 0

    def calibrate(self, kure_high_time, kure_high_level, manual_offset_minutes):
        # ユーザー指定のズレを適用
        target_onishi_time = kure_high_time + datetime.timedelta(minutes=manual_offset_minutes)
        
        search_start = target_onishi_time - datetime.timedelta(hours=3)
        search_end = target_onishi_time + datetime.timedelta(hours=3)
        best_time = search_start
        max_level = -9999
        dt = search_start
        
        while dt <= search_end:
            lvl = self._calc_raw(dt)
            if lvl > max_level:
                max_level = lvl
                best_time = dt
            dt += datetime.timedelta(minutes=1)
        
        # 位相補正
        time_diff_minutes = (target_onishi_time - best_time).total_seconds() / 60.0
        self.phase_offset = time_diff_minutes * 0.48
        
        # 高さ補正 (潮位比は簡易的に1.0とするが、MSLで調整)
        height_diff = kure_high_level - max_level
        self.msl += height_diff
        
        return target_onishi_time

    def _calc_raw(self, target_dt):
        base_dt = datetime.datetime(target_dt.year, 1, 1)
        delta_hours = (target_dt - base_dt).total_seconds() / 3600.0
        level = self.msl
        for name, speed in self.SPEEDS.items():
            const = self.base_consts[name]
            phase = const['phase'] - self.phase_offset
            theta = math.radians(speed * delta_hours - phase)
            level += const['amp'] * math.cos(theta)
        return level

    def calculate_level(self, target_dt):
        return self._calc_raw(target_dt)

    def get_period_data(self, year, month, start_day, end_day, interval_minutes=10):
        detailed_data = []
        try:
            start_dt = datetime.datetime(year, month, start_day)
            last_day_of_month = calendar.monthrange(year, month)[1]
            if end_day > last_day_of_month: end_day = last_day_of_month
            end_dt = datetime.datetime(year, month, end_day, 23, 55)
        except:
            return []

        current_dt = start_dt
        while current_dt <= end_dt:
            level = self.calculate_level(current_dt)
            detailed_data.append({"raw_time": current_dt, "Level_cm": level})
            current_dt += datetime.timedelta(minutes=interval_minutes)
        return detailed_data

# ---------------------------------------------------------
# メイン画面
# ---------------------------------------------------------
st.title("⚓ 大西港 潮汐モニター")
st.markdown("現在は**「標準（呉と同じ）」**設定です。これで「上げ潮」と表示されるはずです。")

# 現在時刻
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
now_jst = now_jst.replace(tzinfo=None, second=0, microsecond=0)

# --- サイドバー ---
with st.sidebar:
    st.header("⚙️ 設定・補正")
    
    # 日付・時刻入力 (画像の値をデフォルトに)
    cal_date = st.date_input("日付", value=now_jst.date())
    kure_time = st.time_input("満潮時刻 (表の値)", value=datetime.time(12, 39))
    kure_level = st.number_input("潮位 (表の値 cm)", value=342, step=10)
    
    st.markdown("---")
    st.subheader("⏱️ ズレ補正")
    # デフォルトを 0 (補正なし) に戻しました
    offset_min = st.slider("時間のズレ (分)", -60, 60, 0, step=5, 
                           help="0なら呉と同じ。+にすると遅れる、-にすると早まる")
    
    st.info(f"大西港 満潮予測: **{(datetime.datetime.combine(cal_date, kure_time) + datetime.timedelta(minutes=offset_min)).strftime('%H:%M')}**")

# --- メインエリア ---
col1, col2 = st.columns(2)
with col1:
    year_sel = st.number_input("年", value=now_jst.year)
    period_options = [f"{m}月前半" for m in range(1, 13)] + [f"{m}月後半" for m in range(1, 13)]
    current_idx = (now_jst.month - 1) * 2
    if now_jst.day > 15: current_idx += 1
    selected_period = st.selectbox("表示期間", period_options, index=current_idx)

with col2:
    target_cm = st.number_input("基準潮位(cm)", value=150, step=10)
    start_hour, end_hour = st.slider("活動時間帯", 0, 24, (6, 19), format="%d時")

# --- 計算 ---
model = HarmonicTideModel()
target_dt = datetime.datetime.combine(cal_date, kure_time)
model.calibrate(target_dt, kure_level, offset_min)

# データ生成
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

data = model.get_period_data(year_sel, month_sel, start_d, end_d)
df = pd.DataFrame(data)
current_level = model.calculate_level(now_jst)

# --- 状態判定 ---
# 5分前と比較して増減を判定
prev_level = model.calculate_level(now_jst - datetime.timedelta(minutes=5))
if current_level > prev_level + 0.5:
    status_text = "上げ潮 ↗ (満ちています)"
    status_color = "red" # 満ち潮は赤系で表現
elif current_level < prev_level - 0.5:
    status_text = "下げ潮 ↘ (引いています)"
    status_color = "blue"
else:
    status_text = "潮止まり (満潮/干潮ピーク)"
    status_color = "green"

# --- グラフ描画 ---
if not df.empty:
    st.subheader(f"現在の状態: :{status_color}[{status_text}]")
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # 線グラフ
    ax.plot(df['raw_time'], df['Level_cm'], color='#1f77b4', linewidth=2, label="潮位")
    ax.axhline(y=target_cm, color='orange', linestyle='--', label=f"基準 {target_cm}cm")
    
    # 塗りつぶし
    hours = df['raw_time'].dt.hour
    is_time_ok = (hours >= start_hour) & (hours < end_hour)
    is_level_ok = (df['Level_cm'] <= target_cm)
    ax.fill_between(df['raw_time'], df['Level_cm'], target_cm, 
                    where=(is_level_ok & is_time_ok), color='orange', alpha=0.3)
    
    # 現在地プロット
    if df['raw_time'].iloc[0] <= now_jst <= df['raw_time'].iloc[-1]:
        ax.scatter(now_jst, current_level, color='gold', s=200, zorder=10, edgecolors='black')
        ax.annotate(f"現在\n{now_jst.strftime('%H:%M')}\n{current_level:.0f}cm", 
                    xy=(now_jst, current_level), xytext=(0, 40),
                    textcoords='offset points', ha='center', va='bottom',
                    fontsize=12, fontweight='bold',
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gold"))

    # ピーク時刻表示
    levels = df['Level_cm'].values
    times = df['raw_time'].tolist()
    for i in range(1, len(levels)-1):
        if levels[i-1] < levels[i] > levels[i+1]: # 満潮
            ax.scatter(times[i], levels[i], color='red', marker='^', s=50, zorder=5)
            ax.text(times[i], levels[i]+5, f"{times[i].strftime('%H:%M')}\n{levels[i]:.0f}", 
                    ha='center', va='bottom', fontsize=8, color='darkred')
        elif levels[i-1] > levels[i] < levels[i+1]: # 干潮
            ax.scatter(times[i], levels[i], color='blue', marker='v', s=50, zorder=5)
            ax.text(times[i], levels[i]-25, f"{times[i].strftime('%H:%M')}\n{levels[i]:.0f}", 
                    ha='center', va='top', fontsize=8, color='darkblue')

    ax.grid(True, linestyle=':', alpha=0.6)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d(%a) %H時'))
    st.pyplot(fig)
    
    with st.expander("データリスト"):
        st.dataframe(df)
