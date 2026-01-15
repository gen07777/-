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
STANDARD_PRESSURE = 1013

# ==========================================
# 2. 内蔵データ (1/15 - 2/14) - 正確なデータ
# ==========================================
MANUAL_TIDE_DATA = {
    "2026-01-15": [("01:00", 54, "L"), ("08:19", 287, "H"), ("14:10", 163, "L"), ("19:19", 251, "H")],
    "2026-01-16": [("02:00", 37, "L"), ("09:00", 309, "H"), ("15:00", 149, "L"), ("20:19", 260, "H")],
    "2026-01-17": [("02:59", 20, "L"), ("09:50", 327, "H"), ("15:50", 133, "L"), ("21:00", 272, "H")],
    "2026-01-18": [("03:39", 7, "L"), ("10:29", 340, "H"), ("16:29", 117, "L"), ("21:59", 284, "H")],
    "2026-01-19": [("04:19", 0, "L"), ("11:00", 348, "H"), ("17:00", 102, "L"), ("22:39", 293, "H")],
    "2026-01-20": [("04:59", 0, "L"), ("11:39", 350, "H"), ("17:39", 90, "L"), ("23:19", 299, "H")],
    "2026-01-21": [("05:30", 8, "L"), ("12:00", 346, "H"), ("18:10", 80, "L")],
    "2026-01-22": [("00:00", 299, "H"), ("06:09", 23, "L"), ("12:39", 337, "H"), ("18:49", 73, "L")],
    "2026-01-23": [("00:39", 295, "H"), ("06:49", 44, "L"), ("13:09", 325, "H"), ("19:20", 70, "L")],
    "2026-01-24": [("01:20", 285, "H"), ("07:20", 71, "L"), ("13:40", 309, "H"), ("20:00", 70, "L")],
    "2026-01-25": [("02:19", 271, "H"), ("08:00", 102, "L"), ("14:19", 290, "H"), ("20:59", 73, "L")],
    "2026-01-26": [("03:19", 256, "H"), ("08:59", 134, "L"), ("14:59", 271, "H"), ("21:49", 76, "L")],
    "2026-01-27": [("04:39", 246, "H"), ("10:00", 163, "L"), ("15:59", 252, "H"), ("23:00", 76, "L")],
    "2026-01-28": [("06:19", 251, "H"), ("11:59", 178, "L"), ("17:00", 239, "H")],
    "2026-01-29": [("00:19", 68, "L"), ("07:40", 269, "H"), ("13:30", 173, "L"), ("18:30", 237, "H")],
    "2026-01-30": [("01:29", 52, "L"), ("08:40", 293, "H"), ("14:39", 156, "L"), ("19:40", 246, "H")],
    "2026-01-31": [("02:20", 34, "L"), ("09:20", 314, "H"), ("15:20", 136, "L"), ("20:40", 262, "H")],
    "2026-02-01": [("03:10", 17, "L"), ("10:00", 331, "H"), ("16:00", 115, "L"), ("21:29", 279, "H")],
    "2026-02-02": [("03:59", 6, "L"), ("10:39", 342, "H"), ("16:39", 96, "L"), ("22:10", 295, "H")],
    "2026-02-03": [("04:30", 1, "L"), ("11:00", 348, "H"), ("17:09", 79, "L"), ("22:59", 306, "H")],
    "2026-02-04": [("05:00", 4, "L"), ("11:39", 347, "H"), ("17:40", 66, "L"), ("23:30", 311, "H")],
    "2026-02-05": [("05:40", 15, "L"), ("12:00", 341, "H"), ("18:10", 57, "L")],
    "2026-02-06": [("00:09", 310, "H"), ("06:19", 34, "L"), ("12:39", 331, "H"), ("18:49", 52, "L")],
    "2026-02-07": [("00:49", 302, "H"), ("06:59", 58, "L"), ("13:00", 316, "H"), ("19:20", 53, "L")],
    "2026-02-08": [("01:30", 288, "H"), ("07:29", 88, "L"), ("13:39", 298, "H"), ("20:00", 58, "L")],
    "2026-02-09": [("02:20", 270, "H"), ("08:10", 121, "L"), ("14:10", 278, "H"), ("20:59", 67, "L")],
    "2026-02-10": [("03:30", 252, "H"), ("09:00", 153, "L"), ("14:59", 256, "H"), ("21:59", 76, "L")],
    "2026-02-11": [("05:00", 244, "H"), ("10:39", 178, "L"), ("15:59", 236, "H"), ("23:19", 78, "L")],
    "2026-02-12": [("06:59", 254, "H"), ("12:40", 181, "L"), ("17:39", 226, "H")],
    "2026-02-13": [("00:40", 69, "L"), ("08:00", 277, "H"), ("14:09", 163, "L"), ("19:00", 233, "H")],
    "2026-02-14": [("01:59", 51, "L"), ("08:59", 300, "H"), ("14:59", 140, "L"), ("20:19", 252, "H")]
}

