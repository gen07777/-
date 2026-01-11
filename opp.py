エラーの解消、よかったです！
スマホで「前の5日間」「次の5日間」のボタンが上下に並んでしまう（積み重なってしまう）件ですね。
Streamlitはスマホだと自動的に縦並びにする仕様があるのですが、強制的に「左右（横並び）」にする魔法のCSSを強化して組み込みました。
また、下のリストもスマホで3列だと潰れてしまうため、2列（左右）で見やすく調整しました。
これを opp.py に上書きしてください。
import streamlit as st
import datetime
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests
import numpy as np
import math

# ==========================================
# 1. アプリ設定 & 定数定義
# ==========================================
st.set_page_config(layout="wide", page_title="大西港 潮汐予測")

# APIキー (OpenWeatherMap)
OWM_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"

# 補正ロジック定数
TIME_OFFSET_MIN = 1       # 時間補正 +1分
LEVEL_BASE_OFFSET = 13    # 基準面補正 +13cm
STANDARD_PRESSURE = 1013  # 標準気圧

# ==========================================
# 2. スタイル & フォント設定
# ==========================================
st.markdown("""
<style>
    /* ボタンのスタイル調整 */
    div.stButton > button { 
        width: 100%; 
        height: 3.0rem; 
        font-size: 1rem; 
        margin-top: 0px;
        padding: 0px; /* スマホでの文字切れ防止 */
    }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    h5 { margin-bottom: 0px; }

    /* 【重要】スマホでもカラムを強制的に横並びにするCSS */
    [data-testid="column"] {
        width: calc(50% - 1rem) !important;
        flex: 1 1 calc(50% - 1rem) !important;
        min-width: 0 !important;
    }
</style>
""", unsafe_allow_html=True)

# グラフのフォント設定（英語フォントを指定して□化けを防ぐ）
def configure_font():
    plt.rcParams.update(plt.rcParamsDefault) # デフォルトに戻すのが一番安全
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans', 'Verdana']
configure_font()

# ==========================================
# 3. データ取得 (API & 気象庁)
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

# ==========================================
# 4. 高精度スプライン補間 (Catmull-Rom)
# ==========================================
def catmull_rom_spline(p0, p1, p2, p3, n_points=30):
    t = np.linspace(0, 1, n_points)
    t2 = t * t
    t3 = t2 * t
    v0 = (p2 - p0) * 0.5
    v1 = (p3 - p1) * 0.5
    a = 2*p1 - 2*p2 + v0 + v1
    b = -3*p1 + 3*p2 - 2*v0 - v1
    c = v0
    d = p1
    return a*t3 + b*t2 + c*t + d

def generate_smooth_curve(timestamps, hourly_levels):
    """毎時データをなめらかな曲線にする"""
    y = hourly_levels
    y_padded = [y[0]] + y + [y[-1]]
    smooth_times = []
    smooth_levels = []
    
    for i in range(len(y) - 1):
        p0, p1, p2, p3 = y_padded[i], y_padded[i+1], y_padded[i+2], y_padded[i+3]
        segment_levels = catmull_rom_spline(p0, p1, p2, p3, n_points=60)
        t_start = timestamps[i]
        segment_times = [t_start + datetime.timedelta(minutes=m) for m in range(60)]
        smooth_levels.extend(segment_levels)
        smooth_times.extend(segment_times)
    
    smooth_times.append(timestamps[-1])
    smooth_levels.append(hourly_levels[-1])
    return pd.DataFrame({"time": smooth_times, "level": smooth_levels})

# ==========================================
# 5. ヘルパー関数
# ==========================================
def get_moon_age(date_obj):
    base = datetime.date(2000, 1, 6)
    return ((date_obj - base).days) % 29.53059

def get_tide_name(moon_age):
    m = int(moon_age)
    if m >= 30: m -= 30
    if 0<=m<=2 or 14<=m<=17 or 29<=m<=30: return "大潮"
    elif 3<=m<=5 or 18<=m<=20: return "中潮"
    elif 6<=m<=9 or 21<=m<=24: return "小潮"
    elif 10<=m<=12: return "長潮"
    elif m==13 or 25<=m<=28: return "若潮"
    return "中潮"

def deduplicate_peaks(df_peaks, min_dist_mins=60):
    if df_peaks.empty: return df_peaks
    keep = []
    last_time = None
    for idx, row in df_peaks.iterrows():
        if last_time is None or (row['time'] - last_time).total_seconds()/60 > min_dist_mins:
            keep.append(idx)
            last_time = row['time']
    return df_peaks.loc[keep]

