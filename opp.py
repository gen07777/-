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
st.set_page_config(layout="wide", page_title="大西港フェリーターミナル 潮汐計算機")

# ---------------------------------------------------------
# 定数・補正ルール（分析結果に基づく）
# ---------------------------------------------------------
# 大西港フェリーターミナルは、呉（標準）に対して：
# 満潮: +5分 (ほぼ同じだがわずかに遅れる)
# 干潮: -7分 (引き潮はかなり早まる)
OFFSET_HIGH = 5   # 分
OFFSET_LOW = -7   # 分

# ---------------------------------------------------------
# 物理計算ロジック (調和分解モデル)
# ---------------------------------------------------------
class HarmonicTideModel:
    def __init__(self):
        # 瀬戸内海・主要分潮の角速度 (degree/hour)
        self.SPEEDS = {
            'M2': 28.9841042, 'S2': 30.0000000,
            'K1': 15.0410686, 'O1': 13.9430356
        }
        # 標準的な振幅・位相定数（初期値）
        self.base_consts = {
            'M2': {'amp': 130.0, 'phase': 200.0},
            'S2': {'amp': 50.0,  'phase': 230.0},
            'K1': {'amp': 38.0,  'phase': 190.0},
            'O1': {'amp': 32.0,  'phase': 170.0}
        }
        self.msl = 240.0 
        self.phase_offset = 0

    def calibrate(self, kure_high_time, kure_high_level):
        """
        呉の満潮時間を入力とし、大西港の満潮（+5分）に合わせてモデルを同調させる
        """
        # 大西港のターゲット満潮時間 = 呉の時間 + 5分
        target_onishi_time = kure_high_time + datetime.timedelta(minutes=OFFSET_HIGH)
        
        search_start = target_onishi_time - datetime.timedelta(hours=3)
        search_end = target_onishi_time + datetime.timedelta(hours=3)
        best_time = search_start
        max_level = -9999
        dt = search_start
        
        # モデル上のピークを探す
        while dt <= search_end:
            lvl = self._calc_raw(dt, phase_shift=0, msl_shift=0)
            if lvl > max_level:
                max_level = lvl
                best_time = dt
            dt += datetime.timedelta(minutes=1)
        
        # ズレを計算して位相を補正
        time_diff_minutes = (target_onishi_time - best_time).total_seconds() / 60.0
        self.phase_offset = time_diff_minutes * 0.48 # 簡易位相係数
        
        # 高さのズレを補正
        height_diff = kure_high_level - max_level
        self.msl += height_diff
        
        return target_onishi_time, height_diff

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

    def get_period_data(self, year, month, start_day, end_day, interval_minutes=10):
        detailed_data = []
        try:
            start_dt = datetime.datetime(year, month, start_day)
            last_day_of_month = calendar.monthrange(year, month)[1]
            if end_day > last_day_of_month: end_day = last_day_of_month
            end_dt = datetime.datetime(year, month, end_day, 23, 55)
        except ValueError:
            return []

        current_dt = start_dt
        while current_dt <= end_dt:
            level = self.calculate_level(current_dt)
            detailed_data.append({"raw_time": current_dt, "Level_cm": level})
            current_dt += datetime.timedelta(minutes=interval_minutes)
        return detailed_data

# ---------------------------------------------------------
# メイン画面構成
# ---------------------------------------------------------
st.title("🚢 大西港フェリーターミナル専用 潮汐計算機")
st.markdown(f"""
**補正ルール適用中:** 呉（標準）に対し、**満潮は {OFFSET_HIGH:+}分**、**干潮は {OFFSET_LOW:+}分** で計算します。  
特に**「引き潮（干潮）」が表よりも早く来る**ことに注意してください。
""")

# 現在時刻 (JST)
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
now_jst = now_jst.replace(tzinfo=None, second=0, microsecond=0)

# --- サイドバー: データ入力 & 変換ツール ---
with st.sidebar:
    st.header("1. 基準データ入力")
    st.info("お手元の「呉（標準）」の潮汐表を見て、今日の満潮時刻を入力してください。")
    
    # デフォルト値
    def_time = datetime.time(12, 30)
    
    cal_date = st.date_input("日付", value=now_jst.date())
    kure_time = st.time_input("呉の満潮時刻", value=def_time)
    kure_level = st.number_input("呉の潮位 (cm)", value=340, step=10)
    
    st.markdown("---")
    st.header("2. 時刻変換ツール")
    st.write("呉の時刻を入力すると、大西港の時刻に変換します。")
    
    conv_mode = st.radio("潮の種類", ["満潮 (High)", "干潮 (Low)"])
    input_time_conv = st.time_input("呉の時刻を入力", value=datetime.time(6, 0) if conv_mode=="干潮 (Low)" else datetime.time(12, 0))
    
    if input_time_conv:
        base_dt_conv = datetime.datetime.combine(datetime.date.today(), input_time_conv)
        if conv_mode == "満潮 (High)":
            res_dt = base_dt_conv + datetime.timedelta(minutes=OFFSET_HIGH)
            st.markdown(f"### ➡ 大西港: **{res_dt.strftime('%H:%M')}**")
            st.caption(f"呉より {OFFSET_HIGH}分 遅らせる")
        else:
            res_dt = base_dt_conv + datetime.timedelta(minutes=OFFSET_LOW)
            st.markdown(f"### ➡ 大西港: **{res_dt.strftime('%H:%M')}**")
            st.caption(f"呉より {-OFFSET_LOW}分 早める")

