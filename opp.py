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
# 物理計算ロジック (調和定数による推算)
# ---------------------------------------------------------
class HarmonicTideModel:
    def __init__(self):
        # 分潮の角速度 (度/時) - 気象庁潮汐表等の定義値
        self.SPEEDS = {
            'M2': 28.9841042,
            'S2': 30.0000000,
            'K1': 15.0410686,
            'O1': 13.9430356
        }
        
        # 初期値: 広島港(宇品)の定数 (ここから微調整する)
        # 振幅(cm), 遅角(度)
        self.consts = {
            'M2': {'amp': 132.0, 'phase': 206.5},
            'S2': {'amp': 48.0,  'phase': 242.6},
            'K1': {'amp': 37.0,  'phase': 191.0},
            'O1': {'amp': 30.0,  'phase': 172.6}
        }
        self.MSL = 240.0 # 平均水面

    def update_constants(self, m2_amp, m2_phase, s2_amp, s2_phase, k1_amp, k1_phase, o1_amp, o1_phase, msl):
        """ユーザー入力で定数を更新"""
        self.consts['M2'] = {'amp': m2_amp, 'phase': m2_phase}
        self.consts['S2'] = {'amp': s2_amp, 'phase': s2_phase}
        self.consts['K1'] = {'amp': k1_amp, 'phase': k1_phase}
        self.consts['O1'] = {'amp': o1_amp, 'phase': o1_phase}
        self.MSL = msl

    def calculate_level(self, target_dt):
        """
        指定時刻の潮位を計算
        h = Z0 + Σ Hi * cos(ωi * t - κi)
        ※tは年初からの経過時間(時間単位)
        """
        # 年初(1月1日 00:00)を基準とする
        base_dt = datetime.datetime(target_dt.year, 1, 1)
        # 経過時間(hours)
        delta_sec = (target_dt - base_dt).total_seconds()
        t = delta_sec / 3600.0
        
        level = self.MSL
        
        for name, speed in self.SPEEDS.items():
            amp = self.consts[name]['amp']
            phase = self.consts[name]['phase']
            speed_rad = math.radians(speed)
            phase_rad = math.radians(phase)
            
            # 分潮の合成
            # cos(ωt - κ)
            level += amp * math.cos(speed_rad * t - phase_rad)
            
        return level

    def get_period_data(self, year, month, start_day, end_day, interval_minutes=5):
        detailed_data = []
        start_dt = datetime.datetime(year, month, start_day)
        last_day_of_month = calendar.monthrange(year, month)[1]
        if end_day > last_day_of_month: end_day = last_day_of_month
        end_dt = datetime.datetime(year, month, end_day, 23, 55)

        current_dt = start_dt
        while current_dt <= end_dt:
            level = self.calculate_level(current_dt)
            detailed_data.append({
                "raw_time": current_dt, 
                "Level_cm": level
            })
            current_dt += datetime.timedelta(minutes=interval_minutes)
        return detailed_data

# ---------------------------------------------------------
# メイン画面構成
# ---------------------------------------------------------
st.title("大西港 潮位ビジュアライザー (調和分解・合成版)")
st.caption("分潮(M2, S2...)の三角関数和により推算潮位を算出します")

# 現在時刻 (JST)
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
now_jst = now_jst.replace(tzinfo=None, second=0, microsecond=0)

# --- レイアウト: 設定とチューニング ---
col_main, col_side = st.columns([3, 1])

# 左側: 計算パラメータ (ここを調整してChowariに合わせる)
with col_side:
    st.header("🌊 定数チューニング")
    st.caption("Chowariと合うように数値を調整してください")
    
    with st.expander("主要分潮設定", expanded=True):
        st.markdown("**M2 (主太陰半日周潮)**")
        m2_amp = st.number_input("M2 振幅", value=132.0, step=1.0)
        m2_phase = st.number_input("M2 遅角(度)", value=206.5, step=1.0, help="時間をずらす場合はここを変更")
        
        st.markdown("**S2 (主太陽半日周潮)**")
        s2_amp = st.number_input("S2 振幅", value=48.0, step=1.0)
        s2_phase = st.number_input("S2 遅角(度)", value=242.6, step=1.0)
        
        st.markdown("**K1 (主太陰太陽日周潮)**")
        k1_amp = st.number_input("K1 振幅", value=37.0, step=1.0)
        k1_phase = st.number_input("K1 遅角(度)", value=191.0, step=1.0)
        
        st.markdown("**O1 (主太陰日周潮)**")
        o1_amp = st.number_input("O1 振幅", value=30.0, step=1.0)
        o1_phase = st.number_input("O1 遅角(度)", value=172.6, step=1.0)

        st.divider()
        msl_val = st.number_input("平均水面 (Z0)", value=240.0, step=10.0, help="グラフ全体の高さを上下させます")

