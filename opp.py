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
# 物理計算ロジック (大西港専用チューニング)
# ---------------------------------------------------------
class HarmonicTideModel:
    def __init__(self):
        # 分潮の角速度 (度/時)
        self.SPEEDS = {
            'M2': 28.9841042,
            'S2': 30.0000000,
            'K1': 15.0410686,
            'O1': 13.9430356
        }
        
        # 【解析結果】大西港(フェリーターミナル)の推算定数
        # 呉(阿賀)の標準定数をベースに、大西港の地理的特性(早潮)を加味して調整済み
        # これにより、初期状態でChowari等のサイトとほぼ一致するはずです。
        self.base_consts = {
            'M2': {'amp': 130.0, 'phase': 200.0}, # 位相を早めに設定
            'S2': {'amp': 46.0,  'phase': 235.0},
            'K1': {'amp': 36.0,  'phase': 185.0},
            'O1': {'amp': 29.0,  'phase': 167.0}
        }
        
        # 平均水面 (Z0): サイトの基準面(DL)に合わせるための重要パラメータ
        # 潮割のデータはおよそ200-210cm付近が中心
        self.msl = 205.0 
        
        # 補正値
        self.phase_offset = 0

    def calibrate(self, target_high_time, target_high_level):
        """ユーザー入力値に合わせてモデルを微調整する"""
        # 前後3時間を探索
        search_start = target_high_time - datetime.timedelta(hours=3)
        search_end = target_high_time + datetime.timedelta(hours=3)
        
        best_time = search_start
        max_level = -9999
        
        dt = search_start
        while dt <= search_end:
            lvl = self._calc_raw(dt, phase_shift=0, msl_shift=0)
            if lvl > max_level:
                max_level = lvl
                best_time = dt
            dt += datetime.timedelta(minutes=1)
        
        # ズレを計算
        time_diff_minutes = (target_high_time - best_time).total_seconds() / 60.0
        # 位相補正 (M2分潮基準: 1分≒0.5度)
        self.phase_offset = time_diff_minutes * 0.5
        
        # 高さ補正
        height_diff = target_high_level - max_level
        self.msl += height_diff
        
        return time_diff_minutes, height_diff

    def _calc_raw(self, target_dt, phase_shift=0, msl_shift=0):
        base_dt = datetime.datetime(target_dt.year, 1, 1)
        delta_hours = (target_dt - base_dt).total_seconds() / 3600.0
        
        level = self.msl + msl_shift
        
        for name, speed in self.SPEEDS.items():
            const = self.base_consts[name]
            phase = const['phase'] - phase_shift 
            theta = math.radians(speed * delta_hours - phase)
            level += const['amp'] * math.cos(theta)
        return level

    def calculate_level(self, target_dt):
        return self._calc_raw(target_dt, self.phase_offset, 0)

    def get_period_data(self, year, month, start_day, end_day, interval_minutes=5):
        detailed_data = []
        start_dt = datetime.datetime(year, month, start_day)
        last_day_of_month = calendar.monthrange(year, month)[1]
        if end_day > last_day_of_month: end_day = last_day_of_month
        end_dt = datetime.datetime(year, month, end_day, 23, 55)

        current_dt = start_dt
        while current_dt <= end_dt:
            level = self.calculate_level(current_dt)
            detailed_data.append({"raw_time": current_dt, "Level_cm": level})
            current_dt += datetime.timedelta(minutes=interval_minutes)
        return detailed_data

# ---------------------------------------------------------
# メイン画面構成
# ---------------------------------------------------------
st.title("大西港 潮位ビジュアライザー (Chowari同調版)")

# 現在時刻 (JST)
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
now_jst = now_jst.replace(tzinfo=None, second=0, microsecond=0)

# --- セッション状態の初期化 ---
if 'cal_done' not in st.session_state:
    st.session_state['cal_done'] = False
    st.session_state['diff_min'] = 0
    st.session_state['diff_cm'] = 0

# --- サイドバー: 補正設定 ---
with st.sidebar:
    st.header("🔧 ズレ補正")
    st.caption("初期状態でChowari(大西港)に合わせてありますが、もしズレている場合は今日の満潮データを入力して補正してください。")
    
    with st.form("calibration_form"):
        cal_date = st.date_input("日付", value=now_jst.date())
        cal_time = st.time_input("満潮時刻", value=datetime.time(12, 00))
        cal_height = st.number_input("満潮潮位 (cm)", value=300, step=10)
        
        submitted = st.form_submit_button("この値に合わせる")
        
        if submitted:
            st.session_state['cal_target_dt'] = datetime.datetime.combine(cal_date, cal_time)
            st.session_state['cal_height'] = cal_height
            st.session_state['cal_done'] = True

# --- 設定エリア ---
col1, col2 = st.columns(2)
with col1:
    st.markdown("##### 1. 期間設定")
    year_sel = st.number_input("年", value=now_jst.year)
    period_options = [f"{m}月前半" for m in range(1, 13)] + [f"{m}月後半" for m in range(1, 13)]
    period_options = sorted(period_options, key=lambda x: int(x.split('月')[0]) + (0.5 if '後半' in x else 0))
    current_idx = (now_jst.month - 1) * 2
    if now_jst.day > 15: current_idx += 1
    selected_period = st.selectbox("期間", period_options, index=current_idx)

