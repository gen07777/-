import streamlit as st
import datetime
import math
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager

# ---------------------------------------------------------
# アプリ設定
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="Onishi Port Tide Master")

# ---------------------------------------------------------
# フォント設定 (英語表記で文字化け回避)
# ---------------------------------------------------------
def configure_font():
    plt.rcParams['font.family'] = 'sans-serif'

configure_font()

# ---------------------------------------------------------
# セッション状態
# ---------------------------------------------------------
if 'view_date' not in st.session_state:
    now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    st.session_state['view_date'] = now_jst.date()

# ---------------------------------------------------------
# 潮汐計算モデル (大西港カスタム・非対称波形)
# ---------------------------------------------------------
class OnishiCustomTideModel:
    def __init__(self, input_date, input_high_time, input_high_level):
        """
        ユーザー入力された「満潮」を基準に、
        大西港特有の「下げ潮が早い」特性を加味したカーブを生成する
        """
        # 基準となる満潮日時
        self.high_dt = datetime.datetime.combine(input_date, input_high_time)
        self.high_level = float(input_high_level)
        
        # 干潮潮位の推定 (呉のデータ傾向から、大潮・小潮を簡易推定して振幅を決める)
        # ※簡易的に、満潮潮位から計算（MSL約180cmを基準に逆算）
        self.msl = 180.0
        self.amp = self.high_level - self.msl
        
        # 【重要】大西港の傾向補正
        # 満潮 -> 干潮 (下げ) : 早い (約6.0時間)
        # 干潮 -> 満潮 (上げ) : 遅い (約6.4時間)
        # 平均周期 12.4時間
        self.period = 12.42 * 60 # 分
        self.fall_ratio = 0.48   # 下げ工程が全周期の48% (通常は50%)

    def _get_phase(self, target_dt):
        # 基準満潮からの経過時間(分)
        diff_min = (target_dt - self.high_dt).total_seconds() / 60.0
        
        # 周期で正規化 (0.0 ~ 1.0)
        cycle_pos = (diff_min % self.period) / self.period
        
        # 非対称補正 (Asymmetric Tide)
        # 下げ潮を早く、上げ潮を遅くするための位相歪曲
        if cycle_pos < self.fall_ratio:
            # 下げ潮区間 (0 ~ 0.48) -> 0 ~ 0.5 に引き伸ばしてcos計算へ
            adjusted_pos = cycle_pos * (0.5 / self.fall_ratio)
        else:
            # 上げ潮区間 (0.48 ~ 1.0) -> 0.5 ~ 1.0 に圧縮してcos計算へ
            adjusted_pos = 0.5 + (cycle_pos - self.fall_ratio) * (0.5 / (1.0 - self.fall_ratio))
            
        return adjusted_pos * 2 * math.pi

    def calculate_level(self, target_dt):
        theta = self._get_phase(target_dt)
        # cos(0)=1(満潮), cos(pi)=-1(干潮)
        return self.msl + self.amp * math.cos(theta)

    def get_dataframe(self, start_date, days=10, interval_min=10):
        start_dt = datetime.datetime.combine(start_date, datetime.time(0, 0))
        end_dt = start_dt + datetime.timedelta(days=days) - datetime.timedelta(minutes=1)
        
        data = []
        curr = start_dt
        while curr <= end_dt:
            lvl = self.calculate_level(curr)
            data.append({"time": curr, "level": lvl})
            curr += datetime.timedelta(minutes=interval_min)
        return pd.DataFrame(data)

    def get_current_level(self):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_jst = now_utc + datetime.timedelta(hours=9)
        now_naive = now_jst.replace(tzinfo=None)
        return now_naive, self.calculate_level(now_naive)

# ---------------------------------------------------------
# メイン画面 UI
# ---------------------------------------------------------
st.title("⚓ Onishi Port Tide Master")
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

# --- サイドバー (入力エリア) ---
with st.sidebar:
    st.header("1. Input Data")
    st.caption("リストにある『今日の満潮』を入力してください")
    
    # 日付入力
    input_date = st.date_input("Date", value=now_jst.date())
    
    # 満潮入力 (デフォルトは1/7の値)
    col1, col2 = st.columns(2)
    with col1:
        in_time = st.time_input("High Tide Time", value=datetime.time(12, 39))
    with col2:
        in_level = st.number_input("High Tide Level", value=342, step=1)
    
    st.markdown("---")
    st.header("2. Work Settings")
    target_cm = st.number_input("Work Limit Level (cm)", value=120, step=10)
    start_h, end_h = st.slider("Workable Hours", 0, 24, (7, 23), format="%d:00")
    
    if st.button("Reset to Today"):
        st.session_state['view_date'] = now_jst.date()

# --- 計算モデル作成 ---
model = OnishiCustomTideModel(input_date, in_time, in_level)

# --- 期間切り替え ---
col_n1, col_n2, col_n3 = st.columns([1, 4, 1])
days_to_show = 10 # 10日表示

with col_n1:
    if st.button("◀ Prev 10d"):
        st.session_state['view_date'] -= datetime.timedelta(days=days_to_show)