# --- 設定エリア (メイン) ---
col1, col2 = st.columns(2)
with col1:
    st.markdown("##### 期間設定")
    year_sel = st.number_input("年", value=now_jst.year)
    period_options = [f"{m}月前半" for m in range(1, 13)] + [f"{m}月後半" for m in range(1, 13)]
    period_options = sorted(period_options, key=lambda x: int(x.split('月')[0]) + (0.5 if '後半' in x else 0))
    
    # 現在の月を選択状態にする
    current_idx = (now_jst.month - 1) * 2
    if now_jst.day > 15: current_idx += 1
    selected_period = st.selectbox("表示期間", period_options, index=current_idx)

with col2:
    st.markdown("##### 作業ターゲット")
    target_cm = st.number_input("基準潮位(cm) 以下を赤色表示", value=150, step=10)
    start_hour, end_hour = st.slider("活動時間帯", 0, 24, (6, 19), format="%d時")

# --- 計算実行 ---
model = HarmonicTideModel()
target_kure_dt = datetime.datetime.combine(cal_date, kure_time)

# キャリブレーション実行（呉の時間 -> 大西港の補正(+5分)を内部で適用）
real_onishi_high_time, diff_height = model.calibrate(target_kure_dt, kure_level)

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

# 現在潮位の計算
current_tide_level = model.calculate_level(now_jst)

if df.empty:
    st.error("日付設定エラー: データが生成できませんでした。")
else:
    # ---------------------------------------------------------
    # グラフ描画
    # ---------------------------------------------------------
    st.subheader(f"潮位グラフ: {year_sel}年{selected_period}")
    st.caption(f"グラフ基準: {cal_date.strftime('%m/%d')}の呉満潮 {kure_time.strftime('%H:%M')} をベースに補正")

    fig, ax = plt.subplots(figsize=(12, 6))

    # メイン線
    ax.plot(df['raw_time'], df['Level_cm'], color='#1f77b4', linewidth=2, alpha=0.8, label="推算潮位")
    ax.axhline(y=target_cm, color='red', linestyle='--', linewidth=1, label=f"基準 ({target_cm}cm)")

    # 塗りつぶし (活動時間かつ基準以下)
    hours = df['raw_time'].dt.hour
    is_time_ok = (hours >= start_hour) & (hours < end_hour)
    is_level_ok = (df['Level_cm'] <= target_cm)
    ax.fill_between(df['raw_time'], df['Level_cm'], target_cm, 
                    where=(is_level_ok & is_time_ok), 
                    color='red', alpha=0.2)

    # ピーク検出と「大西港補正」ラベル表示
    # モデルは満潮(+5分)に合わせてあるため、干潮は物理的に+5分付近になる。
    # しかし大西港の干潮は「-7分」なので、モデルの底より「12分」早い位置が正解。
    # グラフの見た目は変えず、マーカーだけ時間をずらして打つ。
    
    levels = df['Level_cm'].values
    times = df['raw_time'].tolist()
    
    for i in range(1, len(levels) - 1):
        # 満潮 (High Tide)
        if levels[i-1] < levels[i] and levels[i] > levels[i+1]:
            # 満潮はモデル通りでOK (+5分補正済み)
            t_plot = times[i]
            l_plot = levels[i]
            
            ax.scatter(t_plot, l_plot, color='red', s=40, zorder=5, marker='^')
            ax.annotate(f"{t_plot.strftime('%H:%M')}\n{l_plot:.0f}",
                        xy=(t_plot, l_plot), xytext=(0, 10),
                        textcoords='offset points', ha='center', va='bottom',
                        fontsize=9, color='#AA0000', fontweight='bold')
        
        # 干潮 (Low Tide)
        elif levels[i-1] > levels[i] and levels[i] < levels[i+1]:
            # 干潮は「モデルの底」よりも 12分早くする (呉-7分を実現するため)
            # モデルは呉+5分状態なので、そこから-12分すれば 呉-7分になる
            t_plot = times[i] - datetime.timedelta(minutes=12
