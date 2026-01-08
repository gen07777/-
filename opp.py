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

# ユーザー様のAPIキー (OpenWeatherMap)
OWM_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"

# ---------------------------------------------------------
# フォント設定
# ---------------------------------------------------------
def configure_font():
    plt.rcParams['font.family'] = 'sans-serif'

configure_font()

# ---------------------------------------------------------
# セッション状態管理
# ---------------------------------------------------------
if 'view_date' not in st.session_state:
    now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    st.session_state['view_date'] = now_jst.date()

# ---------------------------------------------------------
# OpenWeatherMap API連携 (通信制限付き・1時間キャッシュ)
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
        else:
            return None
    except:
        return None

# ---------------------------------------------------------
# 月齢・潮名計算
# ---------------------------------------------------------
def get_moon_age(date_obj):
    base_date = datetime.date(2000, 1, 6)
    diff = (date_obj - base_date).days
    return diff % 29.53059

def get_tide_name(moon_age):
    m = int(moon_age)
    if m >= 30: m -= 30
    
    if 0 <= m <= 2 or 14 <= m <= 17 or 29 <= m <= 30:
        return "Spring Tide (大潮)"
    elif 3 <= m <= 5 or 18 <= m <= 20:
        return "Middle Tide (中潮)"
    elif 6 <= m <= 9 or 21 <= m <= 24:
        return "Neap Tide (小潮)"
    elif 10 <= m <= 12:
        return "Long Tide (長潮)"
    elif m == 13 or 25 <= m <= 28:
        return "Young Tide (若潮)"
    else:
        return "Middle Tide (中潮)"

# ---------------------------------------------------------
# 潮汐計算モデル (大西港カスタム・気圧連動)
# ---------------------------------------------------------
class OnishiEnvironmentModel:
    def __init__(self, pressure_hpa=1013.0):
        self.epoch_time = datetime.datetime(2026, 1, 7, 12, 39)
        self.epoch_level = 342.0
        self.msl = 180.0
        
        # 気圧補正
        self.pressure_correction = (1013.0 - pressure_hpa) * 1.0

        # 分潮データ (地形補正含む)
        self.consts = [
            {'name': 'M2',  'speed': 28.984104, 'factor': 1.00},
            {'name': 'S2',  'speed': 30.000000, 'factor': 0.45},
            {'name': 'N2',  'speed': 28.439730, 'factor': 0.22},
            {'name': 'K2',  'speed': 30.082137, 'factor': 0.12},
            {'name': 'K1',  'speed': 15.041069, 'factor': 0.38},
            {'name': 'O1',  'speed': 13.943036, 'factor': 0.28},
            {'name': 'P1',  'speed': 14.958931, 'factor': 0.12},
            {'name': 'Q1',  'speed': 13.398661, 'factor': 0.05},
            {'name': 'M4',  'speed': 57.968208, 'factor': 0.08},
            {'name': 'MS4', 'speed': 58.984104, 'factor': 0.06}
        ]
        
        total_factor = sum(c['factor'] for c in self.consts)
        actual_amp = self.epoch_level - self.msl
        self.base_amp = actual_amp / total_factor

    def _calc_raw(self, target_dt):
        delta_hours = (target_dt - self.epoch_time).total_seconds() / 3600.0
        level = self.msl + self.pressure_correction
        for c in self.consts:
            theta_rad = math.radians(c['speed'] * delta_hours)
            phase_shift = 0
            if c['name'] in ['M4', 'MS4']:
                phase_shift = math.radians(90)
            level += (self.base_amp * c['factor']) * math.cos(theta_rad - phase_shift)
        return level

    def get_dataframe(self, start_date, days=10, interval_min=1): # ★ここを1分に変更
        start_dt = datetime.datetime.combine(start_date, datetime.time(0, 0))
        end_dt = start_dt + datetime.timedelta(days=days) - datetime.timedelta(minutes=1)
        data = []
        curr = start_dt
        while curr <= end_dt:
            lvl = self._calc_raw(curr)
            data.append({"time": curr, "level": lvl})
            curr += datetime.timedelta(minutes=interval_min)
        return pd.DataFrame(data)

    def get_current_level(self):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_jst = now_utc + datetime.timedelta(hours=9)
        now_naive = now_jst.replace(tzinfo=None)
        return now_naive, self._calc_raw(now_naive)

# ---------------------------------------------------------
# メイン画面 UI
# ---------------------------------------------------------
st.markdown("<h4 style='text-align: left; margin-bottom: 5px;'>⚓ Onishi Port Tide Master</h4>", unsafe_allow_html=True)
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

# --- 気圧自動取得 ---
fetched_pressure = get_cached_pressure()
current_pressure = fetched_pressure if fetched_pressure else 1013.0
pressure_status_text = "Auto Update" if fetched_pressure else "Standard (No Data)"

# --- 計算実行 ---
model = OnishiEnvironmentModel(pressure_hpa=current_pressure)
curr_time, curr_lvl = model.get_current_level()

# 月齢・潮名
current_view_date = st.session_state['view_date']
moon_age = get_moon_age(current_view_date)
tide_name = get_tide_name(moon_age)

