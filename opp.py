import streamlit as st
import datetime
import math
import calendar
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import re
import requests

# ---------------------------------------------------------
# アプリ設定
# ---------------------------------------------------------
st.set_page_config(layout="wide")

# ---------------------------------------------------------
# 外部データ取得ロジック (30分キャッシュ)
# ---------------------------------------------------------
@st.cache_data(ttl=1800) # 1800秒 = 30分間は再実行せず、前回の結果を返す
def fetch_realtime_offset():
    """
    気象庁の潮位実測データ(竹原)を取得し、予測値とのズレ(偏差)を計算する試み。
    失敗した場合は None を返す安全設計。
    """
    try:
        # 気象庁: 竹原の潮位データURL (JSON/TXT形式の公開データがあればそこを狙うが、
        # ここではHTMLアクセスの概念コードとします。実際にはスクレイピング対策で弾かれる可能性大)
        
        # ※注: Streamlit CloudのIPは海外扱いのため、気象庁HPには接続できないことが多いです。
        # 接続できたと仮定して、偏差が「+10cm」だったとするダミー数値を返します。
        # 本気で実装する場合、ここに BeautifulSoup などの解析コードを書きます。
        
        # url = "https://www.data.jma.go.jp/..."
        # response = requests.get(url, timeout=3)
        # response.raise_for_status()
        
        # ...データ解析処理...
        
        # テスト用に意図的に例外(失敗)を発生させて、安全装置の動作を確認させます
        # 実装時はここを実際の取得コードに変えます
        return None 

    except Exception:
        return None

# ---------------------------------------------------------
# 計算ロジック
# ---------------------------------------------------------
class OnishiTideCalculator:
    def __init__(self):
        self.CONSTITUENTS = {
            'M2': {'amp': 132.0, 'phase': 206.5, 'speed': 28.9841042},
            'S2': {'amp': 48.0,  'phase': 242.6, 'speed': 30.0000000},
            'K1': {'amp': 37.0,  'phase': 191.0, 'speed': 15.0410686},
            'O1': {'amp': 30.0,  'phase': 172.6, 'speed': 13.9430356}
        }
        self.MSL = 180.0 
        self.TIME_OFFSET_MINUTES = 10 
        self.CORRECTION_RATIO = 0.98

    def _calculate_astronomical_tide(self, target_datetime):
        base_date = datetime.datetime(target_datetime.year, 1, 1)
        delta_hours = (target_datetime - base_date).total_seconds() / 3600.0
        tide_height = self.MSL
        for name, const in self.CONSTITUENTS.items():
            theta = math.radians(const['speed'] * delta_hours - const['phase'])
            tide_height += const['amp'] * math.cos(theta)
        return tide_height

    def get_period_data(self, year, month, start_day, end_day, interval_minutes=5, pressure=1013, manual_offset=0):
        detailed_data = []
        start_dt = datetime.datetime(year, month, start_day)
        last_day_of_month = calendar.monthrange(year, month)[1]
        if end_day > last_day_of_month: end_day = last_day_of_month
        end_dt = datetime.datetime(year, month, end_day, 23, 55)
        
        # 気圧補正 (1hPa = 1cm)
        meteo_correction = (1013 - pressure) * 1.0
        
        # 総補正量
        total_offset = meteo_correction + manual_offset

        current_dt = start_dt
        while current_dt <= end_dt:
            calc_time_offset = current_dt - datetime.timedelta(minutes=self.TIME_OFFSET_MINUTES)
            base_level = self._calculate_astronomical_tide(calc_time_offset)
            astro_level = base_level * self.CORRECTION_RATIO
            actual_level = astro_level + total_offset
            
            detailed_data.append({
                "raw_time": current_dt, 
                "Astro_Level": astro_level,
                "Level_cm": actual_level
            })
            current_dt += datetime.timedelta(minutes=interval_minutes)
        return detailed_data, total_offset

# ---------------------------------------------------------
# メイン画面構成
# ---------------------------------------------------------
st.title("大西港 潮位ビジュアライザー (Pro)")
st.caption("データ参照元: 広島港基準+大西補正 / 30分キャッシュ機能搭載")

# --- 設定エリア ---
st.markdown("### 1. 期間と基準の設定")
col1, col2 = st.columns(2)
with col1:
    year_sel = st.number_input("対象年", value=datetime.date.today().year)
    period_options = []
    for m in range(1, 13):
        period_options.append(f"{m}月前半 (1日-15日)")
        period_options.append(f"{m}月後半 (16日-末日)")
    current_month = datetime.date.today().month
    default_index = (current_month - 1) * 2
    selected_period = st.selectbox("表示期間", period_options, index=default_index)

with col2:
    target_cm = st.number_input("基準潮位 (cm)", value=120, step=10, help="この高さより低い時間を探します")
    start_hour, end_hour = st.slider("活動時間 (この時間内のみ抽出)", 0, 24, (7, 23), format="%d時")

st.divider()

# --- 自動取得 & 補正エリア ---
st.markdown("### 2. 気象・実測補正")

# バックグラウンドでデータを取ってみる (30分に1回)
auto_offset = fetch_realtime_offset()

col3, col4 = st.columns(2)

with col3:
    target_pressure = st.number_input("当日の予想気圧 (hPa)", value=1013, step=1)

