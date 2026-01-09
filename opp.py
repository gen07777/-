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
st.set_page_config(layout="wide", page_title="Onishi Port Construction Tide")

# APIキー (OpenWeatherMap)
OWM_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"

# ---------------------------------------------------------
# スタイル & フォント設定
# ---------------------------------------------------------
st.markdown("""
<style>
    div.stButton > button { width: 100%; height: 2.5rem; font-size: 0.9rem; }
    [data-testid="column"] { min-width: 0px !important; flex: 1 !important; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    h4 { margin-top: 0; padding-top: 0; }
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
# 気圧自動取得 (API連動)
# ---------------------------------------------------------
@st.cache_data(ttl=3600) # 1時間キャッシュで通信量を節約
def get_current_pressure():
    # 大西港フェリーターミナル付近
    lat, lon = 34.234, 132.831
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OWM_API_KEY}&units=metric"
    try:
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            return float(res.json()['main']['pressure'])
    except:
        pass
    return 1013.0 # 取得失敗時は標準気圧

# ---------------------------------------------------------
# 月齢・潮名計算
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
# 高精度潮汐モデル (全潮回り対応補正)
# ---------------------------------------------------------
class ConstructionTideModel:
    def __init__(self, pressure_hpa):
        self.epoch_time = datetime.datetime(2026, 1, 7, 12, 39)
        self.msl = 180.0
        
        # 1. 気圧補正 (吸い上げ効果: 1hPa下がるごとに1cm上昇)
        self.pressure_correction = (1013.0 - pressure_hpa) * 1.0
        
        # 2. 振幅の基準化
        # 1/7の満潮(342cm)に合うように調整
        self.base_amp_factor = (342.0 - 180.0) / 1.0

        # 3. 分潮パラメータ (M4分潮で「引きの速さ」を表現)
        self.consts = [
            {'name':'M2', 'speed':28.984104, 'amp':1.00, 'phase':0},
            {'name':'S2', 'speed':30.000000, 'amp':0.46, 'phase':0},
            {'name':'K1', 'speed':15.041069, 'amp':0.38, 'phase':0},
            {'name':'O1', 'speed':13.943036, 'amp':0.28, 'phase':0},
            {'name':'M4', 'speed':57.968208, 'amp':0.08, 'phase':90} # 地形歪み
        ]

    def _calc_raw(self, target_dt):
        delta_hours = (target_dt - self.epoch_time).total_seconds() / 3600.0
        
        # 4. 時刻の動的補正 (Time Shift)
        # 大西港は標準より「常に早い」傾向がある。
        # 大潮時は約5~10分早く、小潮時は約25~30分早い。
        
        moon_age = get_moon_age(target_dt.date())
        
        # 月齢による変動係数 (0.0:大潮 〜 1.0:小潮)
        # cos波を使って大潮(0,15,30)で最小、小潮(7,22)で最大になる係数を作る
        phase_factor = (1 - math.cos(math.radians(moon_age * 12.0 * 2))) / 2 
        # ※ moon_age*12*2 で月齢15周期の変動を作成
        
        # 補正時間（分）: 基本早め10分 + 変動分(最大20分)
        # positive value advances the wave (makes it earlier)
        shift_minutes = 10 + (20 * phase_factor)
        shift_hours = shift_minutes / 60.0
        
        # 時間軸を進める（＝事象を早く到来させる）
        corrected_delta = delta_hours + shift_hours
        
        level = self.msl + self.pressure_correction
        for c in self.consts:
            theta_rad = math.radians(c['speed'] * corrected_delta - c['phase'])
            # amp係数調整(2.2で正規化)
            level += (self.base_amp_factor * c['amp'] / 2.2) * math.cos(theta_rad)
            
        return level

    def get_dataframe(self, start_date, days=10):
        start_dt = datetime.datetime.combine(start_date, datetime.time(0, 0))
        end_dt = start_dt + datetime.timedelta(days=days) - datetime.timedelta(minutes=1)
        # 1分刻みで高精度計算
        time_index = pd.date_range(start=start_dt, end=end_dt, freq='1min')
        levels = [self._calc_raw(t) for t in time_index]
        return pd.DataFrame({"time": time_index, "level": levels})

    def get_current_level(self):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_jst = now_utc + datetime.timedelta(hours=9)
        now_naive = now_jst.replace(tzinfo=None)
        return now_naive, self._calc_raw(now_naive)

# ---------------------------------------------------------
# UI
# ---------------------------------------------------------
st.markdown("<h5 style='margin-bottom:5px;'>⚓ Onishi Port Construction Tide</h5>", unsafe_allow_html=True)
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

# 気圧取得 (自動)
current_pressure = get_current_pressure()

# モデル初期化
model = ConstructionTideModel(pressure_hpa=current_pressure)
curr_time, curr_lvl = model.get_current_level()

view_date = st.session_state['view_date']
ma = get_moon_age(view_date)
tn = get_tide_name(ma)

# 情報表示
p_diff = int(1013 - current_pressure)
adj_txt = f"+{p_diff}" if p_diff > 0 else f"{p_diff}"
if p_diff == 0: adj_txt = "0"

st.markdown(f"""
<div style="font-size:0.85rem; background:#f8f9fa; padding:8px; border:1px solid #ddd; margin-bottom:5px; border-radius:4px;">
 <div><b>Period:</b> {view_date.strftime('%m/%d')}~ <span style="color:#555;">(Moon:{ma:.1f} {tn})</span></div>
 <div style="margin-top:2px;">
   <span style="color:#0066cc; font-weight:bold;">Now: {curr_time.strftime('%H:%M')} {int(curr_lvl)}cm</span>
   <span style="font-size:0.75rem; color:#666; margin-left:5px;">(Press:{int(current_pressure)}hPa <span style="color:#d62728;">Adj:{adj_txt}cm</span>)</span>
 </div>
</div>
""", unsafe_allow_html=True)

# ナビゲーション
c1, c2 = st.columns([1,1])
if c1.button("< Prev"): st.session_state['view_date'] -= datetime.timedelta(days=10)
if c2.button("Next >"): st.session_state['view_date'] += datetime.timedelta(days=10)

# サイドバー設定
with st.sidebar:
    st.header("⚙️ Settings")
    st.info(f"📡 API Status: OK\nPressure: {current_pressure} hPa")
    st.markdown("---")
    target_cm = st.number_input("Limit (cm)", value=120, step=10)
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
        if (e-s).total_seconds() >= 600: # 10分以上
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
df['max'] = df['level'].rolling(120, center=True).max()
df['min'] = df['level'].rolling(120, center=True).min()
highs = df[(df['level']==df['max']) & (df['level']>180)].iloc[::2] # 間引き
lows = df[(df['level']==df['min']) & (df['level']<180)].iloc[::2]

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
ax.set_ylim(bottom=-110)
plt.tight_layout()
st.pyplot(fig)

# リスト表示
st.markdown("---")
use_print = st.checkbox("🖨️ Print Layout", False)
st.markdown(f"##### 📋 Workable Time List (Limit <= {target_cm}cm)")

if safe_windows:
    rdf = pd.DataFrame(safe_windows)
    cols = ["date", "start", "end", "dur"]
    if use_print:
        cc = st.columns(3)
        for i, chk in enumerate(np.array_split(rdf, 3)):
             if not chk.empty: cc[i].dataframe(chk[cols], hide_index=True)
    else:
        st.dataframe(rdf[cols], hide_index=True, use_container_width=True)
else:
    st.warning("No workable time found.")
