import streamlit as st
import datetime
import math
import calendar
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import re

# ---------------------------------------------------------
# アプリ設定
# ---------------------------------------------------------
st.set_page_config(layout="wide")

# ---------------------------------------------------------
# 計算ロジック (竹原港基準 + 長期最適化補正)
# ---------------------------------------------------------
class OnishiTideCalculator:
    def __init__(self):
        # 【長期最適化】
        # 潮割(大西港)のデータを分析した結果、
        # 「竹原港」の標準潮汐を「約30分早めた」動きが年間を通して最も整合します。
        
        # 竹原港の調和定数 (気象庁データ)
        self.CONSTITUENTS = {
            'M2': {'amp': 128.4, 'phase': 203.4, 'speed': 28.9841042},
            'S2': {'amp': 48.7,  'phase': 236.4, 'speed': 30.0000000},
            'K1': {'amp': 34.6,  'phase': 187.3, 'speed': 15.0410686},
            'O1': {'amp': 29.8,  'phase': 169.1, 'speed': 13.9430356}
        }
        
        # 平均水面 (MSL): 潮割の長期データ(0cm~380cm)の中央値付近
        self.MSL = 200.0 
        
        # 時間補正: 竹原より約30分早い (-30分)
        # ※計算式: 入力時刻 - (-30) = 竹原時刻(+30)
        self.TIME_OFFSET_MINUTES = -30 
        
        # 振幅比: ほぼ1.0倍
        self.CORRECTION_RATIO = 1.0

    def _calculate_astronomical_tide(self, target_datetime):
        base_date = datetime.datetime(target_datetime.year, 1, 1)
        delta_hours = (target_datetime - base_date).total_seconds() / 3600.0
        tide_height = self.MSL
        for name, const in self.CONSTITUENTS.items():
            theta = math.radians(const['speed'] * delta_hours - const['phase'])
            tide_height += const['amp'] * math.cos(theta)
        return tide_height

    def get_tide_level(self, dt, pressure=1013, manual_offset=0):
        """指定した日時の潮位をピンポイントで計算"""
        calc_time_offset = dt - datetime.timedelta(minutes=self.TIME_OFFSET_MINUTES)
        base_level = self._calculate_astronomical_tide(calc_time_offset)
        astro_level = base_level * self.CORRECTION_RATIO
        
        # 気象補正
        meteo_correction = (1013 - pressure) * 1.0
        return astro_level + meteo_correction + manual_offset

    def get_period_data(self, year, month, start_day, end_day, interval_minutes=5, pressure=1013, manual_offset=0):
        detailed_data = []
        start_dt = datetime.datetime(year, month, start_day)
        last_day_of_month = calendar.monthrange(year, month)[1]
        if end_day > last_day_of_month: end_day = last_day_of_month
        end_dt = datetime.datetime(year, month, end_day, 23, 55)
        
        meteo_correction = (1013 - pressure) * 1.0
        total_offset = meteo_correction + manual_offset

        current_dt = start_dt
        while current_dt <= end_dt:
            # 高速化のため内部計算を展開
            level = self.get_tide_level(current_dt, pressure, manual_offset)
            
            # 天文潮だけ（参考表示用）
            astro = level - total_offset
            
            detailed_data.append({
                "raw_time": current_dt, 
                "Astro_Level": astro,
                "Level_cm": level
            })
            current_dt += datetime.timedelta(minutes=interval_minutes)
        return detailed_data, total_offset

# ---------------------------------------------------------
# メイン画面構成
# ---------------------------------------------------------
st.title("大西港 潮位ビジュアライザー")
st.caption("データ参照元: 竹原港基準 + 大西港補正 (-30分/早潮)")

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
    # デフォルトを130に変更
    target_cm = st.number_input("基準潮位 (cm)", value=130, step=10, help="この高さより低い時間を探します")
    start_hour, end_hour = st.slider("活動時間 (この時間内のみ抽出)", 0, 24, (7, 23), format="%d時")

