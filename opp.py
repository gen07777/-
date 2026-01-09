import streamlit as st
import datetime
import math
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager
import requests

# ---------------------------------------------------------
# アプリ設定
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="Onishi Port Tide Master Ultimate")

# API Key
OWM_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"

# ---------------------------------------------------------
# フォント設定
# ---------------------------------------------------------
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
# OpenWeatherMap API (1時間キャッシュ)
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def get_cached_pressure():
    lat = 34.234
    lon = 132.831
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OWM_API_KEY}&units=metric"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return float(data['main']['pressure'])
        return None
    except:
        return None

# ---------------------------------------------------------
# 月齢・潮名
# ---------------------------------------------------------
def get_moon_age(date_obj):
    base_date = datetime.date(2000, 1, 6)
    diff = (date_obj - base_date).days
    return diff % 29.53059

def get_tide_name(moon_age):
    m = int(moon_age)
    if m >= 30: m -= 30
    if 0 <= m <= 2 or 14 <= m <= 17 or 29 <= m <= 30: return "Spring Tide (大潮)"
    elif 3 <= m <= 5 or 18 <= m <= 20: return "Middle Tide (中潮)"
    elif 6 <= m <= 9 or 21 <= m <= 24: return "Neap Tide (小潮)"
    elif 10 <= m <= 12: return "Long Tide (長潮)"
    elif m == 13 or 25 <= m <= 28: return "Young Tide (若潮)"
    else: return "Middle Tide (中潮)"

# ---------------------------------------------------------
# 潮汐モデル
# ---------------------------------------------------------
class OnishiEnvironmentModel:
    def __init__(self, pressure_hpa=1013.0):
        self.epoch_time = datetime.datetime(2026, 1, 7, 12, 39)
        self.epoch_level = 342.0
        self.msl = 180.0
        self.pressure_correction = (1013.0 - pressure_hpa) * 1.0
        self.consts = [
            {'name': 'M2', 'speed': 28.984104, 'factor': 1.00},
            {'name': 'S2', 'speed': 30.000000, 'factor': 0.45},
            {'name': 'N2', 'speed': 28.439730, 'factor': 0.22},
            {'name': 'K2', 'speed': 30.082137, 'factor': 0.12},
            {'name': 'K1', 'speed': 15.041069, 'factor': 0.38},
            {'name': 'O1', 'speed': 13.943036, 'factor': 0.28},
            {'name': 'P1', 'speed': 14.958931, 'factor': 0.12},
            {'name': 'Q1', 'speed': 13.398661, 'factor': 0.05},
            {'name': 'M4', 'speed': 57.968208, 'factor': 0.08},
            {'name': 'MS4','speed': 58.984104, 'factor': 0.06}
        ]
        total_factor = sum(c['factor'] for c in self.consts)
        self.base_amp = (self.epoch_level - self.msl) / total_factor

    def _calc_raw(self, target_dt):
        delta_hours = (target_dt - self.epoch_time).total_seconds() / 3600.0
        level = self.msl + self.pressure_correction
        for c in self.consts:
            theta_rad = math.radians(c['speed'] * delta_hours)
            shift = math.radians(90) if c['name'] in ['M4', 'MS4'] else 0
            level += (self.base_amp * c['factor']) * math.cos(theta_rad - shift)
        return level

    def get_dataframe(self, start_date, days=10):
        # 1分刻みで計算
        start_dt = datetime.datetime.combine(start_date, datetime.time(0, 0))
        end_dt = start_dt + datetime.timedelta(days=days) - datetime.timedelta(minutes=1)
        # 高速化のためPandasの日付範囲生成を使用
        time_index = pd.date_range(start=start_dt, end=end_dt, freq='1min')
        
        # ベクトル計算風に処理（実際はループだが構造を整理）
        data = []
        for curr in time_index:
            data.append({"time": curr, "level": self._calc_raw(curr)})
        return pd.DataFrame(data)

    def get_current_level(self):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_jst = now_utc + datetime.timedelta(hours=9)
        now_naive = now_jst.replace(tzinfo=None)
        return now_naive, self._calc_raw(now_naive)