with col4:
    # もし自動取得できていれば、その値をデフォルトにする
    default_manual = 0
    help_msg = "阿賀や竹原の実測値が予測より高い場合に数値を入力。"
    
    if auto_offset is not None:
        default_manual = int(auto_offset)
        st.success(f"📡 竹原の実測データを受信しました！ 偏差: {auto_offset:+d}cm")
        help_msg = "自動取得した偏差が入力されています。必要に応じて修正してください。"
    else:
        st.caption("⚠️ 実測データの自動取得に失敗しました (手動入力を推奨)")
    
    manual_offset = st.number_input(
        "実測偏差の手動補正 (cm)", 
        value=default_manual, step=5,
        help=help_msg
    )

st.markdown("""
<div style='font-size: 0.8em; color: gray;'>
参考: <a href="https://www.data.jma.go.jp/gmd/kaiyou/db/tide/gen_hour/gen_hour.php" target="_blank">気象庁 潮位実測(竹原)</a>
</div>
""", unsafe_allow_html=True)

# --- データ生成 ---
try:
    month_str = selected_period.split('月')[0]
    month_sel = int(month_str)
    is_first_half = "前半" in selected_period
except:
    month_sel = 1
    is_first_half = True

last_day = calendar.monthrange(year_sel, month_sel)[1]
if is_first_half:
    start_d, end_d = 1, 15
else:
    start_d, end_d = 16, last_day

calculator = OnishiTideCalculator()
data, total_correction = calculator.get_period_data(
    year_sel, month_sel, start_d, end_d, 
    pressure=target_pressure, manual_offset=manual_offset
)
df = pd.DataFrame(data)

if df.empty:
    st.error("データがありません。")
else:
    # ---------------------------------------------------------
    # グラフ描画
    # ---------------------------------------------------------
    st.subheader(f"潮位グラフ: {selected_period}")
    
    if total_correction != 0:
        st.info(f"💡 気圧・手動補正により、潮位を **{total_correction:+.1f}cm** 調整しています。")

    fig, ax = plt.subplots(figsize=(15, 10))

    # 天文潮位(点線) & 補正後潮位(実線)
    if total_correction != 0:
        ax.plot(df['raw_time'], df['Astro_Level'], color='gray', linestyle=':', linewidth=1, alpha=0.5, label="Astro (No Correction)")
    ax.plot(df['raw_time'], df['Level_cm'], color='#1f77b4', linewidth=1.5, alpha=0.9, label="Predicted Level")

    # 基準線
    ax.axhline(y=target_cm, color='black', linestyle='--', linewidth=1, label=f"Target ({target_cm}cm)")

    # 塗りつぶし
    hours = df['raw_time'].dt.hour
    is_time_ok = (hours >= start_hour) & (hours < end_hour)
    is_level_ok = (df['Level_cm'] <= target_cm)
    
    ax.fill_between(df['raw_time'], df['Level_cm'], target_cm, 
                    where=(is_level_ok & is_time_ok), 
                    color='red', alpha=0.3, interpolate=True)

    # ラベル表示
    df['in_target'] = is_level_ok & is_time_ok
    df['change'] = df['in_target'].ne(df['in_target'].shift()).cumsum()
    groups = df[df['in_target']].groupby('change')
    
    label_offset_counter = 0

    for _, group in groups:
        start_t = group['raw_time'].iloc[0]
        end_t = group['raw_time'].iloc[-1]
        
        duration = end_t - start_t
        total_minutes = int(duration.total_seconds() / 60)
        
        if total_minutes < 10: continue

        stagger = (label_offset_counter % 2) * 20
        label_offset_counter += 1
        font_size = 8
        
        # Start (青)
        y_pos_start = target_cm + 15 + stagger
        ax.annotate(
            start_t.strftime("%H:%M"), 
            xy=(start_t, target_cm),
            xytext=(0, y_pos_start - target_cm),
            textcoords='offset points', ha='center', va='bottom', 
            fontsize=font_size, color='blue', fontweight='bold',
            arrowprops=dict(arrowstyle='-', color='blue', linewidth=0.5, linestyle=':')
        )

        # End (緑)
        y_pos_end = target_cm - 15 - stagger
        ax.annotate(
            end_t.strftime("%H:%M"), 
            xy=(end_t, target_cm), 
            xytext=(0, y_pos_end - target_cm), 
            textcoords='offset points', ha='center', va='top', 
            fontsize=font_size, color='green', fontweight='bold',
            arrowprops=dict(arrowstyle='-', color='green', linewidth=0.5, linestyle=':')
        )

        # Duration (赤)
        hours_dur = total_minutes // 60
        mins_dur = total_minutes % 60
        dur_str = f"{hours_dur}h{mins_dur}m"
        mid_time = start_t + (duration / 2)
        y_pos_dur = y_pos_end - 30 
        
        ax.text(mid_time, y_pos_dur, dur_str, 
                ha='center', va='top', 
                fontsize=font_size, fontweight='bold', color='#cc0000',
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.6))

    ax.set_ylabel("Level (cm)")
    ax.grid(True, which='both', linestyle='--', alpha=0.3)
    ax.legend(loc='upper right')
    
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d'))
    ax.set_xlim(df['raw_time'].iloc[0], df['raw_time'].iloc[-1])
    
    st.pyplot(fig)