# 右側: 表示設定
with col_main:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### 期間設定")
        year_sel = st.number_input("年", value=now_jst.year)
        period_options = [f"{m}月前半" for m in range(1, 13)] + [f"{m}月後半" for m in range(1, 13)]
        period_options = sorted(period_options, key=lambda x: int(x.split('月')[0]) + (0.5 if '後半' in x else 0))
        
        current_idx = (now_jst.month - 1) * 2
        if now_jst.day > 15: current_idx += 1
        selected_period = st.selectbox("表示期間", period_options, index=current_idx)

    with col2:
        st.markdown("##### ターゲット設定")
        target_cm = st.number_input("基準潮位(cm)", value=130, step=10)
        start_hour, end_hour = st.slider("活動時間", 0, 24, (7, 23), format="%d時")

# --- 計算実行 ---
model = HarmonicTideModel()
# ユーザー設定値を反映
model.update_constants(m2_amp, m2_phase, s2_amp, s2_phase, k1_amp, k1_phase, o1_amp, o1_phase, msl_val)

# 期間解析
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
    st.subheader(f"推算潮位: {selected_period}")
    
    fig, ax = plt.subplots(figsize=(15, 10))

    # メイン線
    ax.plot(df['raw_time'], df['Level_cm'], color='#1f77b4', linewidth=1.5, alpha=0.9, label="推算潮位")
    ax.axhline(y=target_cm, color='black', linestyle='--', linewidth=1, label=f"Target ({target_cm}cm)")

    # 塗りつぶし
    hours = df['raw_time'].dt.hour
    is_time_ok = (hours >= start_hour) & (hours < end_hour)
    is_level_ok = (df['Level_cm'] <= target_cm)
    ax.fill_between(df['raw_time'], df['Level_cm'], target_cm, 
                    where=(is_level_ok & is_time_ok), 
                    color='red', alpha=0.3, interpolate=True)

    # -----------------------------------------------------
    # 満潮・干潮の検出 (Peak Detection)
    # -----------------------------------------------------
    levels = df['Level_cm'].values
    times = df['raw_time'].tolist()
    
    for i in range(1, len(levels) - 1):
        # 満潮 (High)
        if levels[i-1] < levels[i] and levels[i] > levels[i+1]:
            ax.scatter(times[i], levels[i], color='red', s=30, zorder=5, marker='^')
            # グラフの上に表示
            ax.annotate(f"{times[i].strftime('%H:%M')}\n{levels[i]:.0f}",
                        xy=(times[i], levels[i]), xytext=(0, 10),
                        textcoords='offset points', ha='center', va='bottom',
                        fontsize=8, color='#880000', fontweight='bold')

        # 干潮 (Low)
        elif levels[i-1] > levels[i] and levels[i] < levels[i+1]:
            ax.scatter(times[i], levels[i], color='blue', s=30, zorder=5, marker='v')
            # グラフの下に表示
            ax.annotate(f"{times[i].strftime('%H:%M')}\n{levels[i]:.0f}",
                        xy=(times[i], levels[i]), xytext=(0, -25),
                        textcoords='offset points', ha='center', va='top',
                        fontsize=8, color='#000088', fontweight='bold')

    # -----------------------------------------------------
    # 現在時刻 (黄色点)
    # -----------------------------------------------------
    graph_start = df['raw_time'].iloc[0]
    graph_end = df['raw_time'].iloc[-1]
    
    if graph_start <= now_jst <= graph_end:
        ax.scatter(now_jst, current_tide_level, color='yellow', s=180, zorder=10, edgecolors='black', linewidth=1.5)
        ax.annotate(f"Now\n{now_jst.strftime('%H:%M')}\n{current_tide_level:.0f}cm", 
                    xy=(now_jst, current_tide_level), xytext=(0, 45),
                    textcoords='offset points', ha='center', va='bottom',
                    fontsize=10, fontweight='bold', color='black',
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", alpha=0.9),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0', color='black'))

    # -----------------------------------------------------
    # ターゲットエリア情報
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
        ax.annotate(start_t.strftime("%H:%M"), 
                    xy=(start_t, target_cm), xytext=(0, y_pos_start - target_cm),
                    textcoords='offset points', ha='center', va='bottom', 
                    fontsize=font_size, color='blue', fontweight='bold',
                    arrowprops=dict(arrowstyle='-', color='blue', linewidth=0.5, linestyle=':'))

        # End (緑/下)
        y_pos_end = target_cm - 15 - stagger
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