# ==========================================
# 3. スタイル & フォント設定
# ==========================================
st.markdown("""
<style>
    .block-container { padding-top: 1rem; padding-bottom: 3rem; }
    h5 { margin-bottom: 0px; }
    /* スマホ対策 */
    @media (max-width: 640px) {
        div[data-testid="stHorizontalBlock"] {
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            gap: 8px !important;
            padding-right: 0px !important;
        }
        div[data-testid="column"] {
            width: calc(50% - 4px) !important;
            flex: 0 0 calc(50% - 4px) !important;
            min-width: 0 !important;
        }
        div.stButton > button {
            width: 100% !important;
            font-size: 0.9rem !important;
            padding: 0px !important;
            height: 2.8rem !important;
            white-space: nowrap !important;
            margin: 0px !important;
        }
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
# 4. データ処理ロジック
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
    """気象庁から年間データを取得"""
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

def get_moon_age(date_obj):
    base = datetime.date(2000, 1, 6)
    return ((date_obj - base).days) % 29.53059

def get_tide_name(moon_age):
    m = int(moon_age)
    if m >= 30: m -= 30
    if m >= 28 or m <= 2: return "大潮"
    if 13 <= m <= 17: return "大潮"
    if 3 <= m <= 5: return "中潮"
    if 18 <= m <= 20: return "中潮"
    if 6 <= m <= 9: return "小潮"
    if 21 <= m <= 24: return "小潮"
    if 10 <= m <= 12: return "長潮"
    if m == 25: return "長潮"
    if m == 13 or 26 <= m <= 27: return "若潮"
    return "中潮"

class OnishiTideModel:
    def __init__(self, pressure_hpa, year, manual_input=""):
        # 1. 気象庁データ取得
        self.jma_map = fetch_jma_data_map(year)
        # 2. 気圧補正
        self.pressure_correction = int(STANDARD_PRESSURE - pressure_hpa)
        # 3. 手動入力データの解析
        self.user_data = self.parse_user_input(manual_input)

    def parse_user_input(self, text):
        """ユーザー入力(CSV形式等)を解析して辞書にする"""
        data = {}
        if not text: return data
        lines = text.splitlines()
        for line in lines:
            try:
                parts = line.split()
                if len(parts) >= 3:
                    d_str = parts[0]
                    t_str = parts[1]
                    lvl = int(parts[2])
                    if d_str not in data: data[d_str] = []
                    ptype = "H" if lvl > 150 else "L" 
                    data[d_str].append((t_str, lvl, ptype))
            except:
                pass
        return data
    
    def get_jma_range_text(self):
        """気象庁データの受信範囲を返す"""
        if not self.jma_map:
            return None
        dates = sorted(self.jma_map.keys())
        start = dates[0]
        end = dates[-1]
        return f"{start} ～ {end}"

    def generate_daily_curve(self, date_str):
        times = []
        levels = []
        base_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        
        # A. ピーク情報 (ユーザー入力 -> 内蔵データ)
        peaks = []
        if date_str in self.user_data:
            peaks = self.user_data[date_str]
        elif date_str in MANUAL_TIDE_DATA:
            peaks = MANUAL_TIDE_DATA[date_str]
            
        if peaks:
            for p_time, p_level, _ in peaks:
                h, m = map(int, p_time.split(":"))
                dt = base_date.replace(hour=h, minute=m)
                levels.append(p_level + self.pressure_correction)
                times.append(dt)
            return times, levels

        # B. 気象庁データ (毎時)
        if date_str in self.jma_map:
            hourly = self.jma_map[date_str]
            for h, val in enumerate(hourly):
                dt = base_date.replace(hour=h, minute=0)
                levels.append(val + self.pressure_correction)
                times.append(dt)
            return times, levels
            
        return None

    def get_dataframe(self, start_date, days=5):
        # 前日～翌日まで取得
        calc_start = start_date - datetime.timedelta(days=1)
        calc_end = start_date + datetime.timedelta(days=days+1)
        
        curr = calc_start
        points_t = []
        points_l = []
        
        while curr <= calc_end:
            d_str = curr.strftime("%Y-%m-%d")
            res = self.generate_daily_curve(d_str)
            if res:
                ts, ls = res
                points_t.extend(ts)
                points_l.extend(ls)
            curr += datetime.timedelta(days=1)
            
        if not points_t: return pd.DataFrame()

        # Cos補間
        fine_times = []
        fine_levels = []
        
        for i in range(len(points_t) - 1):
            t1, t2 = points_t[i], points_t[i+1]
            l1, l2 = points_l[i], points_l[i+1]
            diff_min = int((t2 - t1).total_seconds() / 60)
            if diff_min <= 0: continue
            
            for m in range(diff_min):
                t_cur = t1 + datetime.timedelta(minutes=m)
                ratio = m / diff_min
                mu2 = (1 - math.cos(ratio * math.pi)) / 2
                val = l1 * (1 - mu2) + l2 * mu2
                fine_times.append(t_cur)
                fine_levels.append(val)
                
        df = pd.DataFrame({"time": fine_times, "level": fine_levels})
        
        start_dt = datetime.datetime.combine(start_date, datetime.time(0,0))
        end_dt = start_dt + datetime.timedelta(days=days)
        mask = (df['time'] >= start_dt) & (df['time'] < end_dt)
        return df.loc[mask].reset_index(drop=True)

    def get_current_level(self, df):
        now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
        now_naive = now_jst.replace(tzinfo=None)
        if df.empty: return now_naive, 0
        idx = (df['time'] - now_naive).abs().idxmin()
        return now_naive, df.loc[idx, 'level']

# ==========================================
# 5. UI表示・実行部
# ==========================================
if 'view_date' not in st.session_state:
    now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    if now_jst.year != 2026:
        st.session_state['view_date'] = datetime.date(2026, 1, 15)
    else:
        st.session_state['view_date'] = now_jst.date()

view_date = st.session_state['view_date']
st.markdown("<h5 style='margin-bottom:5px;'>⚓ 大西港 潮汐・作業予報</h5>", unsafe_allow_html=True)

# サイドバー設定
with st.sidebar:
    st.header("⚙️ 設定")
    current_pressure = get_current_pressure()
    
    # ------------------------------------
    # 気象庁データの受信状況表示エリア
    # ------------------------------------
    # ここでモデルを仮生成してステータスを確認
    temp_model = OnishiTideModel(pressure_hpa=current_pressure, year=2026)
    jma_range = temp_model.get_jma_range_text()
    
    if jma_range:
        st.success(f"📡 気象庁データ: 受信完了\n期間: {jma_range}")
    else:
        st.warning("📡 気象庁データ: 未受信\n(内蔵データまたは手動入力を使用中)")
    # ------------------------------------

    st.markdown("---")
    st.info(f"気圧: {current_pressure} hPa")
    
    st.markdown("---")
    st.subheader("🛠 データ不足時の対応")
    with st.expander("将来のデータを追加する"):
        st.caption("2/15以降など、データがない場合にここに入力するとグラフに反映されます。")
        st.caption("書式: 2026-02-15 09:00 300 (1行に1つ)")
        manual_input = st.text_area("追加データ入力", height=150)
        
    st.markdown("---")
    target_cm = st.number_input("作業可能潮位 (cm以下)", value=120, step=10)
    start_h, end_h = st.slider("作業時間帯", 0, 24, (7, 23))
    
    st.markdown("---")
    if st.button("基準日 (2026/1/15)"): st.session_state['view_date'] = datetime.date(2026, 1, 15)

# モデル初期化 (ユーザー入力反映) & データ生成
model = OnishiTideModel(pressure_hpa=current_pressure, year=2026, manual_input=manual_input)
df = model.get_dataframe(view_date, days=5)

if df.empty:
    st.error(f"⚠️ {view_date.strftime('%m/%d')} 付近のデータがありません。サイドバーから追加するか、日付を戻してください。")
    curr_time, curr_lvl = datetime.datetime.now(), 0
else:
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
    気圧:{int(current_pressure)}hPa (<span style="color:#d62728;">{adj_txt}cm</span>)
   </div>
 </div>
</div>
""", unsafe_allow_html=True)