# ==========================================
# 6. メイン予測モデルクラス
# ==========================================
class OnishiTideModel:
    def __init__(self, pressure_hpa, year=2026):
        self.jma_map = fetch_jma_data_map(year)
        self.pressure_correction = int(STANDARD_PRESSURE - pressure_hpa)
        self.total_level_offset = LEVEL_BASE_OFFSET + self.pressure_correction
        self.time_offset = TIME_OFFSET_MIN
    
    def get_backup_level(self, dt):
        epoch = datetime.datetime(2026, 1, 1, 0, 0)
        delta_h = (dt - epoch).total_seconds() / 3600.0
        level = 180 
        level += 110 * math.cos(2 * math.pi * delta_h / 12.42 - 1.0) 
        level += 40 * math.cos(2 * math.pi * delta_h / 24.0 - 2.0)
        return int(level)

    def get_dataframe(self, start_date, days=5):
        timestamps_hourly = []
        levels_hourly = []
        
        start_dt = datetime.datetime.combine(start_date, datetime.time(0, 0))
        calc_start = start_dt - datetime.timedelta(hours=2)
        calc_end = start_dt + datetime.timedelta(days=days) + datetime.timedelta(hours=2)
        
        curr = calc_start
        while curr <= calc_end:
            d_str = curr.strftime("%Y-%m-%d")
            hour = curr.hour
            val = None
            if d_str in self.jma_map:
                try: val = self.jma_map[d_str][hour]
                except: pass
            if val is None:
                val = self.get_backup_level(curr)
            
            final_val = val + self.total_level_offset
            t_point = curr + datetime.timedelta(minutes=self.time_offset)
            timestamps_hourly.append(t_point)
            levels_hourly.append(final_val)
            curr += datetime.timedelta(hours=1)
            
        df_smooth = generate_smooth_curve(timestamps_hourly, levels_hourly)
        mask = (df_smooth['time'] >= start_dt) & (df_smooth['time'] < (start_dt + datetime.timedelta(days=days)))
        return df_smooth.loc[mask].reset_index(drop=True)

    def get_current_level(self, df_fine):
        now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
        now_naive = now_jst.replace(tzinfo=None)
        if df_fine.empty or now_naive < df_fine['time'].iloc[0] or now_naive > df_fine['time'].iloc[-1]:
            return now_naive, self.get_backup_level(now_naive) + self.total_level_offset
        idx = (df_fine['time'] - now_naive).abs().idxmin()
        return now_naive, df_fine.loc[idx, 'level']

# ==========================================
# 7. UI表示・実行部
# ==========================================
if 'view_date' not in st.session_state:
    now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    if now_jst.year != 2026:
        st.session_state['view_date'] = datetime.date(2026, 1, 9)
    else:
        st.session_state['view_date'] = now_jst.date()

view_date = st.session_state['view_date']
st.markdown("<h5 style='margin-bottom:5px;'>⚓ 大西港 潮汐・作業予報</h5>", unsafe_allow_html=True)

current_pressure = get_current_pressure()
model = OnishiTideModel(pressure_hpa=current_pressure, year=2026)
df = model.get_dataframe(view_date, days=5)
curr_time, curr_lvl = model.get_current_level(df)

ma = get_moon_age(view_date)
tn = get_tide_name(ma)
p_diff = int(1013 - current_pressure)
adj_txt = f"+{p_diff}" if p_diff > 0 else f"{p_diff}"

st.markdown(f"""
<div style="font-size:0.9rem; background:#f8f9fa; padding:10px; border:1px solid #ddd; margin-bottom:10px; border-radius:5px;">
 <div><b>期間:</b> {view_date.strftime('%Y/%m/%d')} ～ (5日間) <span style="color:#555; margin-left:10px;">月齢:{ma:.1f} ({tn})</span></div>
 <div style="margin-top:5px;">
   <span style="color:#0066cc; font-weight:bold; font-size:1.1rem;">現在: {curr_time.strftime('%H:%M')} / {int(curr_lvl)}cm</span>
   <div style="font-size:0.8rem; color:#666; margin-top:3px;">
    気圧:{int(current_pressure)}hPa (<span style="color:#d62728;">{adj_txt}cm</span>) + 地形差 <span style="color:#2ca02c;">+13cm</span>
   </div>
 </div>
</div>
""", unsafe_allow_html=True)

# ナビゲーション (スマホでも横並び)
c1, c2 = st.columns([1,1])
if c1.button("前の5日間 <"): st.session_state['view_date'] -= datetime.timedelta(days=5)
if c2.button("> 次の5日間"): st.session_state['view_date'] += datetime.timedelta(days=5)

