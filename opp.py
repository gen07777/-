import streamlit as st
import datetime
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests
import numpy as np
import math

# ==========================================
# 1. アプリ設定
# ==========================================
st.set_page_config(layout="wide", page_title="大西港 潮汐予測")
OWM_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"
STANDARD_PRESSURE = 1013

# ==========================================
# 2. 教師データ (大西港フェリーターミナル)
# ==========================================
# 提供いただいたTide Graph BI(大西港)のデータを正解として使用
TEACHER_DATA = {
    "2026-01-15": [("01:00", 54), ("08:19", 287), ("14:10", 163), ("19:19", 251)],
    "2026-01-16": [("02:00", 37), ("09:00", 309), ("15:00", 149), ("20:19", 260)],
    "2026-01-17": [("02:59", 20), ("09:50", 327), ("15:50", 133), ("21:00", 272)],
    "2026-01-18": [("03:39", 7), ("10:29", 340), ("16:29", 117), ("21:59", 284)],
    "2026-01-19": [("04:19", 0), ("11:00", 348), ("17:00", 102), ("22:39", 293)],
    "2026-01-20": [("04:59", 0), ("11:39", 350), ("17:39", 90), ("23:19", 299)],
    "2026-01-21": [("05:30", 8), ("12:00", 346), ("18:10", 80)],
    "2026-01-22": [("00:00", 299), ("06:09", 23), ("12:39", 337), ("18:49", 73)],
    "2026-01-23": [("00:39", 295), ("06:49", 44), ("13:09", 325), ("19:20", 70)],
    "2026-01-24": [("01:20", 285), ("07:20", 71), ("13:40", 309), ("20:00", 70)],
    "2026-01-25": [("02:19", 271), ("08:00", 102), ("14:19", 290), ("20:59", 73)],
    "2026-01-26": [("03:19", 256), ("08:59", 134), ("14:59", 271), ("21:49", 76)],
    "2026-01-27": [("04:39", 246), ("10:00", 163), ("15:59", 252), ("23:00", 76)],
    "2026-01-28": [("06:19", 251), ("11:59", 178), ("17:00", 239)],
    "2026-01-29": [("00:19", 68), ("07:40", 269), ("13:30", 173), ("18:30", 237)],
    "2026-01-30": [("01:29", 52), ("08:40", 293), ("14:39", 156), ("19:40", 246)],
    "2026-01-31": [("02:20", 34), ("09:20", 314), ("15:20", 136), ("20:40", 262)],
    "2026-02-01": [("03:10", 17), ("10:00", 331), ("16:00", 115), ("21:29", 279)],
    "2026-02-02": [("03:59", 6), ("10:39", 342), ("16:39", 96), ("22:10", 295)],
    "2026-02-03": [("04:30", 1), ("11:00", 348), ("17:09", 79), ("22:59", 306)],
    "2026-02-04": [("05:00", 4), ("11:39", 347), ("17:40", 66), ("23:30", 311)],
    "2026-02-05": [("05:40", 15), ("12:00", 341), ("18:10", 57)],
    "2026-02-06": [("00:09", 310), ("06:19", 34), ("12:39", 331), ("18:49", 52)],
    "2026-02-07": [("00:49", 302), ("06:59", 58), ("13:00", 316), ("19:20", 53)],
    "2026-02-08": [("01:30", 288), ("07:29", 88), ("13:39", 298), ("20:00", 58)],
    "2026-02-09": [("02:20", 270), ("08:10", 121), ("14:10", 278), ("20:59", 67)],
    "2026-02-10": [("03:30", 252), ("09:00", 153), ("14:59", 256), ("21:59", 76)],
    "2026-02-11": [("05:00", 244), ("10:39", 178), ("15:59", 236), ("23:19", 78)],
    "2026-02-12": [("06:59", 254), ("12:40", 181), ("17:39", 226)],
    "2026-02-13": [("00:40", 69), ("08:00", 277), ("14:09", 163), ("19:00", 233)],
    "2026-02-14": [("01:59", 51), ("08:59", 300), ("14:59", 140), ("20:19", 252)]
}

