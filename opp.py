import streamlit as st
import datetime
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests
import numpy as np
import math

# ---------------------------------------------------------
# 1. アプリ設定 & 定数
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="Onishi Port Precision Tide")
OWM_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"

# 大西港 (大崎上島) 補正定数
LEVEL_BASE_OFFSET = 0     # 紙面データをベースにするため補正は0スタート
STANDARD_PRESSURE = 1013  # 標準気圧

# ---------------------------------------------------------
# 2. 紙面のデータ（正解データ）をアンカーとして登録
# ---------------------------------------------------------
# 紙面の満潮・干潮時刻と潮位をここに定義します
# これにより、グラフは必ずこの点を通ります
ANCHOR_POINTS = [
    # 1月9日
    {"time": "2026-01-09 05:01", "level": -9, "type": "low"},
    {"time": "2026-01-09 11:57", "level": 378, "type": "high"},
    {"time": "2026-01-09 17:50", "level": 121, "type": "low"},
    {"time": "2026-01-09 23:25", "level": 310, "type": "high"},
    # 1月10日
    {"time": "2026-01-10 05:42", "level": 18, "type": "low"},
    {"time": "2026-01-10 12:34", "level": 373, "type": "high"},
    {"time": "2026-01-10 18:30", "level": 114, "type": "low"},
    # 1月11日
    {"time": "2026-01-11 00:10", "level": 307, "type": "high"}, # 前日深夜からの推測
    {"time": "2026-01-11 06:23", "level": 45, "type": "low"},
    {"time": "2026-01-11 13:11", "level": 365, "type": "high"},
    {"time": "2026-01-11 19:13", "level": 109, "type": "low"},
    # 1月12日
    {"time": "2026-01-12 00:56", "level": 300, "type": "high"},
    {"time": "2026-01-12 07:05", "level": 72, "type": "low"},
    {"time": "2026-01-12 13:48", "level": 352, "type": "high"},
    {"time": "2026-01-12 19:58", "level": 107, "type": "low"},
    # 1月13日
    {"time": "2026-01-13 01:45", "level": 288, "type": "high"},
    {"time": "2026-01-13 07:49", "level": 98, "type": "low"},
    {"time": "2026-01-13 14:27", "level": 337, "type": "high"},
    {"time": "2026-01-13 20:48", "level": 105, "type": "low"},
    # 1月14日
    {"time": "2026-01-14 02:40", "level": 274, "type": "high"},
    {"time": "2026-01-14 08:38", "level": 120, "type": "low"}, # 推測
    {"time": "2026-01-14 15:08", "level": 320, "type": "high"},
    {"time": "2026-01-14 21:44", "level": 105, "type": "low"},
]

# ---------------------------------------------------------
# 3. レイアウト & スタイル
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
# 4. データ取得ロジック (気圧のみ)
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
# 5. 滑らか曲線生成ロジック (Cosine Interpolation)
# ---------------------------------------------------------
def cosine_interpolate(y1, y2, mu):
    """2点間を波打つように補間する"""
    mu2 = (1 - math.cos(mu * math.pi)) / 2
    return (y1 * (1 - mu2) + y2 * mu2)

def generate_tide_curve(anchors, interval_minutes=5):
    """アンカーポイント間を5分刻みで補間して滑らかなカーブを作る"""
    times = []
    levels = []
    
    # 日付順にソート
    sorted_anchors = sorted(anchors, key=lambda x: x["time"])
    
    for i in range(len(sorted_anchors) - 1):
        p_start = sorted_anchors[i]
        p_end = sorted_anchors[i+1]
        
        t_start = datetime.datetime.strptime(p_start["time"], "%Y-%m-%d %H:%M")
        t_end = datetime.datetime.strptime(p_end["time"], "%Y-%m-%d %H:%M")
        
        y_start = p_start["level"]
        y_end = p_end["level"]
        
        # 時間差(分)
        total_minutes = (t_end - t_start).total_seconds() / 60
        steps = int(total_minutes / interval_minutes)
        
        for s in range(steps):
            mu = s / steps
            # コサイン補間で滑らかに
            interp_y = cosine_interpolate(y_start, y_end, mu)
            interp_t = t_start + datetime.timedelta(minutes=s*interval_minutes)
            
            times.append(interp_t)
            levels.append(interp_y)
            
    return pd.DataFrame({"time": times, "level": levels})

# ---------------------------------------------------------
# 6. ヘルパー関数
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# 7. メイン処理 & UI
# ---------------------------------------------------------
if 'view_date' not in st.session_state:
    st.session_state['view_date'] = datetime.date(2026, 1, 9)

view_date = st.session_state['view_date']
st.markdown("<h5 style='margin-bottom:5px;'>⚓ Onishi Port (Paper Match)</h5>", unsafe_allow_html=True)

# 気圧取得と補正値計算
current_pressure = get_current_pressure()
pressure_correction = int(STANDARD_PRESSURE - current_pressure) # 1hPa = 1cm吸い上げ

# データ生成
# 1. 紙面のデータをベースに曲線を生成
df = generate_tide_curve(ANCHOR_POINTS, interval_minutes=5)

# 2. 気圧補正を適用 (紙面データ + 気圧差)
df['level'] = df['level'] + pressure_correction