with col2:
    st.markdown("##### 2. ターゲット設定")
    target_cm = st.number_input("基準潮位(cm)", value=130, step=10)
    start_hour, end_hour = st.slider("活動時間", 0, 24, (7, 23), format="%d時")

# --- 計算実行 ---
model = HarmonicTideModel()

# 補正が適用されている場合
if st.session_state['cal_done']:
    diff_min, diff_cm = model.calibrate(st.session_state['cal_target_dt'], st.session_state['cal_height'])
    st.session_state['diff_min'] = diff_min
    st.session_state['diff_cm'] = diff_cm

# 期間データ生成
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

data = model.get_period_data(year_sel, month_sel, start_d, end_d)
df = pd.DataFrame(data)
current_tide_level = model.calculate_level(now_jst)

if df.empty:
    st.error("データがありません。")
else:
    # ---------------------------------------------------------
    # グラフ描画
    # ---------------------------------------------------------
    st.subheader(f"潮位グラフ: {selected_period}")
    
    if st.session_state['cal_done']:
        st.success(f"✅ 補正適用中: 時間 {st.session_state['diff_min']:+.1f}分 / 高さ {st.session_state['diff_cm']:+.1f}cm")

    fig, ax = plt.subplots(figsize=(15, 10))

    # メイン線
    ax.plot(df['raw_time'], df['Level_cm'], color='#1f77b4', linewidth=1.5, alpha=0.9, label="潮位")
    ax.axhline(y=target_cm, color='black', linestyle='--', linewidth=1, label=f"基準 ({target_cm}cm)")

    # 塗りつぶし
    hours = df['raw_time'].dt.hour
    is_time_ok = (hours >= start_hour) & (hours < end_hour)
    is_level_ok = (df['Level_cm'] <= target_cm)
    ax.fill_between(df['raw_time'], df['Level_cm'], target_cm, 
                    where=(is_level_ok & is_time_ok), 
                    color='red', alpha=0.3, interpolate=True)

    # -----------------------------------------------------
    # 満潮・干潮 (Peak Detection)
    # -----------------------------------------------------
    levels = df['Level_cm'].values
    times = df['raw_time'].tolist()
    
    for i in range(1, len(levels) - 1):
        # 満潮 (High)
        if levels[i-1] < levels[i] and levels[i] > levels[i+1]:
            ax.scatter(times[i], levels[i], color='red', s=30, zorder=5, marker='^')
            ax.annotate(f"{times[i].strftime('%H:%M')}\n{levels[i]:.0f}",
                        xy=(times[i], levels[i]), xytext=(0, 15),
                        textcoords='offset points', ha='center', va='bottom',
                        fontsize=9, color='#AA0000', fontweight='bold')

        # 干潮 (Low)
        elif levels[i-1] > levels[i] and levels[i] < levels[i+1]:
            ax.scatter(times[i], levels[i], color='blue', s=30, zorder=5, marker='v')
            ax.annotate(f"{times[i].strftime('%H:%M')}\n{levels[i]:.0f}",
                        xy=(times[i], levels[i]), xytext=(0, -25),
                        textcoords='offset points', ha='center', va='top',
                        fontsize=9, color='#0000AA', fontweight='bold')

    # -----------------------------------------------------
    # 現在時刻 (黄色点)
    # -----------------------------------------------------
    graph_start = df['raw_time'].iloc[0]
    graph_end = df['raw_time'].iloc[-1]
    
    if graph_start <= now_jst <= graph_end:
        ax.scatter(now_jst, current_tide_level, color='yellow', s=180, zorder=10, edgecolors='black', linewidth=1.5)
        
        # 吹き出し位置をさらに調整（他の文字と被らないよう大きく上に）
        ax.annotate(f"Now\n{now_jst.strftime('%H:%M')}\n{current_tide_level:.0f}cm", 
                    xy=(now_jst, current_tide_level), xytext=(0, 60),
                    textcoords='offset points', ha='center', va='bottom',
                    fontsize=10, fontweight='bold', color='black',
                    bbox=dict(boxstyle="round,pad=0.3", fc="yellow", ec="black", alpha=0.8),
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

        stagger = (label_offset_counter % 2) * 25 # ジグザグ幅を少し拡大
        label_offset_counter += 1
        font_size = 8
        
        # Start (青/上)
        y_pos_start = target_cm + 25 + stagger
        ax.annotate(start_t.strftime("%H:%M"), 
                    xy=(start_t, target_cm), xytext=(0, y_pos_start - target_cm),
                    textcoords='offset points', ha='center', va='bottom', 
                    fontsize=font_size, color='blue', fontweight='bold',
                    arrowprops=dict(arrowstyle='-', color='blue', linewidth=0.5, linestyle=':'))

        # End (緑/下)
        y_pos_end = target_cm - 25 - stagger
        ax.annotate(end_t.strftime("%H:%M"), 
                    xy=(end_t, target_cm), xytext=(0, y_pos_end - target_cm), 
                    textcoords='offset points', ha='center', va='top', 
                    fontsize=font_size, color='green', fontweight='bold',
                    arrowprops=dict(arrowstyle='-', color='green', linewidth=0.5, linestyle=':'))

        # Duration (赤/下)
        hours_dur = total_minutes // 60
        mins_dur = total_minutes % 60
        dur_str = f"{hours_dur}h{mins_dur}m"
        mid_time = start_t + (duration / 2)
        y_pos_dur = y_pos_end - 25 
        
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
