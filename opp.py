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
# フォント設定 (グラフは完全英語化して文字化け回避)
# ---------------------------------------------------------
def configure_font():
    # 英語フォントを優先
    plt.rcParams['font.family'] = 'sans-serif'

configure_font()

# ---------------------------------------------------------
# セッション状態管理
# ---------------------------------------------------------
if 'view_date' not in st.session_state:
    now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    st.session_state['view_date'] = now_jst.date()

# ---------------------------------------------------------
# 潮汐計算モデル (調和分解法・1/7基準)
# ---------------------------------------------------------
class HarmonicTideModel:
    def __init__(self):
        """
        1/7の画像データを基準(Epoch)として、
        分潮(M2, S2, K1, O1)を合成し、月齢による潮位変化(大潮/小潮)を再現する。
        """
        # 基準日時: 2026/1/7 12:39 満潮 342cm (大西港実測)
        self.epoch_time = datetime.datetime(2026, 1, 7, 12, 39)
        self.epoch_level = 342.0
        
        # 平均水面 (MSL): 180cm (干潮がしっかり引くように設定)
        self.msl = 180.0
        
        # 呉港周辺の主要分潮定数
        # これらを合成することで「毎日違う波」が作られます
        self.consts = [
            {'name': 'M2', 'amp': 130.0, 'speed': 28.984}, # 主太陰半日周潮 (月の重力)
            {'name': 'S2', 'amp': 50.0,  'speed': 30.000}, # 主太陽半日周潮 (太陽の重力)
            {'name': 'K1', 'amp': 38.0,  'speed': 15.041}, # 日周潮
            {'name': 'O1', 'amp': 33.0,  'speed': 13.943}  # 日周潮
        ]
        
        # スケール補正 (基準日の高さに合うように振幅全体を調整)
        total_amp_theory = sum(c['amp'] for c in self.consts)
        actual_amp = self.epoch_level - self.msl
        self.scale_factor = actual_amp / total_amp_theory

    def _calc_raw(self, target_dt):
        # 基準時からの経過時間
        delta_hours = (target_dt - self.epoch_time).total_seconds() / 3600.0
        
        level = self.msl
        for c in self.consts:
            # 各波の位相を計算して合成
            theta_rad = math.radians(c['speed'] * delta_hours)
            level += (c['amp'] * self.scale_factor) * math.cos(theta_rad)
        return level

    def get_dataframe(self, start_date, days=10, interval_min=10):
        start_dt = datetime.datetime.combine(start_date, datetime.time(0, 0))
        end_dt = start_dt + datetime.timedelta(days=days) - datetime.timedelta(minutes=1)
        
        data = []
        curr = start_dt
        while curr <= end_dt:
            lvl = self._calc_raw(curr)
            data.append({"time": curr, "level": lvl})
            curr += datetime.timedelta(minutes=interval_min)
        return pd.DataFrame(data)

    def get_current_level(self):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_jst = now_utc + datetime.timedelta(hours=9)
        now_naive = now_jst.replace(tzinfo=None)
        return now_naive, self._calc_raw(now_naive)

# ---------------------------------------------------------
# メイン画面 UI
# ---------------------------------------------------------
st.title("⚓ Onishi Port Tide Master")
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

# --- サイドバー設定 ---
with st.sidebar:
    st.header("⚙️ Work Settings")
    
    # 作業基準潮位
    target_cm = st.number_input("Work Limit Level (cm)", value=120, step=10, help="これ以下なら作業可能")
    # 作業可能時間帯
    start_h, end_h = st.slider("Workable Hours", 0, 24, (7, 23), format="%d:00")
    
    st.markdown("---")
    st.info("Calculated based on Jan 7 Data.\n(1/7のデータを基準に自動計算)")
    
    if st.button("Back to Today"):
        st.session_state['view_date'] = now_jst.date()

# --- 計算実行 ---
model = HarmonicTideModel()

# --- 期間切り替え ---
col_n1, col_n2, col_n3 = st.columns([1, 4, 1])
days_to_show = 10

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
        
        # 10分以上
        if (end_t - start_t).total_seconds() >= 600:
            min_lvl = grp['level'].min()
            min_time = grp.loc[grp['level'].idxmin(), 'time']
            
            # 作業時間計算
            duration = end_t - start_t
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            dur_str = f"{hours}:{minutes:02}"
            
            safe_windows.append({
                "date_str": start_t.strftime('%m/%d (%a)'),
                "start": start_t.strftime("%H:%M"),
                "end": end_t.strftime("%H:%M"),
                "duration": dur_str, # リスト用(日本語OK)
                "graph_label": f"Work Time\n{dur_str}", # グラフ用(英語)
                "min_time": min_time,
                "min_level": min_lvl
            })

# ---------------------------------------------------------
# グラフ描画 (English Only)
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(14, 7))

# 線と基準
ax.plot(df['time'], df['level'], color='#0066cc', linewidth=2, label="Level", zorder=2)
ax.axhline(y=target_cm, color='orange', linestyle='--', linewidth=2, label=f"Limit {target_cm}cm", zorder=1)
ax.fill_between(df['time'], df['level'], target_cm, where=df['is_safe'], color='#ffcc00', alpha=0.4, label="Workable")

# 1. 現在位置 (Now)
curr_time, curr_lvl = model.get_current_level()
graph_start = df['time'].iloc[0]
graph_end = df['time'].iloc[-1]

if graph_start <= curr_time <= graph_end:
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
    
    # 干潮 (Low)
    if levels[i-1] > l and l < levels[i+1] and l < 180:
        ax.scatter(t, l, color='blue', marker='v', s=40, zorder=3)
        off_y = -25 if (t.day % 2 == 0) else -40
        ax.annotate(f"{t.strftime('%H:%M')}\n{int(l)}", (t, l), xytext=(0, off_y), 
                    textcoords='offset points', ha='center', fontsize=9, color='#0000cc', fontweight='bold')

# 3. 作業時間 (Work Time)
for win in safe_windows:
    x = win['min_time']
    y = win['min_level']
    # 英語ラベル
    ax.annotate(win['graph_label'], (x, y), xytext=(0, -65), 
                textcoords='offset points', ha='center', fontsize=9, 
                color='#b8860b', fontweight='bold',
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.7))

# 軸設定 (English)
ax.set_ylabel("Level (cm)")
ax.grid(True, linestyle=':', alpha=0.6)
ax.xaxis.set_major_locator(mdates.DayLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n(%a)')) # Mon, Tue...
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
            "date_str": st.column_config.TextColumn("日付 (Date)", width="medium"),
            "start": st.column_config.TextColumn("開始 (Start)", width="medium"),
            "end": st.column_config.TextColumn("終了 (End)", width="medium"),
            "duration": st.column_config.TextColumn("作業時間 (Duration)", width="medium"),
        }
    )