# ---------------------------------------------------------
# UI構築
# ---------------------------------------------------------
st.markdown("<h4 style='text-align: left; margin-bottom: 5px;'>⚓ Onishi Port Tide Master</h4>", unsafe_allow_html=True)
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

# 気圧取得
fetched_pressure = get_cached_pressure()
current_pressure = fetched_pressure if fetched_pressure else 1013.0
status_text = "Auto Update" if fetched_pressure else "Standard (No Data)"

# 計算実行
model = OnishiEnvironmentModel(pressure_hpa=current_pressure)
curr_time, curr_lvl = model.get_current_level()

# 月齢
current_view_date = st.session_state['view_date']
moon_age = get_moon_age(current_view_date)
tide_name = get_tide_name(moon_age)

# 情報パネル
pressure_diff = int(1013 - current_pressure)
corr_str = f"+{pressure_diff}" if pressure_diff > 0 else f"{pressure_diff}"
if pressure_diff == 0: corr_str = "±0"

info_html = f"""
<div style="font-size: 0.9rem; margin-bottom: 5px; color: #444; background-color: #f8f9fa; padding: 10px; border-radius: 5px; border: 1px solid #ddd;">
  <div style="margin-bottom: 4px;">
    <b>Date:</b> {current_view_date.strftime('%Y/%m/%d')} 
    <span style="margin-left:8px; color:#555;">Moon: {moon_age:.1f} ({tide_name})</span>
  </div>
  <div style="font-size: 1.0rem;">
    <span style="color: #0066cc;"><b>Current:</b> {curr_time.strftime('%H:%M')} | <b>Level:</b> {int(curr_lvl)}cm</span>
    <span style="font-size: 0.85rem; color: #666; margin-left: 8px;">
      (Pressure: {int(current_pressure)}hPa <span style="color:#d62728;">Adj {corr_str}cm</span>)
    </span>
  </div>
</div>
"""
st.markdown(info_html, unsafe_allow_html=True)

# ナビゲーション
days_to_show = 10
col_prev, col_next = st.columns(2)
with col_prev:
    if st.button("<< Prev 10d", use_container_width=True):
        st.session_state['view_date'] -= datetime.timedelta(days=days_to_show)
with col_next:
    if st.button("Next 10d >>", use_container_width=True):
        st.session_state['view_date'] += datetime.timedelta(days=days_to_show)

# サイドバー
with st.sidebar:
    st.header("⚙️ Settings")
    st.info(f"📡 Weather: {status_text}\n{current_pressure} hPa")
    st.markdown("---")
    target_cm = st.number_input("Work Limit Level (cm)", value=120, step=10)
    start_h, end_h = st.slider("Workable Hours", 0, 24, (7, 23), format="%d:00")
    st.markdown("---")
    if st.button("Back to Today"):
        st.session_state['view_date'] = now_jst.date()

# データ生成
df = model.get_dataframe(st.session_state['view_date'], days=days_to_show)

# ---------------------------------------------------------
# 解析 & ピーク検出 (修正版)
# ---------------------------------------------------------
df['hour'] = df['time'].dt.hour
df['is_safe'] = (df['level'] <= target_cm) & (df['hour'] >= start_h) & (df['hour'] < end_h)

# 作業時間リスト作成
safe_windows = []
if df['is_safe'].any():
    df['group'] = (df['is_safe'] != df['is_safe'].shift()).cumsum()
    for _, grp in df[df['is_safe']].groupby('group'):
        start_t = grp['time'].iloc[0]
        end_t = grp['time'].iloc[-1]
        
        if (end_t - start_t).total_seconds() >= 600:
            min_lvl = grp['level'].min()
            min_time = grp.loc[grp['level'].idxmin(), 'time']
            duration = end_t - start_t
            h = duration.seconds // 3600
            m = (duration.seconds % 3600) // 60
            
            safe_windows.append({
                "date_str": start_t.strftime('%m/%d (%a)'),
                "start": start_t.strftime("%H:%M"),
                "end": end_t.strftime("%H:%M"),
                "duration": f"{h}:{m:02}",
                "graph_label": f"Work\n{h}:{m:02}",
                "min_time": min_time,
                "min_level": min_lvl
            })