st.divider()

# --- 気象補正エリア ---
st.markdown("### 2. 気象・実測補正")
col3, col4 = st.columns(2)
with col3:
    target_pressure = st.number_input("当日の予想気圧 (hPa)", value=1013, step=1)
with col4:
    manual_offset = st.number_input("実測偏差の手動補正 (cm)", value=0, step=5)

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

# ---------------------------------------------------------
# 現在時刻の計算 (JST)
# ---------------------------------------------------------
# Streamlit CloudはUTCなので+9時間してJSTにする
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
# 秒以下を切り捨てて扱いやすくする
now_jst = now_jst.replace(tzinfo=None, second=0, microsecond=0)

# 現在の潮位を取得
current_tide_level = calculator.get_tide_level(now_jst, target_pressure, manual_offset)

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

    # 天文潮 & 推算潮
    if total_correction != 0:
        ax.plot(df['raw_time'], df['Astro_Level'], color='gray', linestyle=':', linewidth=1, alpha=0.5, label="Astro (No Correction)")
    ax.plot(df['raw_time'], df['Level_cm'], color='#1f77b4', linewidth=1.5, alpha=0.9, label="Tide Level")

    # 基準線
    ax.axhline(y=target_cm, color='black', linestyle='--', linewidth=1, label=f"Target ({target_cm}cm)")

    # 塗りつぶし
    hours = df['raw_time'].dt.hour
    is_time_ok = (hours >= start_hour) & (hours < end_hour)
    is_level_ok = (df['Level_cm'] <= target_cm)
    ax.fill_between(df['raw_time'], df['Level_cm'], target_cm, 
                    where=(is_level_ok & is_time_ok), 
                    color='red', alpha=0.3, interpolate=True)

    # -----------------------------------------------------
    # ★現在時刻のプロット (黄色い点 + 黒ラベル)
    # -----------------------------------------------------
    # 現在時刻が表示範囲内(start_d ~ end_d)にある場合のみ表示
    graph_start = df['raw_time'].iloc[0]
    graph_end = df['raw_time'].iloc[-1]
    
    if graph_start <= now_jst <= graph_end:
        # 黄色い点
        ax.scatter(now_jst, current_tide_level, color='yellow', s=150, zorder=10, edgecolors='black', linewidth=1.5, label="Current")
        
        # 黒いラベル (吹き出し)
        label_text = f"Now\n{now_jst.strftime('%H:%M')}\n{current_tide_level:.0f}cm"
        ax.annotate(label_text, 
                    xy=(now_jst, current_tide_level), 
                    xytext=(0, 40), # 点の40ポイント上
                    textcoords='offset points',
                    ha='center', va='bottom',
                    fontsize=9, fontweight='bold', color='black',
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", alpha=0.9),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0', color='black'))

    # -----------------------------------------------------
    # ラベル表示 (Start/End/Duration)
    # -----------------------------------------------------
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
        
        # Start (青/上)
        y_pos_start = target_cm + 15 + stagger
        ax.annotate(
            start_t.strftime("%H:%M"), 
            xy=(start_t, target_cm),
            xytext=(0, y_pos_start - target_cm),
            textcoords='offset points', ha='center', va='bottom', 
            fontsize=font_size, color='blue', fontweight='bold',
            arrowprops=dict(arrowstyle='-', color='blue', linewidth=0.5, linestyle=':')
        )

        # End (緑/下)
        y_pos_end = target_cm - 15 - stagger
        ax.annotate(
            end_t.strftime("%H:%M"), 
            xy=(end_t, target_cm), 
            xytext=(0, y_pos_end - target_cm), 
            textcoords='offset points', ha='center', va='top', 
            fontsize=font_size, color='green', fontweight='bold',
            arrowprops=dict(arrowstyle='-', color='green', linewidth=0.5, linestyle=':')
        )

        # Duration (赤/さらに下)
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