# --- 情報表示 ---
pressure_diff = int(1013 - current_pressure)
correction_str = f"+{pressure_diff}" if pressure_diff > 0 else f"{pressure_diff}"
if pressure_diff == 0: correction_str = "±0"

info_html = f"""
<div style="font-size: 0.9rem; margin-bottom: 5px; color: #444; background-color: #f8f9fa; padding: 10px; border-radius: 5px; border: 1px solid #ddd;">
  <div style="margin-bottom: 4px;">
    <b>Date:</b> {current_view_date.strftime('%Y/%m/%d')} 
    <span style="margin-left:8px; color:#555;">Moon: {moon_age:.1f} ({tide_name})</span>
  </div>
  <div style="font-size: 1.0rem;">
    <span style="color: #0066cc;"><b>Current:</b> {curr_time.strftime('%H:%M')} | <b>Level:</b> {int(curr_lvl)}cm</span>
    <span style="font-size: 0.85rem; color: #666; margin-left: 8px;">
      (Pressure: {int(current_pressure)}hPa <span style="color:#d62728;">Adj {correction_str}cm</span>)
    </span>
  </div>
</div>
"""
st.markdown(info_html, unsafe_allow_html=True)

# --- ナビゲーション ---
days_to_show = 10
col_prev, col_next = st.columns(2)
with col_prev:
    if st.button("<< Prev 10d", use_container_width=True):
        st.session_state['view_date'] -= datetime.timedelta(days=days_to_show)
with col_next:
    if st.button("Next 10d >>", use_container_width=True):
        st.session_state['view_date'] += datetime.timedelta(days=days_to_show)

# --- サイドバー (設定のみ) ---
with st.sidebar:
    st.header("⚙️ Settings")
    st.info(f"📡 Weather: {pressure_status_text}\n{current_pressure} hPa")
    
    st.markdown("---")
    target_cm = st.number_input("Work Limit Level (cm)", value=120, step=10)
    start_h, end_h = st.slider("Workable Hours", 0, 24, (7, 23), format="%d:00")
    
    st.markdown("---")
    if st.button("Back to Today"):
        st.session_state['view_date'] = now_jst.date()

# --- データ生成 (1分刻みで精密計算) ---
# interval_min=1 に設定することで、リストの開始・終了時刻が正確になります
df = model.get_dataframe(st.session_state['view_date'], days=days_to_show, interval_min=1)

# ---------------------------------------------------------
# 作業可能時間の解析
# ---------------------------------------------------------
df['hour'] = df['time'].dt.hour
df['is_safe'] = (df['level'] <= target_cm) & (df['hour'] >= start_h) & (df['hour'] < end_h)

safe_windows = []
if df['is_safe'].any():
    df['group'] = (df['is_safe'] != df['is_safe'].shift()).cumsum()
    groups = df[df['is_safe']].groupby('group')
    
    for _, grp in groups:
        start_t = grp['time'].iloc[0]
        end_t = grp['time'].iloc[-1]
        
        # 10分以上
        if (end_t - start_t).total_seconds() >= 600:
            min_lvl = grp['level'].min()
            min_time = grp.loc[grp['level'].idxmin(), 'time']
            
            duration = end_t - start_t
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            dur_str = f"{hours}:{minutes:02}"
            
            safe_windows.append({
                "date_str": start_t.strftime('%m/%d (%a)'),
                "start": start_t.strftime("%H:%M"),
                "end": end_t.strftime("%H:%M"),
                "duration": dur_str,
                "graph_label": f"Work\n{dur_str}",
                "min_time": min_time,
                "min_level": min_lvl
            })

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

# 2. ピーク (解像度が上がったため、ピーク検出の間隔調整)
# 1分刻みなので、データ点数が増えています。間隔(window)を広げてノイズを拾わないようにします
levels = df['level'].values
times = df['time'].tolist()
# データ間隔が10倍になったので、スキップしながらピークを探すか、条件を厳しくする
# ここでは簡易的に、30分(30データ分)前後と比較
search_step = 30 
for i in range(search_step, len(levels)-search_step, 10): # 10分おきにチェック
    t, l = times[i], levels[i]
    
    # 周辺データ(±30分)の中で最大かつ、基準より高い
    local_max = max(levels[i-search_step:i+search_step])
    local_min = min(levels[i-search_step:i+search_step])
    
    # High Tide
    if l == local_max and l > 180:
        # 重複防止: 直近にプロットしてなければ描画
        ax.scatter(t, l, color='red', marker='^', s=40, zorder=3)
        off_y = 15 if (t.day % 2 == 0) else 30
        ax.annotate(f"{t.strftime('%H:%M')}\n{int(l)}", (t, l), xytext=(0, off_y), 
                    textcoords='offset points', ha='center', fontsize=9, color='#cc0000', fontweight='bold')
    
    # Low Tide
    if l == local_min and l < 180:
        ax.scatter(t, l, color='blue', marker='v', s=40, zorder=3)
        off_y = -25 if (t.day % 2 == 0) else -40
        ax.annotate(f"{t.strftime('%H:%M')}\n{int(l)}", (t, l), xytext=(0, off_y), 
                    textcoords='offset points', ha='center', fontsize=9, color='#0000cc', fontweight='bold')

# 3. Workラベル
for win in safe_windows:
    x = win['min_time']
    y = win['min_level']
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
