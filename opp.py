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
# 計算ロジック (標準港: 広島 + ユーザー調整機能)
# ---------------------------------------------------------
class OnishiTideCalculator:
    def __init__(self):
        # 広島港(宇品)の標準調和定数 (最も信頼性が高いデータ)
        self.CONSTITUENTS = {
            'M2': {'amp': 132.0, 'phase': 206.5, 'speed': 28.9841042},
            'S2': {'amp': 48.0,  'phase': 242.6, 'speed': 30.0000000},
            'K1': {'amp': 37.0,  'phase': 191.0, 'speed': 15.0410686},
            'O1': {'amp': 30.0,  'phase': 172.6, 'speed': 13.9430356}
        }
        # 平均水面 (MSL): 240cm (広島標準)
        self.MSL = 240.0 
        
        # ユーザー補正値 (初期化)
        self.user_time_offset = 0
        self.user_height_offset = 0

    def set_user_offsets(self, time_offset_mins, height_offset_cm):
        """ユーザーによる補正値をセット"""
        self.user_time_offset = time_offset_mins
        self.user_height_offset = height_offset_cm

    def _calculate_astronomical_tide(self, target_datetime):
        base_date = datetime.datetime(target_datetime.year, 1, 1)
        delta_hours = (target_datetime - base_date).total_seconds() / 3600.0
        tide_height = self.MSL
        for name, const in self.CONSTITUENTS.items():
            theta = math.radians(const['speed'] * delta_hours - const['phase'])
            tide_height += const['amp'] * math.cos(theta)
        return tide_height

    def get_tide_level(self, dt):
        """指定日時の潮位計算"""
        # ユーザー補正（時間をずらす）
        # calc_time = 表示時刻 - (ユーザー補正)
        calc_dt = dt - datetime.timedelta(minutes=self.user_time_offset)
        
        base_level = self._calculate_astronomical_tide(calc_dt)
        
        # ユーザー補正（高さをずらす）
        final_level = base_level + self.user_height_offset
        return final_level

    def get_period_data(self, year, month, start_day, end_day, interval_minutes=5):
        detailed_data = []
        start_dt = datetime.datetime(year, month, start_day)
        last_day_of_month = calendar.monthrange(year, month)[1]
        if end_day > last_day_of_month: end_day = last_day_of_month
        end_dt = datetime.datetime(year, month, end_day, 23, 55)

        current_dt = start_dt
        while current_dt <= end_dt:
            level = self.get_tide_level(current_dt)
            detailed_data.append({
                "raw_time": current_dt, 
                "Level_cm": level
            })
            current_dt += datetime.timedelta(minutes=interval_minutes)
        return detailed_data

# ---------------------------------------------------------
# メイン画面構成
# ---------------------------------------------------------
st.title("大西港 潮位ビジュアライザー (調整モード)")

# 現在時刻 (JST) の取得
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
now_jst = now_jst.replace(tzinfo=None, second=0, microsecond=0)

st.markdown(f"**現在時刻 (JST):** `{now_jst.strftime('%Y/%m/%d %H:%M')}`")

# --- 設定エリア (3カラム) ---
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    st.markdown("##### 1. 期間設定")
    year_sel = st.number_input("年", value=now_jst.year)
    
    period_options = []
    for m in range(1, 13):
        period_options.append(f"{m}月前半")
        period_options.append(f"{m}月後半")
    
    # 今の時期をデフォルト選択
    current_idx = (now_jst.month - 1) * 2
    if now_jst.day > 15: current_idx += 1
    selected_period = st.selectbox("期間", period_options, index=current_idx)

with col2:
    st.markdown("##### 2. ターゲット設定")
    target_cm = st.number_input("基準潮位(cm)", value=130, step=10)
    start_hour, end_hour = st.slider("活動時間", 0, 24, (7, 23), format="%d時")

with col3:
    st.markdown("##### 3. ズレ補正 (重要)")
    st.caption("Chowariと合うように調整してください")
    
    offset_time = st.number_input(
        "時間のズレ (分)", 
        value=0, step=10, 
        help="グラフが実測より「遅れている」ならマイナス、「進んでいる」ならプラス"
    )
    
    offset_height = st.number_input(
        "高さのズレ (cm)", 
        value=0, step=10,
        help="グラフ全体を上げ下げします"
    )

st.divider()

# --- データ生成 ---
try:
    month_match = re.match(r"(\d+)月", selected_period)
    month_sel = int(month_match.group(1))
    is_first_half = "前半" in selected_period
except:
    month_sel = now_jst.month
    is_first_half = True

last_day = calendar.monthrange(year_sel, month_sel)[1]
if is_first_half:
    start_d, end_d = 1, 15
else:
    start_d, end_d = 16, last_day

# 計算実行
calculator = OnishiTideCalculator()
calculator.set_user_offsets(offset_time, offset_height) # 補正値をセット

data = calculator.get_period_data(year_sel, month_sel, start_d, end_d)
df = pd.DataFrame(data)

# 現在潮位の計算
current_tide_level = calculator.get_tide_level(now_jst)

if df.empty:
    st.error("データがありません。")
else:
    # ---------------------------------------------------------
    # グラフ描画
    # ---------------------------------------------------------
    st.subheader(f"{selected_period}の潮位")
    
    # 補正情報の表示
    if offset_time != 0 or offset_height != 0:
        st.info(f"🔧 補正中: 時間 **{offset_time:+d}分**, 高さ **{offset_height:+d}cm**")

    fig, ax = plt.subplots(figsize=(15, 10))

    # メイン潮位線
    ax.plot(df['raw_time'], df['Level_cm'], color='#1f77b4', linewidth=1.5, alpha=0.9, label="Tide Level")
    ax.axhline(y=target_cm, color='black', linestyle='--', linewidth=1, label=f"Target ({target_cm}cm)")

    # 塗りつぶし
    hours = df['raw_time'].dt.hour
    is_time_ok = (hours >= start_hour) & (hours < end_hour)
    is_level_ok = (df['Level_cm'] <= target_cm)
    ax.fill_between(df['raw_time'], df['Level_cm'], target_cm, 
                    where=(is_level_ok & is_time_ok), 
                    color='red', alpha=0.3, interpolate=True)

    # -----------------------------------------------------
    # 現在時刻プロット (黄色点)
    # -----------------------------------------------------
    graph_start = df['raw_time'].iloc[0]
    graph_end = df['raw_time'].iloc[-1]
    
    if graph_start <= now_jst <= graph_end:
        ax.scatter(now_jst, current_tide_level, color='yellow', s=180, zorder=10, edgecolors='black', linewidth=1.5)
        
        # ラベル
        label_text = f"Now\n{now_jst.strftime('%H:%M')}\n{current_tide_level:.0f}cm"
        ax.annotate(label_text, 
                    xy=(now_jst, current_tide_level), 
                    xytext=(0, 45),
                    textcoords='offset points', ha='center', va='bottom',
                    fontsize=10, fontweight='bold', color='black',
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", alpha=0.9),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0', color='black'))

    # -----------------------------------------------------
    # ラベル (Start/End/Duration)
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

        # Duration (赤/下)
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
    
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d'))
    ax.set_xlim(df['raw_time'].iloc[0], df['raw_time'].iloc[-1])
    
    st.pyplot(fig)
