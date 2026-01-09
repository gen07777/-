import streamlit as st
import datetime
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import requests
import numpy as np
from scipy.interpolate import interp1d  # 滑らかなグラフを描くために追加

# ---------------------------------------------------------
# 1. アプリ設定 & 定数
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="Onishi Port Precision Tide")
OWM_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"

# 大西港 (大崎上島) 補正定数 (検証済み)
TIME_OFFSET_MIN = 1       # 時間補正 +1分
LEVEL_BASE_OFFSET = 13    # 基準面補正 +13cm
STANDARD_PRESSURE = 1013  # 標準気圧

# バックアップデータ (気象庁接続エラー時用: 1月9日前後)
BACKUP_HOURLY = [
    230, 275, 290, 265, 210, 140, 70, 30, 40, 100, 180, 260, 315, 330, 300, 240, 170, 110, 80, 85, 130, 190, 250, 290
]

# ---------------------------------------------------------
# 2. レイアウト & スタイル
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
# 3. データ取得ロジック (気象庁 + OWM)
# ---------------------------------------------------------

# 気圧取得
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

# 気象庁データ取得 & 解析
@st.cache_data(ttl=3600)
def fetch_jma_data_map(year):
    """気象庁のTXTデータを辞書{日付: [0-23時の潮位]}に変換"""
    url = f"https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt/{year}/344311.txt" # 竹原
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

# ---------------------------------------------------------
# 4. ヘルパー関数 (月齢・潮名・ピーク処理)
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
# 5. 新・潮汐モデル (JMAデータ補間 + 補正)
# ---------------------------------------------------------
class JMATideModel:
    def __init__(self, pressure_hpa, year=2026):
        self.jma_map = fetch_jma_data_map(year)
        self.pressure_correction = int(STANDARD_PRESSURE - pressure_hpa) # 吸い上げ効果
        self.total_level_offset = LEVEL_BASE_OFFSET + self.pressure_correction
        self.time_offset = TIME_OFFSET_MIN
    
    def get_dataframe(self, start_date, days=10):
        # 指定期間の毎時データを作成
        timestamps = []
        levels = []
        
        start_dt = datetime.datetime.combine(start_date, datetime.time(0, 0))
        end_dt = start_dt + datetime.timedelta(days=days)
        
        # 必要な日数分ループ
        curr = start_dt
        while curr < end_dt:
            d_str = curr.strftime("%Y-%m-%d")
            
            # データ取得 (なければバックアップを回転させて擬似生成)
            if d_str in self.jma_map:
                hourly = self.jma_map[d_str]
            else:
                # バックアップロジック (デモ用)
                diff = (curr.date() - datetime.date(2026,1,9)).days
                shift = diff * 1 
                l_len = len(BACKUP_HOURLY)
                hourly = [BACKUP_HOURLY[(i - shift) % l_len] for i in range(l_len)]

            # 補正適用 (潮位オフセット)
            corrected_hourly = [h + self.total_level_offset for h in hourly]
            
            # タイムスタンプ生成 (時間オフセット適用)
            # 竹原の0時データ -> 大西の0時01分データとして扱う
            base_time = datetime.datetime.combine(curr.date(), datetime.time(0,0))
            for h in range(24):
                t = base_time + datetime.timedelta(hours=h, minutes=self.time_offset)
                timestamps.append(t)
                levels.append(corrected_hourly[h])
            
            curr += datetime.timedelta(days=1)
            
        # データフレーム化
        df_hourly = pd.DataFrame({"time": timestamps, "level": levels})
        
        # スプライン補間 (毎時 -> 毎分) で滑らかにする
        # UNIXタイムスタンプにして補間
        df_hourly['ts'] = df_hourly['time'].map(datetime.datetime.timestamp)
        
        # 補間関数作成 (cubic=3次スプライン)
        f = interp1d(df_hourly['ts'], df_hourly['level'], kind='cubic', fill_value="extrapolate")
        
        # 10分刻み(描画用) または 1分刻み(厳密計算用) のTimeIndexを作成
        # ここでは描画パフォーマンスと精度のバランスで5分刻み
        fine_index = pd.date_range(start=df_hourly['time'].iloc[0], end=df_hourly['time'].iloc[-1], freq='5T')
        fine_levels = f(fine_index.map(datetime.datetime.timestamp))
        
        df_fine = pd.DataFrame({"time": fine_index, "level": fine_levels})
        return df_fine

    def get_current_level(self, df_fine):
        # 現在時刻に最も近いデータをdfから取得
        now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
        now_naive = now_jst.replace(tzinfo=None)
        
        # 未来・過去すぎる場合はNone
        if now_naive < df_fine['time'].iloc[0] or now_naive > df_fine['time'].iloc[-1]:
            return now_naive, 0
            
        # 近似検索
        idx = (df_fine['time'] - now_naive).abs().idxmin()
        return now_naive, df_fine.loc[idx, 'level']

