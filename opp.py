import streamlit as st
import datetime
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests
import numpy as np
import math
import re

# ==========================================
# 1. アプリ設定
# ==========================================
st.set_page_config(layout="wide", page_title="大西港 潮汐予測")
OWM_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"
STANDARD_PRESSURE = 1013

# ==========================================
# 2. 教師データ (大西港フェリーターミナル)
# ==========================================
# ベースとなる学習データ (1/15 - 2/14)
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
# 3. スプレッドシート読み込み機能
# ==========================================
@st.cache_data(ttl=600) # 10分間キャッシュ
def fetch_sheet_data(csv_url):
    """Googleスプレッドシート(CSV公開)からデータを読み込む"""
    if not csv_url:
        return {}
    
    data_map = {}
    try:
        # pandasでCSVとして読み込む
        # ヘッダーなし(A,B,C列)を想定。エラー回避のため列名指定は柔軟に。
        # A列:日付, B列:時間, C列:潮位
        df = pd.read_csv(csv_url, header=None)
        
        # 必要な3列だけ抽出 (念のため)
        df = df.iloc[:, :3]
        df.columns = ["date", "time", "level"]
        
        # データの解析
        for _, row in df.iterrows():
            try:
                # 日付の正規化
                d_str = pd.to_datetime(row['date'], errors='coerce')
                if pd.isnull(d_str): continue
                d_str = d_str.strftime("%Y-%m-%d")
                
                t_str = str(row['time']).strip()
                
                # 潮位のクリーニング ("300cm" -> 300)
                l_val = row['level']
                if isinstance(l_val, str):
                    l_str = l_val.lower().replace("cm", "").strip()
                    lvl = int(float(l_str))
                else:
                    lvl = int(l_val)
                
                if d_str not in data_map:
                    data_map[d_str] = []
                data_map[d_str].append((t_str, lvl))
                
            except:
                continue
                
    except Exception as e:
        # 読み込み失敗時は空を返してアプリを止めない
        return {}
        
    return data_map

# ==========================================
# 4. スタイル設定
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

def configure_font():
    plt.rcParams.update(plt.rcParamsDefault)
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans', 'Verdana']
configure_font()

# ==========================================
# 5. ロジック: 自己学習型
# ==========================================
class SelfLearningTideModel:
    def __init__(self, teacher_data, sheet_data, pressure_hpa=1013):
        self.pressure_correction = int(STANDARD_PRESSURE - pressure_hpa)
        
        # データの結合
        combined_data = teacher_data.copy()
        for k, v in sheet_data.items():
            combined_data[k] = v
            
        self.constituents = self.learn_from_data(combined_data)
        self.raw_data = combined_data 
        
    def learn_from_data(self, data_map):
        timestamps = []
        levels = []
        for date_str, peaks in data_map.items():
            try:
                base = datetime.datetime.strptime(date_str, "%Y-%m-%d")
                for t_str, lvl in peaks:
                    h, m = map(int, t_str.split(":"))
                    dt = base.replace(hour=h, minute=m)
                    timestamps.append(dt.timestamp())
                    levels.append(lvl)
            except: continue
        
        if not timestamps: return None

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

    def get_max_date(self):
        if not self.raw_data: return None
        all_dates = []
        for d in self.raw_data.keys():
            try:
                all_dates.append(datetime.datetime.strptime(d, "%Y-%m-%d").date())
            except: continue
        return max(all_dates) if all_dates else None

# ==========================================
# 6. UI & 実行
# ==========================================
@st.cache_data(ttl=3600)
def get_current_pressure():
    try:
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

if 'view_date' not in st.session_state:
    st.session_state['view_date'] = (datetime.datetime.now() + datetime.timedelta(hours=9)).date()

view_date = st.session_state['view_date']
st.markdown("<h5 style='margin-bottom:5px;'>⚓ 大西港フェリーターミナル 潮汐予測</h5>", unsafe_allow_html=True)

