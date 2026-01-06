import streamlit as st
import datetime
import math
import calendar
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ---------------------------------------------------------
# 計算ロジック
# ---------------------------------------------------------
class OnishiTideCalculator:
    def __init__(self):
        self.CORRECTION_RATIO = 1.0
        self.TIME_OFFSET_MINUTES = 0
        self.MSL = 250.0 
        self.CONSTITUENTS = {
            'M2': {'amp': 130.0, 'phase': 200.0, 'speed': 28.9841042},
            'S2': {'amp': 50.0,  'phase': 230.0, 'speed': 30.0000000},
            'K1': {'amp': 35.0,  'phase': 180.0, 'speed': 15.0410686},
            'O1': {'amp': 30.0,  'phase': 160.0, 'speed': 13.9430356}
        }

    def _calculate_astronomical_tide(self, target_datetime):
        base_date = datetime.datetime(target_datetime.year, 1, 1)
        delta_hours = (target_datetime - base_date).total_seconds() / 3600.0
        tide_height = self.MSL
        for name, const in self.CONSTITUENTS.items():
            theta = math.radians(const['speed'] * delta_hours - const['phase'])
            tide_height += const['amp'] * math.cos(theta)
        return tide_height

    def get_period_data(self, year, month, start_day, end_day, interval_minutes=5):
        """指定期間のデータを生成 (精度を上げるため5分刻み)"""
        detailed_data = []
        
        start_dt = datetime.datetime(year, month, start_day)
        if end_day == calendar.monthrange(year, month)[1]:
            end_dt = datetime.datetime(year, month, end_day, 23, 55)
        else:
            end_dt = datetime.datetime(year, month, end_day + 1) - datetime.timedelta(minutes=interval_minutes)

        current_dt = start_dt
        while current_dt <= end_dt:
            calc_time_offset = current_dt - datetime.timedelta(minutes=self.TIME_OFFSET_MINUTES)
            base_level = self._calculate_astronomical_tide(calc_time_offset)
            onishi_level = base_level * self.CORRECTION_RATIO
            
            detailed_data.append({
                "raw_time": current_dt,
                "Level_cm": onishi_level
            })
            current_dt += datetime.timedelta(minutes=interval_minutes)
            
        return detailed_data

# ---------------------------------------------------------
# アプリ設定
# ---------------------------------------------------------
st.set_page_config(layout="wide")
st.title("大西港 潮位ビジュアライザー")

# --- サイドバー設定 ---
with st.sidebar:
    st.header("設定")
    target_cm = st.number_input("基準潮位 (cm)", value=150, step=10, help="この高さより低くなる時間を探します")
    
    st.subheader("活動時間フィルタ")
    # 時間範囲選択 (初期値 7:00 - 23:00)
    start_hour, end_hour = st.slider(
        "表示する時間帯:",
        0, 24, (7, 23),
        format="%d時"
    )

# --- メイン操作エリア ---
col1, col2, col3 = st.columns([1, 1, 3])
with col1:
    year_sel = st.number_input("年", value=datetime.date.today().year)
with col2:
    month_sel = st.number_input("月", value=datetime.date.today().month, min_value=1, max_value=12)

# 期間計算
last_day = calendar.monthrange(year_sel, month_sel)[1]

# 前半・後半ボタンの作成
with col3:
    period_label = st.radio(
        "表示期間", # ラベルは隠せないのでシンプルに
        [f"{month_sel}月前半 (1日-15日)", f"{month_sel}月後半 (16日-{last_day}日)"],
        horizontal=True,
        label_visibility="collapsed" # ラベルを隠す設定
    )

# 選択に基づき日付範囲を決定
if "前半" in period_label:
    start_d, end_d = 1, 15
else:
    start_d, end_d = 16, last_day

# データ計算
calculator = OnishiTideCalculator()
data = calculator.get_period_data(year_sel, month_sel, start_d, end_d)
df = pd.DataFrame(data)

# ---------------------------------------------------------
# グラフ描画
# ---------------------------------------------------------
st.subheader(f"潮位グラフ: {period_label}")

# グラフ作成
fig, ax = plt.subplots(figsize=(15, 8)) # 少し縦に大きく

# 1. 潮位線
ax.plot(df['raw_time'], df['Level_cm'], color='#1f77b4', linewidth=1.5, alpha=0.7)