with col_n3:
    if st.button("Next 10d ▶"):
        st.session_state['view_date'] += datetime.timedelta(days=days_to_show)
with col_n2:
    st.markdown(f"<h4 style='text-align: center;'>Period: {st.session_state['view_date'].strftime('%Y/%m/%d')} - </h4>", unsafe_allow_html=True)

# --- データ生成 ---
df = model.get_dataframe(st.session_state['view_date'], days=days_to_show)

# ---------------------------------------------------------
# 作業可能時間の解析
# ---------------------------------------------------------
df['hour'] = df['time'].dt.hour
df['is_safe'] = (df['level'] <= target_cm) & (df['hour'] >= start_h) & (df['hour'] < end_h)

safe_windows = []
if df['is_safe'].any():
    df['group'] = (df['is_safe'] != df['is_safe'].shift()).cumsum()
    groups = df[df['is_safe']].groupby('group')
    
    for _, grp in groups:
        start_t = grp['time'].iloc[0]
        end_t = grp['time'].iloc[-1]
        
        if (end_t - start_t).total_seconds() >= 600:
            min_lvl = grp['level'].min()
            min_time = grp.loc[grp['level'].idxmin(), 'time']
            
            # 時間計算
            duration = end_t - start_t
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            dur_str = f"{hours}:{minutes:02}"
            
            safe_windows.append({
                "date_str": start_t.strftime('%m/%d (%a)'),
                "start": start_t.strftime("%H:%M"),
                "end": end_t.strftime("%H:%M"),
                "duration": dur_str,
                "label": f"Work Time\n{dur_str}",
                "min_time": min_time,
                "min_level": min_lvl
            })

# ---------------------------------------------------------
# グラフ描画
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(14, 7))

# 線と基準
ax.plot(df['time'], df['level'], color='#0066cc', linewidth=2, label="Level", zorder=2)
ax.axhline(y=target_cm, color='orange', linestyle='--', linewidth=2, label=f"Limit {target_cm}cm", zorder=1)
ax.fill_between(df['time'], df['level'], target_cm, where=df['is_safe'], color='#ffcc00', alpha=0.4, label="Workable")

# 1. 現在位置 (Now)
curr_time, curr_lvl = model.get_current_level()
if df['time'].iloc[0] <= curr_time <= df['time'].iloc[-1]:
    ax.scatter(curr_time, curr_lvl, color='gold', edgecolors='black', s=180, zorder=10)
    ax.annotate(f"Now\n{int(curr_lvl)}cm", (curr_time, curr_lvl), xytext=(0, 25), 
                textcoords='offset points', ha='center', fontsize=10, fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gold", alpha=0.9))

# 2. ピーク (High/Low)
levels = df['level'].values
times = df['time'].tolist()
for i in range(1, len(levels)-1):
    t, l = times[i], levels[i]
    
    # 満潮 (High)
    if levels[i-1] < l and l > levels[i+1] and l > 180:
        ax.scatter(t, l, color='red', marker='^', s=40, zorder=3)
        off_y = 15 if (t.day % 2 == 0) else 30
        ax.annotate(f"{t.strftime('%H:%M')}\n{int(l)}", (t, l), xytext=(0, off_y), 
                    textcoords='offset points', ha='center', fontsize=9, color='#cc0000', fontweight='bold')
    
    # 干潮 (Low) - 時刻も表示
    if levels[i-1] > l and l < levels[i+1] and l < 180:
        ax.scatter(t, l, color='blue', marker='v', s=40, zorder=3)
        off_y = -25 if (t.day % 2 == 0) else -40
        ax.annotate(f"{t.strftime('%H:%M')}\n{int(l)}", (t, l), xytext=(0, off_y), 
                    textcoords='offset points', ha='center', fontsize=9, color='#0000cc', fontweight='bold')

# 3. 作業時間 (Work Time)
for win in safe_windows:
    x = win['min_time']
    y = win['min_level']
    # 干潮時刻の下に表示
    ax.annotate(win['label'], (x, y), xytext=(0, -65), 
                textcoords='offset points', ha='center', fontsize=9, 
                color='#b8860b', fontweight='bold',
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.7))

# 軸設定
ax.set_ylabel("Level (cm)")
ax.grid(True, linestyle=':', alpha=0.6)
ax.xaxis.set_major_locator(mdates.DayLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n(%a)'))
ax.set_ylim(bottom=-80)

plt.tight_layout()
st.pyplot(fig)

# ---------------------------------------------------------
# 作業可能時間検討リスト (日本語OK)
# ---------------------------------------------------------
st.markdown(f"### 📋 作業可能時間検討リスト (Level <= {target_cm}cm)")

if not safe_windows:
    st.warning("No workable time found.")
else:
    res_df = pd.DataFrame(safe_windows)
    display_df = res_df[['date_str', 'start', 'end', 'duration']]
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "date_str": st.column_config.TextColumn("Date", width="medium"),
            "start": st.column_config.TextColumn("Start", width="medium"),
            "end": st.column_config.TextColumn("End", width="medium"),
            "duration": st.column_config.TextColumn("Duration (作業時間)", width="medium"),
        }
    )