# 表示範囲のフィルタリング (表示日から5日間)
start_dt = datetime.datetime.combine(view_date, datetime.time(0,0))
end_dt = start_dt + datetime.timedelta(days=5)
df = df[(df['time'] >= start_dt) & (df['time'] <= end_dt)]

# 現在時刻の取得 (デモ用に2026年に合わせる)
now_real = datetime.datetime.now()
curr_time = datetime.datetime(2026, 1, 9, now_real.hour, now_real.minute) # デモ用現在時刻
# 現在潮位の取得
if not df.empty:
    idx = (df['time'] - curr_time).abs().idxmin()
    curr_lvl = df.loc[idx, 'level']
else:
    curr_lvl = 0

ma = get_moon_age(view_date)
tn = get_tide_name(ma)

# 情報表示
p_diff_txt = f"+{pressure_correction}" if pressure_correction > 0 else f"{pressure_correction}"

st.markdown(f"""
<div style="font-size:0.85rem; background:#f8f9fa; padding:8px; border:1px solid #ddd; margin-bottom:5px; border-radius:4px;">
 <div><b>Period:</b> {view_date.strftime('%m/%d')}~ (5 Days) <span style="color:#555;">(Moon:{ma:.1f} {tn})</span></div>
 <div style="margin-top:2px;">
   <span style="color:#0066cc; font-weight:bold;">Now (Demo): {curr_time.strftime('%H:%M')} {int(curr_lvl)}cm</span>
   <span style="font-size:0.75rem; color:#666; margin-left:5px;">
    (Press:{int(current_pressure)}hPa <span style="color:#d62728;">Adj:{p_diff_txt}cm</span> Included)
   </span>
 </div>
</div>
""", unsafe_allow_html=True)

# サイドバー設定
with st.sidebar:
    st.header("⚙️ Settings")
    st.info(f"📡 Pressure: {current_pressure} hPa")
    st.markdown("---")
    target_cm = st.number_input("Work Limit (cm)", value=120, step=10)
    start_h, end_h = st.slider("Work Hours", 0, 24, (7, 23))

# 作業可能時間の判定
df['hour'] = df['time'].dt.hour
df['is_safe'] = (df['level'] <= target_cm) & (df['hour'] >= start_h) & (df['hour'] <= end_h)

# 作業時間リスト作成
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

# ピークの抽出 (グラフ表示用)
# アンカーポイントそのものを表示すれば確実
display_anchors = []
for p in ANCHOR_POINTS:
    pt = datetime.datetime.strptime(p['time'], "%Y-%m-%d %H:%M")
    if start_dt <= pt <= end_dt:
        # 気圧補正を加味して表示
        display_anchors.append({
            "time": pt,
            "level": p['level'] + pressure_correction,
            "type": p['type']
        })
highs = [p for p in display_anchors if p['type'] == 'high']
lows = [p for p in display_anchors if p['type'] == 'low']

# ---------------------------------------------------------
# 8. グラフ描画 (Matplotlib)
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5))

# メイン潮位線 (滑らかな曲線)
ax.plot(df['time'], df['level'], '#0066cc', lw=2, zorder=2, label="Tide Level")

# 制限ライン
ax.axhline(target_cm, c='orange', ls='--', lw=1.5, label='Limit')

# 作業可能エリアの塗りつぶし
ax.fill_between(df['time'], df['level'], target_cm, where=df['is_safe'], color='#ffcc00', alpha=0.4)

# 現在位置
if not df.empty:
    ax.scatter(curr_time, curr_lvl, c='gold', edgecolors='black', s=90, zorder=10, label="Now")

# 満潮 (赤 ▲)
for r in highs:
    ax.scatter(r['time'], r['level'], c='red', marker='^', s=40, zorder=3)
    off = 15 if r['time'].day % 2 == 0 else 35
    ax.annotate(f"{r['time'].strftime('%H:%M')}\n{int(r['level'])}", 
                (r['time'], r['level']), xytext=(0,off), textcoords='offset points', 
                ha='center', fontsize=8, color='#cc0000', fontweight='bold')

# 干潮 (青 ▼)
for r in lows:
    ax.scatter(r['time'], r['level'], c='blue', marker='v', s=40, zorder=3)
    off = -25 if r['time'].day % 2 == 0 else -45
    ax.annotate(f"{r['time'].strftime('%H:%M')}\n{int(r['level'])}", 
                (r['time'], r['level']), xytext=(0,off), textcoords='offset points', 
                ha='center', fontsize=8, color='#0000cc', fontweight='bold')

# 作業時間の注釈
for w in safe_windows:
    ax.annotate(w['gl'], (w['mt'], w['ml']), xytext=(0,-85), textcoords='offset points', 
                ha='center', fontsize=8, color='#b8860b', fontweight='bold', 
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.7))

ax.set_ylabel("Level (cm)")
ax.grid(True, ls=':', alpha=0.6)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n(%a)'))

# Y軸調整
y_vals = df['level']
if not y_vals.empty:
    ax.set_ylim(bottom=y_vals.min() - 30, top=y_vals.max() + 50)

plt.tight_layout()
st.pyplot(fig)

# ---------------------------------------------------------
# 9. 作業時間リスト
# ---------------------------------------------------------
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
    st.warning("No workable time found in this period.")