# 2. ターゲットライン
ax.axhline(y=target_cm, color='black', linestyle='--', linewidth=1)

# 3. 塗りつぶし & 時間検出ロジック
# 条件: 指定潮位以下 かつ 指定時間内
hours = df['raw_time'].dt.hour
# end_hourが24の場合は23:59まで含むため < 24 とするなどの調整
# sliderの23は「23時台まで」つまり 23:59 までを含むと解釈して実装
time_condition = (hours >= start_hour) & (hours <= end_hour if end_hour < 24 else 24)
level_condition = (df['Level_cm'] <= target_cm)

# 赤く塗りつぶす
ax.fill_between(df['raw_time'], df['Level_cm'], target_cm, 
                where=(level_condition & time_condition), 
                color='red', alpha=0.3, interpolate=True)

# 4. 「開始」「終了」「継続時間」のラベル表示
# 連続した区間（塊）を見つけて処理する
in_zone = False
zone_start_time = None
label_counter = 0 # 重なり防止用のカウンタ

# データを走査して区間を検出
# iterrowsは遅いので単純ループで処理
times = df['raw_time'].tolist()
levels = df['Level_cm'].tolist()
n_points = len(times)

for i in range(n_points):
    t = times[i]
    lvl = levels[i]
    h = t.hour
    
    # フィルタ条件チェック
    is_target = (lvl <= target_cm) and (start_hour <= h <= (end_hour if end_hour < 24 else 24))
    
    if is_target and not in_zone:
        # 区間開始 (Start)
        in_zone = True
        zone_start_time = t
        
        # 開始時間のラベル (引き出し線)
        # カウンタを使って高さを変える (30, 60, 90...)
        offset = 30 + (label_counter % 3) * 25
        
        time_str = t.strftime("%H:%M")
        ax.annotate(
            time_str, xy=(t, target_cm), xytext=(-10, offset),
            textcoords='offset points', ha='center', va='bottom', fontsize=8,
            color='blue', arrowprops=dict(arrowstyle='->', color='blue', linewidth=0.5)
        )
        
    elif not is_target and in_zone:
        # 区間終了 (End)
        in_zone = False
        zone_end_time = times[i-1] # ひとつ前のポイントが最後
        
        # 終了時間のラベル
        offset = 30 + (label_counter % 3) * 25 # 開始と同じ高さにする
        time_str = zone_end_time.strftime("%H:%M")
        ax.annotate(
            time_str, xy=(zone_end_time, target_cm), xytext=(10, offset),
            textcoords='offset points', ha='center', va='bottom', fontsize=8,
            color='blue', arrowprops=dict(arrowstyle='->', color='blue', linewidth=0.5)
        )
        
        # ★時間の長さ (Duration) を真ん中に表示★
        duration = zone_end_time - zone_start_time
        total_minutes = int(duration.total_seconds() / 60)
        if total_minutes >= 10: # 10分以上ある場合のみ表示
            hours_dur = total_minutes // 60
            mins_dur = total_minutes % 60
            dur_str = f"{hours_dur}h {mins_dur}m" # 英語表記で文字化け回避
            
            # 区間の真ん中の時間
            mid_time = zone_start_time + (duration / 2)
            
            # グラフの下の方、またはターゲットラインの少し下に表示
            ax.text(mid_time, target_cm - 15, dur_str, 
                    ha='center', va='top', fontsize=9, fontweight='bold', color='#cc0000')
            
        label_counter += 1

# グラフ装飾
ax.set_ylabel("Level (cm)")
ax.grid(True, which='both', linestyle='--', alpha=0.3)
ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
ax.xaxis.set_major_formatter(mdates.DateFormatter('%d')) # 日付のみ
plt.xlim(df['raw_time'].min(), df['raw_time'].max())

st.pyplot(fig)

# リスト表示 (詳細データ)
with st.expander("詳細リストを表示"):
    # フィルタ条件に合うデータを抽出して表示
    filtered_df = df[level_condition & time_condition].copy()
    if not filtered_df.empty:
        filtered_df['Date'] = filtered_df['raw_time'].dt.strftime('%m/%d')
        filtered_df['Time'] = filtered_df['raw_time'].dt.strftime('%H:%M')
        st.dataframe(filtered_df[['Date', 'Time', 'Level_cm']], use_container_width=True)
    else:
        st.write("条件に合う時間帯はありません。")