# サイドバー
with st.sidebar:
    st.header("⚙️ 設定")
    st.info(f"気圧: {current_pressure} hPa")
    st.markdown("---")
    target_cm = st.number_input("作業可能潮位 (cm以下)", value=120, step=10)
    start_h, end_h = st.slider("作業時間帯", 0, 24, (7, 23))
    st.markdown("---")
    if st.button("基準日 (2026/1/9)"): st.session_state['view_date'] = datetime.date(2026, 1, 9)

# 作業可能判定
df['hour'] = df['time'].dt.hour
df['is_safe'] = (df['level'] <= target_cm) & (df['hour'] >= start_h) & (df['hour'] < end_h)

safe_windows = []
if df['is_safe'].any():
    df['grp'] = (df['is_safe'] != df['is_safe'].shift()).cumsum()
    for _, g in df[df['is_safe']].groupby('grp'):
        s, e = g['time'].iloc[0], g['time'].iloc[-1]
        if (e-s).total_seconds() >= 600:
            min_l = g['level'].min()
            min_t = g.loc[g['level'].idxmin(), 'time']
            d = e - s
            h, m = d.seconds//3600, (d.seconds%3600)//60
            
            safe_windows.append({
                "日付": s.strftime('%m/%d(%a)'),
                "開始": s.strftime("%H:%M"),
                "終了": e.strftime("%H:%M"),
                "時間": f"{h}:{m:02}",
                "gl": f"Work\n{h}:{m:02}",
                "mt": min_t, "ml": min_l
            })

# ピーク検出
peak_window = 60
df['is_high'] = False
df['is_low'] = False
levels_arr = df['level'].values
for i in range(peak_window, len(levels_arr)-peak_window):
    window = levels_arr[i-peak_window : i+peak_window+1]
    center = levels_arr[i]
    if center == np.max(window) and center > 150:
        df.at[i, 'is_high'] = True
    if center == np.min(window) and center < 250:
        df.at[i, 'is_low'] = True

highs = deduplicate_peaks(df[df['is_high']].copy())
lows = deduplicate_peaks(df[df['is_low']].copy())

# グラフ描画
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(df['time'], df['level'], '#0066cc', lw=2, zorder=2, label="Level")
ax.axhline(target_cm, c='orange', ls='--', lw=1.5, label='Limit')
ax.fill_between(df['time'], df['level'], target_cm, where=df['is_safe'], color='#ffcc00', alpha=0.4)

gs, ge = df['time'].iloc[0], df['time'].iloc[-1]
if gs <= curr_time <= ge:
    ax.scatter(curr_time, curr_lvl, c='gold', edgecolors='black', s=100, zorder=10)

for _, r in highs.iterrows():
    ax.scatter(r['time'], r['level'], c='red', marker='^', s=40, zorder=3)
    off = 15 if r['time'].day % 2 == 0 else 35
    ax.annotate(f"{r['time'].strftime('%H:%M')}\n{int(r['level'])}", 
                (r['time'], r['level']), xytext=(0,off), textcoords='offset points', 
                ha='center', fontsize=8, color='#cc0000', fontweight='bold')

for _, r in lows.iterrows():
    ax.scatter(r['time'], r['level'], c='blue', marker='v', s=40, zorder=3)
    off = -25 if r['time'].day % 2 == 0 else -45
    ax.annotate(f"{r['time'].strftime('%H:%M')}\n{int(r['level'])}", 
                (r['time'], r['level']), xytext=(0,off), textcoords='offset points', 
                ha='center', fontsize=8, color='#0000cc', fontweight='bold')

for w in safe_windows:
    ax.annotate(w['gl'], (w['mt'], w['ml']), xytext=(0,-85), textcoords='offset points', 
                ha='center', fontsize=8, color='#b8860b', fontweight='bold', 
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.7))

ax.set_ylabel("Level (cm)")
ax.grid(True, ls=':', alpha=0.6)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n(%a)'))
ax.set_ylim(bottom=df['level'].min() - 30, top=df['level'].max() + 50)
plt.tight_layout()
st.pyplot(fig)

# 作業時間リスト (スマホ対応: 2列表示)
st.markdown("---")
st.markdown(f"##### 📋 作業可能時間リスト (潮位 {target_cm}cm以下)")

if safe_windows:
    rdf = pd.DataFrame(safe_windows)
    rdf_display = rdf[["日付", "開始", "終了", "時間"]]
    
    # 【変更】スマホで見やすいように、3列ではなく2列に分割する
    cc = st.columns(2)
    chunks = np.array_split(rdf_display, 2)
    for i, col in enumerate(cc):
        if i < len(chunks) and not chunks[i].empty:
            col.dataframe(chunks[i], hide_index=True, use_container_width=True)
else:
    st.warning("この期間に作業可能な時間帯はありません。")

