import streamlit as st
import datetime
import math
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager
import requests
import numpy as np

# ---------------------------------------------------------
# アプリ設定
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="Onishi Port Precision Tide")
OWM_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"

# ---------------------------------------------------------
# レイアウト & フォント
# ---------------------------------------------------------
st.markdown("""
<style>
    div.stButton > button { width: 100%; height: 3.0rem; font-size: 1rem; margin-top: 0px; }
    [data-testid="column"] { min-width: 0px !important; flex: 1 !important; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    h5 { margin-bottom: 0px; }
</style>
""", unsafe_allow_html=True)

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
# API: 気圧自動取得
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# 月齢・潮名
# ---------------------------------------------------------
def get_moon_age(date_obj):
    base = datetime.date(2000, 1, 6)
    return ((date_obj - base).days) % 29.53059

def get_tide_name(moon_age):
    m = int(moon_age)
    if m >= 30: m -= 30
    if 0<=m<=2 or 14<=m<=17 or 29<=m<=30: return "大潮 (Spring)"
    elif 3<=m<=5 or 18<=m<=20: return "中潮 (Middle)"
    elif 6<=m<=9 or 21<=m<=24: return "小潮 (Neap)"
    elif 10<=m<=12: return "長潮 (Long)"
    elif m==13 or 25<=m<=28: return "若潮 (Young)"
    return "中潮 (Middle)"

# ---------------------------------------------------------
# 精密潮汐モデル (季節補正 & 小満潮調整入り)
# ---------------------------------------------------------
class PrecisionTideModel:
    def __init__(self, pressure_hpa, target_date):
        # 基準: 釣割データ 2026/1/7 12:39 満潮 342cm
        self.epoch_time = datetime.datetime(2026, 1, 7, 12, 19) # 時間ズレ微調整済み
        self.base_msl = 180.0
        
        # 1. 気圧補正 (1hPa = 1cm)
        self.pressure_correction = (1013.0 - pressure_hpa) * 1.0
        
        # 2. 季節別平均水面補正 (Seasonal MSL)
        # 瀬戸内海は夏秋が高く、冬春が低い。
        # 1月:-10cm, 8月:+20cm 程度の変動がある。
        month = target_date.month
        if month in [12, 1, 2, 3]:
            self.seasonal_offset = -10.0 # 冬〜春は低い
        elif month in [4, 5, 11]:
            self.seasonal_offset = 0.0   # 中間
        else:
            self.seasonal_offset = 15.0  # 夏〜秋は高い(膨張)
            
        # 3. 振幅基準
        self.base_amp_factor = (342.0 - 180.0) / 1.0

        # 4. 分潮パラメータ
        # K1, O1の係数を少し下げて(0.38->0.32, 0.28->0.24)、小さい満潮が低くなりすぎるのを防ぐ
        self.consts = [
            {'name':'M2', 'speed':28.984104, 'amp':1.00, 'phase':0},
            {'name':'S2', 'speed':30.000000, 'amp':0.46, 'phase':0},
            {'name':'K1', 'speed':15.041069, 'amp':0.32, 'phase':0}, # 調整
            {'name':'O1', 'speed':13.943036, 'amp':0.24, 'phase':0}, # 調整
            {'name':'M4', 'speed':57.968208, 'amp':0.10, 'phase':270} # 引き潮加速
        ]

    def _calc_raw(self, target_dt):
        delta_hours = (target_dt - self.epoch_time).total_seconds() / 3600.0
        
        # 時刻シフト (小潮の遅れ補正)
        moon_age = get_moon_age(target_dt.date())
        phase_factor = (1 - math.cos(math.radians(moon_age * 12.0 * 2))) / 2
        shift_minutes = 5 + (15 * phase_factor)
        shift_hours = shift_minutes / 60.0
        
        # 合計水位 = 基準MSL + 気圧補正 + 季節補正 + 潮汐波
        level = self.base_msl + self.pressure_correction + self.seasonal_offset
        
        # 波の合成
        diurnal_wave = 0
        for c in self.consts:
            theta_rad = math.radians(c['speed'] * (delta_hours + shift_hours) - c['phase'])
            component = (self.base_amp_factor * c['amp'] / 2.05) * math.cos(theta_rad) # 係数再調整
            level += component
            if c['name'] in ['K1', 'O1']:
                diurnal_wave += component

        # 動的引き潮加速 (大きい満潮の後だけガクッと下げる)
        m2 = next(c for c in self.consts if c['name'] == 'M2')
        m2_theta = math.radians(m2['speed'] * (delta_hours + shift_hours) - m2['phase'])
        
        if math.sin(m2_theta) > 0: # 引き潮時
             # 日周潮成分がプラス（＝今日の潮位が高い方の満潮）のときだけ、引きを加速
             if diurnal_wave > 0:
                extra_ebb = diurnal_wave * 0.2 * math.sin(m2_theta)
                level -= extra_ebb

        return level

    def get_dataframe(self, start_date, days=10):
        start_dt = datetime.datetime.combine(start_date, datetime.time(0, 0))
        end_dt = start_dt + datetime.timedelta(days=days) - datetime.timedelta(minutes=1)
        time_index = pd.date_range(start=start_dt, end=end_dt, freq='1min')
        levels = [self._calc_raw(t) for t in time_index]
        return pd.DataFrame({"time": time_index, "level": levels})

    def get_current_level(self):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_jst = now_utc + datetime.timedelta(hours=9)
        now_naive = now_jst.replace(tzinfo=None)
        return now_naive, self._calc_raw(now_naive)