# ナビゲーション
c1, c2 = st.columns([1,1])
if c1.button("< 前5日"): st.session_state['view_date'] -= datetime.timedelta(days=5)
if c2.button("次5日 >"): st.session_state['view_date'] += datetime.timedelta(days=5)

# グラフとリストの描画
if not df.empty:
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

    # ピーク抽出(表示用)
    peaks_to_plot = []
    check_date = view_date
    for _ in range(5):
        d_str = check_date.strftime("%Y-%m-%d")
        peaks_src = []
        if d_str in model.user_data: 
            peaks_src = model.user_data[d_str]
        elif d_str in MANUAL_TIDE_DATA: 
            peaks_src = MANUAL_TIDE_DATA[d_str]
        
        for pt, pl, ptype in peaks_src:
             dt_peak = datetime.datetime.strptime(f"{d_str} {pt}", "%Y-%m-%d %H:%M")
             peaks_to_plot.append({
                 "time": dt_peak, 
                 "level": pl + model.pressure_correction, 
                 "type": ptype
             })
        check_date += datetime.timedelta(days=1)
    
    df_peaks = pd.DataFrame(peaks_to_plot)

    # グラフ描画
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df['time'], df['level'], '#0066cc', lw=2, zorder=2, label="Level")
    ax.axhline(target_cm, c='orange', ls='--', lw=1.5, label='Limit')
    ax.fill_between(df['time'], df['level'], target_cm, where=df['is_safe'], color='#ffcc00', alpha=0.4)

    gs, ge = df['time'].iloc[0], df['time'].iloc[-1]
    if gs <= curr_time <= ge:
        ax.scatter(curr_time, curr_lvl, c='gold', edgecolors='black', s=100, zorder=10)

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

    # リスト
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