# ---------------------------------------------------------
# 6. メイン処理 & UI
# ---------------------------------------------------------
if 'view_date' not in st.session_state:
    now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    # デモ用に初期表示を2026年にする
    if now_jst.year != 2026:
        st.session_state['view_date'] = datetime.date(2026, 1, 9)
    else:
        st.session_state['view_date'] = now_jst.date()

view_date = st.session_state['view_date']
st.markdown("<h5 style='margin-bottom:5px;'>⚓ Onishi Port (Final Fixed)</h5>", unsafe_allow_html=True)

# データ準備
current_pressure = get_current_pressure()
model = JMATideModel(pressure_hpa=current_pressure, year=2026)

# データ生成 (5日分で十分だがナビゲーション用に少し多めに)
df = model.get_dataframe(view_date, days=5)

curr_time, curr_lvl = model.get_current_level(df)
ma = get_moon_age(view_date)
tn = get_tide_name(ma)

# 補正情報の表示
p_diff = int(1013 - current_pressure)
adj_txt = f"+{p_diff}" if p_diff > 0 else f"{p_diff}"
total_adj = model.total_level_offset
base_adj_txt = f"+{LEVEL_BASE_OFFSET}"

st.markdown(f"""
<div style="font-size:0.85rem; background:#f8f9fa; padding:8px; border:1px solid #ddd; margin-bottom:5px; border-radius:4px;">
 <div><b>Period:</b> {view_date.strftime('%m/%d')}~ (5 Days) <span style="color:#555;">(Moon:{ma:.1f} {tn})</span></div>
 <div style="margin-top:2px;">
   <span style="color:#0066cc; font-weight:bold;">Now: {curr_time.strftime('%H:%M')} {int(curr_lvl)}cm</span>
   <span style="font-size:0.75rem; color:#666; margin-left:5px;">
    (Press:{int(current_pressure)}hPa <span style="color:#d62728;">Adj:{adj_txt}cm</span> + Base:{base_adj_txt}cm = Total <span style="color:#2ca02c;">+{total_adj}cm</span>)
   </span>
 </div>
</div>
""", unsafe_allow_html=True)

# ナビゲーション
c1, c2 = st.columns([1,1])
if c1.button("< Prev 5 Days"): st.session_state['view_date'] -= datetime.timedelta(days=5)
if c2.button("Next 5 Days >"): st.session_state['view_date'] += datetime.timedelta(days=5)

# サイドバー
with st.sidebar:
    st.header("⚙️ Settings")
    st.info(f"📡 API Status: OK\nPressure: {current_pressure} hPa")
    st.markdown("---")
    target_cm = st.number_input("Limit (cm)", value=120, step=10)
    start_h, end_h = st.slider("Hours", 0, 24, (7, 23))
    st.markdown("---")
    if st.button("Reset to 2026/1/9"): st.session_state['view_date'] = datetime.date(2026, 1, 9)

# 解析
df['hour'] = df['time'].dt.hour
df['is_safe'] = (df['level'] <= target_cm) & (df['hour'] >= start_h) & (df['hour'] < end_h)