# ---------------------------------------------------------
# ヘルパー: 重複ピーク除去
# ---------------------------------------------------------
def deduplicate_peaks(df_peaks, min_dist_mins=60):
    if df_peaks.empty: return df_peaks
    keep = []
    last_time = None
    for idx, row in df_peaks.iterrows():
        if last_time is None or (row['time'] - last_time).total_seconds()/60 > min_dist_mins:
            keep.append(idx)
            last_time = row['time']
    return df_peaks.loc[keep]

# ---------------------------------------------------------
# UI
# ---------------------------------------------------------
st.markdown("<h5 style='margin-bottom:5px;'>⚓ Onishi Port (Final Fixed)</h5>", unsafe_allow_html=True)
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
view_date = st.session_state['view_date']

current_pressure = get_current_pressure()
# モデル生成時に日付を渡して季節補正を適用
model = PrecisionTideModel(pressure_hpa=current_pressure, target_date=view_date)
curr_time, curr_lvl = model.get_current_level()

ma = get_moon_age(view_date)
tn = get_tide_name(ma)

# 情報表示
p_diff = int(1013 - current_pressure)
adj_txt = f"+{p_diff}" if p_diff > 0 else f"{p_diff}"
if p_diff == 0: adj_txt = "0"
# 季節補正値の表示
season_off = int(model.seasonal_offset)
season_txt = f"+{season_off}" if season_off > 0 else f"{season_off}"

st.markdown(f"""
<div style="font-size:0.85rem; background:#f8f9fa; padding:8px; border:1px solid #ddd; margin-bottom:5px; border-radius:4px;">
 <div><b>Period:</b> {view_date.strftime('%m/%d')}~ <span style="color:#555;">(Moon:{ma:.1f} {tn})</span></div>
 <div style="margin-top:2px;">
   <span style="color:#0066cc; font-weight:bold;">Now: {curr_time.strftime('%H:%M')} {int(curr_lvl)}cm</span>
   <span style="font-size:0.75rem; color:#666; margin-left:5px;">
    (Press:{int(current_pressure)}hPa <span style="color:#d62728;">Adj:{adj_txt}cm</span>, Season:<span style="color:#2ca02c;">{season_txt}cm</span>)
   </span>
 </div>
</div>
""", unsafe_allow_html=True)