# ------------------------------------
# サイドバー (スプレッドシート連携)
# ------------------------------------
with st.sidebar:
    st.header("⚙️ 設定")
    
    st.subheader("📊 データ連携")
    st.caption("Googleスプレッドシートのデータを自動で取り込みます。")
    
    # ユーザー提供のスプレッドシートIDから、CSV出力用URLを生成
    # ID: 1jcPC_G9aU2sV77BcqLZYfMDAoPV9_HOQl-tVKhNV7qc
    DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1jcPC_G9aU2sV77BcqLZYfMDAoPV9_HOQl-tVKhNV7qc/export?format=csv"
    
    sheet_url = st.text_input("スプレッドシートURL(CSV)", value=DEFAULT_SHEET_URL)
    
    # データの読み込み
    sheet_data = fetch_sheet_data(sheet_url)
    
    st.markdown("---")
    target_cm = st.number_input("作業可能潮位 (cm以下)", value=120, step=10)
    start_h, end_h = st.slider("作業時間帯", 0, 24, (7, 23))
    st.markdown("---")
    if st.button("今日に戻る"): st.session_state['view_date'] = (datetime.datetime.now() + datetime.timedelta(hours=9)).date()

# モデル生成 (内蔵 + シート)
pressure = get_current_pressure()
model = SelfLearningTideModel(TEACHER_DATA, sheet_data, pressure)
data_max_date = model.get_max_date()

# データの登録期間表示
if data_max_date:
    if data_max_date >= view_date:
        st.sidebar.success(f"データ登録期間:\n～ {data_max_date.strftime('%Y/%m/%d')}")
    else:
        st.sidebar.warning(f"データ登録期間:\n～ {data_max_date.strftime('%Y/%m/%d')}\n(これ以降はAI予測です)")
else:
    st.sidebar.warning("データ未登録(内蔵のみ)")

# データ生成
df = model.get_dataframe(view_date, 5)
df_peaks = model.get_peaks(view_date, 5)

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
    気圧:{int(pressure)}hPa (<span style="color:#d62728;">{adj_txt}cm</span>) | AIモデル稼働中
   </div>
 </div>
</div>
""", unsafe_allow_html=True)

c1, c2 = st.columns([1,1])
if c1.button("< 前5日"): st.session_state['view_date'] -= datetime.timedelta(days=5)
if c2.button("次5日 >"): st.session_state['view_date'] += datetime.timedelta(days=5)

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
            safe_windows.append({"日付": s.strftime('%m/%d(%a)'), "開始": s.strftime("%H:%M"), "終了": e.strftime("%H:%M"), "時間": f"{h}:{m:02}", "gl": f"Work\n{h}:{m:02}", "mt": min_t, "ml": min_l})

fig, ax = plt.subplots(figsize=(10, 5))
all_known_dates = list(model.raw_data.keys())
if all_known_dates:
    max_known_val = max([datetime.datetime.strptime(d, "%Y-%m-%d").date() for d in all_known_dates])
    teacher_end_dt = datetime.datetime.combine(max_known_val, datetime.time(23,59,59))
else:
    teacher_end_dt = datetime.datetime(2000,1,1)

ax.plot(df['time'], df['level'], '#0066cc', lw=1.5, ls='--', label="AI Forecast", zorder=1)
df_solid = df[df['time'] <= teacher_end_dt]
if not df_solid.empty:
    ax.plot(df_solid['time'], df_solid['level'], '#0066cc', lw=2, label="Actual Data", zorder=2)

if df['time'].iloc[0] <= teacher_end_dt <= df['time'].iloc[-1]:
    ax.axvline(teacher_end_dt, color='gray', linestyle=':', alpha=0.7)
    y_max = df['level'].max()
    ax.text(teacher_end_dt, y_max + 10, " <- Data | Forecast ->", color='gray', fontsize=9, ha='center')

ax.axhline(target_cm, c='orange', ls='--', lw=1.5, label='Limit')
ax.fill_between(df['time'], df['level'], target_cm, where=df['is_safe'], color='#ffcc00', alpha=0.4)

gs, ge = df['time'].iloc[0], df['time'].iloc[-1]
if gs <= curr_now <= ge:
    ax.scatter(curr_now, curr_lvl, c='gold', edgecolors='black', s=120, zorder=10, label="Now")

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