# ピーク検出 (Pandasの機能を使って正確に検出)
# 前後60分(60データ)の中で最大/最小であるものを抽出
window_size = 60
df['is_high'] = df.iloc[window_size:-window_size]['level'].copy()
# ローカル最大値を見つける（シフトさせて比較）
df['max_roll'] = df['level'].rolling(window=120, center=True).max()
df['min_roll'] = df['level'].rolling(window=120, center=True).min()

# 満潮抽出 (ノイズ除去のためMSLより上)
high_tides = df[(df['level'] == df['max_roll']) & (df['level'] > 180)].copy()
# 重複除去（念のため、近い時間は間引く）
high_tides['time_diff'] = high_tides['time'].diff().dt.total_seconds().fillna(9999)
high_tides = high_tides[high_tides['time_diff'] > 3600]

# 干潮抽出 (MSLより下)
low_tides = df[(df['level'] == df['min_roll']) & (df['level'] < 180)].copy()
low_tides['time_diff'] = low_tides['time'].diff().dt.total_seconds().fillna(9999)
low_tides = low_tides[low_tides['time_diff'] > 3600]

# ---------------------------------------------------------
# グラフ描画
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5))

# 線と基準
ax.plot(df['time'], df['level'], color='#0066cc', linewidth=2, label="Level", zorder=2)
ax.axhline(y=target_cm, color='orange', linestyle='--', linewidth=2, label=f"Limit {target_cm}cm", zorder=1)
ax.fill_between(df['time'], df['level'], target_cm, where=df['is_safe'], color='#ffcc00', alpha=0.4, label="Workable")

# 1. 現在位置
graph_start = df['time'].iloc[0]
graph_end = df['time'].iloc[-1]
if graph_start <= curr_time <= graph_end:
    ax.scatter(curr_time, curr_lvl, color='gold', edgecolors='black', s=90, zorder=10)

# 2. 満潮プロット
for _, row in high_tides.iterrows():
    t, l = row['time'], row['level']
    ax.scatter(t, l, color='red', marker='^', s=40, zorder=3)
    off_y = 15 if (t.day % 2 == 0) else 35
    ax.annotate(f"{t.strftime('%H:%M')}\n{int(l)}", (t, l), xytext=(0, off_y), 
                textcoords='offset points', ha='center', fontsize=9, color='#cc0000', fontweight='bold')

# 3. 干潮プロット
for _, row in low_tides.iterrows():
    t, l = row['time'], row['level']
    ax.scatter(t, l, color='blue', marker='v', s=40, zorder=3)
    off_y = -25 if (t.day % 2 == 0) else -45
    ax.annotate(f"{t.strftime('%H:%M')}\n{int(l)}", (t, l), xytext=(0, off_y), 
                textcoords='offset points', ha='center', fontsize=9, color='#0000cc', fontweight='bold')

# 4. Workラベル
for win in safe_windows:
    x = win['min_time']
    y = win['min_level']
    # 干潮ラベルと被らないよう更に下へ
    ax.annotate(win['graph_label'], (x, y), xytext=(0, -85), 
                textcoords='offset points', ha='center', fontsize=9, 
                color='#b8860b', fontweight='bold',
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.7))

# 軸設定
ax.set_ylabel("Level (cm)")
ax.grid(True, linestyle=':', alpha=0.6)
ax.xaxis.set_major_locator(mdates.DayLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n(%a)'))
ax.set_ylim(bottom=-110)

plt.tight_layout()
st.pyplot(fig)

# ---------------------------------------------------------
# 作業可能時間リスト (コンパクト)
# ---------------------------------------------------------
st.markdown(f"##### 📋 Workable Time List (Level <= {target_cm}cm)")

if not safe_windows:
    st.warning("No workable time found.")
else:
    res_df = pd.DataFrame(safe_windows)
    display_df = res_df[['date_str', 'start', 'end', 'duration']]
    st.dataframe(
        display_df,
        use_container_width=False, 
        hide_index=True,
        column_config={
            "date_str": st.column_config.TextColumn("Date", width="small"),
            "start": st.column_config.TextColumn("Start", width="small"),
            "end": st.column_config.TextColumn("End", width="small"),
            "duration": st.column_config.TextColumn("Time", width="small"),
        }
    )