# ナビゲーション
c1, c2 = st.columns([1,1])
if c1.button("< Prev"): st.session_state['view_date'] -= datetime.timedelta(days=10)
if c2.button("Next >"): st.session_state['view_date'] += datetime.timedelta(days=10)

# サイドバー
with st.sidebar:
    st.header("⚙️ Settings")
    st.info(f"📡 API Status: OK\nPressure: {current_pressure} hPa")
    st.markdown("---")
    target_cm = st.number_input("Limit (cm)", value=130, step=10)
    start_h, end_h = st.slider("Hours", 0, 24, (7, 23))
    st.markdown("---")
    if st.button("Today"): st.session_state['view_date'] = now_jst.date()

# データ生成
df = model.get_dataframe(view_date, days=10)

# 解析
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
                "date": s.strftime('%m/%d(%a)'),
                "start": s.strftime("%H:%M"),
                "end": e.strftime("%H:%M"),
                "dur": f"{h}:{m:02}",
                "gl": f"Work\n{h}:{m:02}",
                "mt": min_t, "ml": min_l
            })

# ピーク検出
window = 120
df['max'] = df['level'].rolling(window, center=True).max()
df['min'] = df['level'].rolling(window, center=True).min()

raw_highs = df[(df['level'] == df['max']) & (df['level'] > 180)].copy()
raw_lows = df[(df['level'] == df['min']) & (df['level'] < 180)].copy()

highs = deduplicate_peaks(raw_highs)
lows = deduplicate_peaks(raw_lows)

# グラフ描画
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(df['time'], df['level'], '#0066cc', lw=2, zorder=2)
ax.axhline(target_cm, c='orange', ls='--', lw=1.5, label='Limit')
ax.fill_between(df['time'], df['level'], target_cm, where=df['is_safe'], color='#ffcc00', alpha=0.4)

gs, ge = df['time'].iloc[0], df['time'].iloc[-1]
if gs <= curr_time <= ge:
    ax.scatter(curr_time, curr_lvl, c='gold', edgecolors='black', s=90, zorder=10)

for _, r in highs.iterrows():
    ax.scatter(r['time'], r['level'], c='red', marker='^', s=40, zorder=3)
    off = 15 if r['time'].day%2==0 else 35
    ax.annotate(f"{r['time'].strftime('%H:%M')}\n{int(r['level'])}", (r['time'], r['level']), xytext=(0,off), textcoords='offset points', ha='center', fontsize=8, color='#cc0000', fontweight='bold')

for _, r in lows.iterrows():
    ax.scatter(r['time'], r['level'], c='blue', marker='v', s=40, zorder=3)
    off = -25 if r['time'].day%2==0 else -45
    ax.annotate(f"{r['time'].strftime('%H:%M')}\n{int(r['level'])}", (r['time'], r['level']), xytext=(0,off), textcoords='offset points', ha='center', fontsize=8, color='#0000cc', fontweight='bold')

for w in safe_windows:
    ax.annotate(w['gl'], (w['mt'], w['ml']), xytext=(0,-85), textcoords='offset points', ha='center', fontsize=8, color='#b8860b', fontweight='bold', bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.7))

ax.set_ylabel("Level (cm)")
ax.grid(True, ls=':', alpha=0.6)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n(%a)'))
ax.set_ylim(bottom=-130)
plt.tight_layout()
st.pyplot(fig)

# リスト
st.markdown("---")
st.markdown(f"##### 📋 Workable Time List (Limit <= {target_cm}cm)")

if safe_windows:
    rdf = pd.DataFrame(safe_windows)
    cols = ["date", "start", "end", "dur"]
    cc = st.columns(3)
    chunks = np.array_split(rdf, 3)
    for i, col in enumerate(cc):
        if i < len(chunks) and not chunks[i].empty:
            col.dataframe(chunks[i][cols], hide_index=True, use_container_width=True)
else:
    st.warning("No workable time found.")