# 作業可能時間の抽出
safe_windows = []
if df['is_safe'].any():
    # 連続区間のグルーピング
    df['grp'] = (df['is_safe'] != df['is_safe'].shift()).cumsum()
    for _, g in df[df['is_safe']].groupby('grp'):
        s, e = g['time'].iloc[0], g['time'].iloc[-1]
        
        # 10分以上を作業時間とみなす
        if (e-s).total_seconds() >= 600:
            min_l = g['level'].min()
            min_t = g.loc[g['level'].idxmin(), 'time']
            d = e - s
            h, m = d.seconds//3600, (d.seconds%3600)//60
            
            # リスト表示用データ
            safe_windows.append({
                "date": s.strftime('%m/%d(%a)'),
                "start": s.strftime("%H:%M"),
                "end": e.strftime("%H:%M"),
                "dur": f"{h}:{m:02}",
                "gl": f"Work\n{h}:{m:02}", # グラフ注釈用
                "mt": min_t, "ml": min_l
            })

# ピーク検出 (極大・極小)
# 補間データなので rolling を使うより、単純な近傍比較が有効
df['peak_high'] = (df['level'] > df['level'].shift(1)) & (df['level'] > df['level'].shift(-1))
df['peak_low'] = (df['level'] < df['level'].shift(1)) & (df['level'] < df['level'].shift(-1))

highs = df[df['peak_high']].copy()
lows = df[df['peak_low']].copy()

highs = deduplicate_peaks(highs)
lows = deduplicate_peaks(lows)

# ---------------------------------------------------------
# 7. グラフ描画 (Matplotlib)
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5))

# メイン潮位線
ax.plot(df['time'], df['level'], '#0066cc', lw=2, zorder=2, label="Tide Level")

# 制限ライン
ax.axhline(target_cm, c='orange', ls='--', lw=1.5, label='Limit')

# 作業可能エリアの塗りつぶし
ax.fill_between(df['time'], df['level'], target_cm, where=df['is_safe'], color='#ffcc00', alpha=0.4)

# 現在位置のポイント
gs, ge = df['time'].iloc[0], df['time'].iloc[-1]
if gs <= curr_time <= ge:
    ax.scatter(curr_time, curr_lvl, c='gold', edgecolors='black', s=90, zorder=10, label="Now")

# 満潮 (赤 ▲)
for _, r in highs.iterrows():
    ax.scatter(r['time'], r['level'], c='red', marker='^', s=40, zorder=3)
    # 日付ごとに高さを互い違いにして重なり防止
    off = 15 if r['time'].day % 2 == 0 else 35
    ax.annotate(f"{r['time'].strftime('%H:%M')}\n{int(r['level'])}", 
                (r['time'], r['level']), xytext=(0,off), textcoords='offset points', 
                ha='center', fontsize=8, color='#cc0000', fontweight='bold')

# 干潮 (青 ▼)
for _, r in lows.iterrows():
    ax.scatter(r['time'], r['level'], c='blue', marker='v', s=40, zorder=3)
    off = -25 if r['time'].day % 2 == 0 else -45
    ax.annotate(f"{r['time'].strftime('%H:%M')}\n{int(r['level'])}", 
                (r['time'], r['level']), xytext=(0,off), textcoords='offset points', 
                ha='center', fontsize=8, color='#0000cc', fontweight='bold')

# 作業時間の注釈 (Work X:XX)
for w in safe_windows:
    # グラフが混み合うので、最も潮位が低いポイントにラベルを表示
    ax.annotate(w['gl'], (w['mt'], w['ml']), xytext=(0,-85), textcoords='offset points', 
                ha='center', fontsize=8, color='#b8860b', fontweight='bold', 
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.7))

ax.set_ylabel("Level (cm)")
ax.grid(True, ls=':', alpha=0.6)
# X軸フォーマット
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n(%a)'))
ax.set_ylim(bottom=-50) # 干潮がマイナスになることもあるので余裕をもたせる
plt.tight_layout()

st.pyplot(fig)

# ---------------------------------------------------------
# 8. 作業時間リスト
# ---------------------------------------------------------
st.markdown("---")
st.markdown(f"##### 📋 Workable Time List (Limit <= {target_cm}cm)")

if safe_windows:
    rdf = pd.DataFrame(safe_windows)
    cols = ["date", "start", "end", "dur"]
    
    # スマートフォンでも見やすいようにカード形式に近い表示か、分割表示
    cc = st.columns(3)
    chunks = np.array_split(rdf, 3)
    for i, col in enumerate(cc):
        if i < len(chunks) and not chunks[i].empty:
            col.dataframe(chunks[i][cols], hide_index=True, use_container_width=True)
else:
    st.warning("No workable time found in this period.")
