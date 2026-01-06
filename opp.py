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

    def get_period_data(self, year, month, start_day, end_day, interval_minutes=10):
        """指定期間（開始日〜終了日）のデータを生成"""
        detailed_data = []
        
        # 開始日時
        start_dt = datetime.datetime(year, month, start_day)
        # 終了日時（翌日の00:00まで含めるため+1日）
        if end_day == calendar.monthrange(year, month)[1]:
            # 月末の場合、翌月の1日を計算すると面倒なので、当日の23:50までにする
            end_dt = datetime.datetime(year, month, end_day, 23, 50)
        else:
            end_dt = datetime.datetime(year, month, end_day + 1)

        current_dt = start_dt
        while current_dt <= end_dt:
            # 補正込みの計算
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
# アプリ画面構成
# ---------------------------------------------------------
st.set_page_config(layout="wide") # 横長画面モードにする
st.title("Tide Visualizer (15-Day View)")
st.caption("Onishi Port")

# --- サイドバー設定 ---
with st.sidebar:
    st.header("Settings")
    
    # 1. 潮位設定
    target_cm = st.number_input("Target Level (cm)", value=150, step=10)
    
    # 2. 時間枠設定 (活動時間)
    st.subheader("Activity Time Filter")
    start_hour, end_hour = st.slider(
        "Show only between:",
        0, 23, (7, 23) # 初期値 7:00 - 23:00
    )
    st.caption(f"Showing tides below {target_cm}cm only between {start_hour}:00 and {end_hour}:00")

# --- メインエリア ---

# 3. 日付・期間選択
col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    year_sel = st.number_input("Year", value=datetime.date.today().year)
with col2:
    month_sel = st.number_input("Month", value=datetime.date.today().month, min_value=1, max_value=12)
with col3:
    # 前半・後半の切り替えスイッチ
    period_type = st.radio("Display Period", ["1st - 15th (First Half)", "16th - End (Second Half)"], horizontal=True)

# 期間の計算
last_day_of_month = calendar.monthrange(year_sel, month_sel)[1]

if "1st" in period_type:
    start_d, end_d = 1, 15
else:
    start_d, end_d = 16, last_day_of_month

# 計算実行
calculator = OnishiTideCalculator()
data = calculator.get_period_data(year_sel, month_sel, start_d, end_d)
df = pd.DataFrame(data)

# ---------------------------------------------------------
# グラフ描画 (Matplotlib)
# ---------------------------------------------------------
st.subheader(f"{year_sel}/{month_sel}  ({start_d} - {end_d})")

# グラフサイズを大きく確保 (15日分なので横長に)
fig, ax = plt.subplots(figsize=(15, 7))

# 1. メインの潮位線 (青)
ax.plot(df['raw_time'], df['Level_cm'], label='Tide Level', color='#1f77b4', linewidth=1.5, alpha=0.8)

# 2. ターゲットライン (黒点線)
ax.axhline(y=target_cm, color='black', linestyle='--', linewidth=1, label=f'Target ({target_cm}cm)')

# 3. 塗りつぶし & フィルタリング
# 条件: (潮位 <= 指定値) AND (指定した時間帯内)
# 時間帯のフィルタを作る
hours = df['raw_time'].dt.hour
time_condition = (hours >= start_hour) & (hours <= end_hour)
level_condition = (df['Level_cm'] <= target_cm)

# 条件に合うところだけ赤く塗る
ax.fill_between(df['raw_time'], df['Level_cm'], target_cm, 
                where=(level_condition & time_condition), 
                color='red', alpha=0.4, interpolate=True, label='Activity Window')

# 4. 引き出し線 (Callout) で時間を表示
# 交差点を検出して、条件に合うものだけラベル付けする

# 前のデータとの比較用シフトデータ
df['prev_level'] = df['Level_cm'].shift(1)
df['prev_time'] = df['raw_time'].shift(1)

# 交差判定 (またいだ瞬間)
# 上から下へ (Start) または 下から上へ (End)
crossings = df[
    ((df['prev_level'] > target_cm) & (df['Level_cm'] <= target_cm)) | # Down
    ((df['prev_level'] <= target_cm) & (df['Level_cm'] > target_cm))   # Up
].copy()

# 交差点の中でも「時間枠内」のものだけに絞る
# 許容範囲を少し広げる（境界線上の扱いのため）
filtered_crossings = crossings[
    (crossings['raw_time'].dt.hour >= start_hour) & 
    (crossings['raw_time'].dt.hour <= end_hour)
]

# 注釈を入れる
for _, row in filtered_crossings.iterrows():
    t = row['raw_time']
    lvl = row['Level_cm']
    
    # 時間のフォーマット
    time_str = t.strftime("%H:%M")
    
    # 引き出し線の設定
    # グラフが見づらくならないよう、ターゲットラインより少し上にテキストを配置
    ax.annotate(
        time_str, 
        xy=(t, target_cm),             # 矢印の先端 (交差点)
        xytext=(0, 30),                # テキストの位置 (交差点から上に30ポイント)
        textcoords='offset points',    # 相対座標指定
        ha='center', 
        va='bottom',
        fontsize=9,
        fontweight='bold',
        color='#aa0000',
        arrowprops=dict(arrowstyle='->', color='black', linewidth=0.5) # 矢印の設定
    )

# 5. グラフの装飾
ax.set_ylabel("Level (cm)")
ax.grid(True, which='both', linestyle='--', alpha=0.3)
ax.legend(loc='upper right')

# X軸の設定 (1日ごとに目盛り、日付表示)
ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
ax.xaxis.set_major_formatter(mdates.DateFormatter('%d (%a)'))
plt.xticks(rotation=0) # 日付は横向き
plt.xlim(df['raw_time'].min(), df['raw_time'].max()) # 左右の余白を詰める

st.pyplot(fig)

# データテーブル表示（条件に合う日時をリスト化）
with st.expander("Show List of Target Times"):
    # フィルタリングされたデータから、「日付」と「時間帯」を抽出して表示
    # 簡易的に、赤く塗られたエリアのデータを抽出
    target_df = df[level_condition & time_condition].copy()
    if not target_df.empty:
        target_df['Date'] = target_df['raw_time'].dt.strftime('%m/%d (%a)')
        target_df['Time'] = target_df['raw_time'].dt.strftime('%H:%M')
        # 表示用
        st.dataframe(target_df[['Date', 'Time', 'Level_cm']], use_container_width=True)
    else:
        st.write("No times found matching criteria.")