# ==========================================
# 3. スタイル設定
# ==========================================
st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 3rem; }
    h5 { margin-bottom: 0px; }
    /* スマホ対策 */
    @media (max-width: 640px) {
        div[data-testid="stHorizontalBlock"] { flex-direction: row !important; gap: 8px !important; }
        div[data-testid="column"] { width: calc(50% - 4px) !important; flex: 0 0 calc(50% - 4px) !important; min-width: 0 !important; }
        div.stButton > button { width: 100% !important; font-size: 0.9rem !important; padding: 0px !important; height: 2.8rem !important; white-space: nowrap !important; margin: 0px !important; }
    }
    div.stButton > button { width: 100%; margin-top: 0px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 4. ロジック: 自己学習型 (Harmonic Analysis)
# ==========================================
class SelfLearningTideModel:
    def __init__(self, teacher_data, pressure_hpa=1013):
        self.pressure_correction = int(STANDARD_PRESSURE - pressure_hpa)
        # 大西港データを学習
        self.constituents = self.learn_from_data(teacher_data)
        
    def learn_from_data(self, data_map):
        """教師データ(大西港)から潮汐定数を逆算"""
        timestamps = []
        levels = []
        for date_str, peaks in data_map.items():
            base = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            for t_str, lvl in peaks:
                h, m = map(int, t_str.split(":"))
                dt = base.replace(hour=h, minute=m)
                timestamps.append(dt.timestamp())
                levels.append(lvl)
        
        if not timestamps: return None

        # 瀬戸内海・大西港の主要分潮近似 (M2, S2, K1, O1)
        speeds_deg_hr = [28.984, 30.000, 15.041, 13.943] 
        omegas = [s * (np.pi / 180) / 3600 for s in speeds_deg_hr]
        
        t = np.array(timestamps)
        y = np.array(levels)
        
        A = np.ones((len(t), 1))
        for w in omegas:
            A = np.hstack([A, np.cos(w * t)[:, None], np.sin(w * t)[:, None]])
            
        coeffs, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
        
        return {
            "mean": coeffs[0],
            "omegas": omegas,
            "coeffs": coeffs[1:]
        }

    def predict_level(self, dt_obj):
        """学習結果に基づき予測"""
        if not self.constituents: return 0
        t = dt_obj.timestamp()
        val = self.constituents["mean"]
        coeffs = self.constituents["coeffs"]
        omegas = self.constituents["omegas"]
        for i, w in enumerate(omegas):
            c_cos = coeffs[2*i]
            c_sin = coeffs[2*i+1]
            val += c_cos * math.cos(w * t) + c_sin * math.sin(w * t)
        return val + self.pressure_correction

    def get_dataframe(self, start_date, days=5):
        start_dt = datetime.datetime.combine(start_date, datetime.time(0,0))
        end_dt = start_dt + datetime.timedelta(days=days)
        times = []
        levels = []
        curr = start_dt
        while curr < end_dt:
            lvl = self.predict_level(curr)
            times.append(curr)
            levels.append(lvl)
            curr += datetime.timedelta(minutes=5)
        return pd.DataFrame({"time": times, "level": levels})

    def get_peaks(self, start_date, days=5):
        df = self.get_dataframe(start_date, days)
        if df.empty: return pd.DataFrame()
        levels = df['level'].values
        times = df['time'].values
        peaks = []
        window = 12
        for i in range(window, len(levels)-window):
            val = levels[i]
            if val == np.max(levels[i-window:i+window+1]) and val > self.constituents["mean"]:
                peaks.append({"time": pd.to_datetime(times[i]), "level": val, "type": "H"})
            elif val == np.min(levels[i-window:i+window+1]) and val < self.constituents["mean"]:
                peaks.append({"time": pd.to_datetime(times[i]), "level": val, "type": "L"})
        
        res = []
        last_t = None
        for p in peaks:
            if last_t is None or (p['time'] - last_t).total_seconds() > 3600*2:
                res.append(p)
                last_t = p['time']
        return pd.DataFrame(res)

# ==========================================
# 5. ヘルパー関数
# ==========================================
@st.cache_data(ttl=3600)
def get_current_pressure():
    try:
        # 大崎上島(大西港付近)の座標
        url = f"https://api.openweathermap.org/data/2.5/weather?lat=34.23&lon=132.83&appid={OWM_API_KEY}&units=metric"
        return float(requests.get(url, timeout=3).json()['main']['pressure'])
    except: return 1013.0

def get_moon_age(d): return ((d - datetime.date(2000, 1, 6)).days) % 29.53
def get_tide_name(m):
    if m>=28 or m<=2 or 13<=m<=17: return "大潮"
    if 3<=m<=5 or 18<=m<=20: return "中潮"
    if 6<=m<=9 or 21<=m<=24: return "小潮"
    if 10<=m<=12 or m==25: return "長潮"
    return "若潮"

# ==========================================
# 6. UI & 実行
# ==========================================
if 'view_date' not in st.session_state:
    now = datetime.datetime.now() + datetime.timedelta(hours=9)
    # デフォルトを今日に
    st.session_state['view_date'] = now.date()

view_date = st.session_state['view_date']
st.markdown("<h5 style='margin-bottom:5px;'>⚓ 大西港フェリーターミナル 潮汐予測</h5>", unsafe_allow_html=True)

# 予測エンジンの起動
pressure = get_current_pressure()
model = SelfLearningTideModel(TEACHER_DATA, pressure) 

# データ生成
df = model.get_dataframe(view_date, 5)
df_peaks = model.get_peaks(view_date, 5)

# 現在値
curr_now = datetime.datetime.now() + datetime.timedelta(hours=9)
curr_now = curr_now.replace(tzinfo=None)
curr_lvl = model.predict_level(curr_now)

ma = get_moon_age(view_date)
tn = get_tide_name(ma)
p_diff = int(1013 - pressure)
adj_txt = f"+{p_diff}" if p_diff > 0 else f"{p_diff}"

st.markdown(f"""
<div style="font-size:0.9rem; background:#f8f9fa; padding:10px; border:1px solid #ddd; margin-bottom:10px; border-radius:5px;">
 <div><b>期間:</b> {view_date.strftime('%Y/%m/%d')} ～ (5日間) <span style="color:#555; margin-left:10px;">月齢:{ma:.1f} ({tn})</span></div>
 <div style="margin-top:5px;">
   <span style="color:#0066cc; font-weight:bold; font-size:1.1rem;">現在: {curr_now.strftime('%H:%M')} / {int(curr_lvl)}cm</span>
   <div style="font-size:0.8rem; color:#666; margin-top:3px;">
    気圧:{int(pressure)}hPa (<span style="color:#d62728;">{adj_txt}cm</span>) | 大西港独自学習モデル(AI)
   </div>
 </div>
</div>
""", unsafe_allow_html=True)

c1, c2 = st.columns([1,1])
if c1.button("< 前5日"): st.session_state['view_date'] -= datetime.timedelta(days=5)
if c2.button("次5日 >"): st.session_state['view_date'] += datetime.timedelta(days=5)

with st.sidebar:
    st.header("⚙️ 設定")
    st.info("✅ 予測モデル: 稼働中\n(大西港データ学習済み)")
    st.markdown("---")
    target_cm = st.number_input("作業可能潮位 (cm以下)", value=120, step=10)
    start_h, end_h = st.slider("作業時間帯", 0, 24, (7, 23))
    st.markdown("---")
    if st.button("今日に戻る"): 
        st.session_state['view_date'] = (datetime.datetime.now() + datetime.timedelta(hours=9)).date()

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

# グラフ描画
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(df['time'], df['level'], '#0066cc', lw=2, zorder=2, label="Level")
ax.axhline(target_cm, c='orange', ls='--', lw=1.5, label='Limit')
ax.fill_between(df['time'], df['level'], target_cm, where=df['is_safe'], color='#ffcc00', alpha=0.4)

# ピーク注釈
if not df_peaks.empty:
    highs = df_peaks[df_peaks['type'] == 'H']
    lows = df_peaks[df_peaks['type'] == 'L']
    for _, r in highs.iterrows():
        ax.scatter(r['time'], r['level'], c='red', marker='^', s=40, zorder=3)
        off = 15 if r['time'].day % 2 == 0 else 35
        ax.annotate(f"{r['time'].strftime('%H:%M')}\n{int(r['level'])}", (r['time'], r['level']), xytext=(0,off), textcoords='offset points', ha='center', fontsize=8, color='#cc0000', fontweight='bold')
    for _, r in lows.iterrows():
        ax.scatter(r['time'], r['level'], c='blue', marker='v', s=40, zorder=3)
        off = -25 if r['time'].day % 2 == 0 else -45
        ax.annotate(f"{r['time'].strftime('%H:%M')}\n{int(r['level'])}", (r['time'], r['level']), xytext=(0,off), textcoords='offset points', ha='center', fontsize=8, color='#0000cc', fontweight='bold')

for w in safe_windows:
    ax.annotate(w['gl'], (w['mt'], w['ml']), xytext=(0,-85), textcoords='offset points', ha='center', fontsize=8, color='#b8860b', fontweight='bold', bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.7))

ax.set_ylabel("Level (cm)")
ax.grid(True, ls=':', alpha=0.6)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n(%a)'))
ax.set_ylim(bottom=df['level'].min() - 30, top=df['level'].max() + 50)
plt.tight_layout()
st.pyplot(fig)

st.markdown("---")
st.markdown(f"##### 📋 作業可能時間リスト (潮位 {target_cm}cm以下)")
if safe_windows:
    rdf = pd.DataFrame(safe_windows)
    rdf_display = rdf[["日付", "開始", "終了", "時間"]]
    cc = st.columns(2)
    chunks = np.array_split(rdf_display, 2)
    for i, col in enumerate(cc):
        if i < len(chunks) and not chunks[i].empty:
            col.dataframe(chunks[i], hide_index=True, use_container_width=True)
else:
    st.warning("この期間に作業可能な時間帯はありません。")
