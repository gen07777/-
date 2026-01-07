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
st.set_page_config(layout="wide", page_title="Osaki-Kamijima Tide")

# ---------------------------------------------------------
# フォント設定 (一応残しますが、基本英語表記にします)
# ---------------------------------------------------------
def configure_font():
    # 英語フォントを優先
    plt.rcParams['font.family'] = 'sans-serif'

configure_font()

# ---------------------------------------------------------
# セッション状態管理
# ---------------------------------------------------------
if 'view_date' not in st.session_state:
    # タイムゾーンを考慮してJSTで初期化
    now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    st.session_state['view_date'] = now_jst.date()

# ---------------------------------------------------------
# 潮汐計算モデル (大西港・呉準拠 / MSL=180版)
# ---------------------------------------------------------
class FixedKureTideModel:
    def __init__(self):
        # 基準日時 (1/7 12:39 満潮 342cm)
        self.epoch_time = datetime.datetime(2026, 1, 7, 12, 39)
        self.epoch_level = 342.0
        self.msl = 180.0 
        
        # 分潮定数
        self.consts = [
            {'name': 'M2', 'amp': 130.0, 'speed': 28.984},
            {'name': 'S2', 'amp': 50.0,  'speed': 30.000},
            {'name': 'K1', 'amp': 38.0,  'speed': 15.041},
            {'name': 'O1', 'amp': 33.0,  'speed': 13.943}
        ]
        
        total_amp_theory = sum(c['amp'] for c in self.consts)
        actual_amp = self.epoch_level - self.msl
        self.scale_factor = actual_amp / total_amp_theory

    def _calc_raw(self, target_dt):
        delta_hours = (target_dt - self.epoch_time).total_seconds() / 3600.0
        level = self.msl
        for c in self.consts:
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
st.title("⚓ Osaki-Kamijima Tide Monitor")
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

# --- サイドバー設定 ---
with st.sidebar:
    st.header("⚙️ Settings")
    
    target_cm = st.number_input("Work Limit Level (cm)", value=120, step=10, help="作業基準潮位")
    start_h, end_h = st.slider("Workable Hours", 0, 24, (7, 23), format="%d:00")
    
    st.markdown("---")
    
    if st.button("Back to Today"):
        st.session_state['view_date'] = now_jst.date()

# --- 計算実行 ---
model = FixedKureTideModel()

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
    st.markdown(f"<h4 style='text-align: center;'>Range: {st.session_state['view_date'].strftime('%Y/%m/%d')} - </h4>", unsafe_allow_html=True)

# --- データ生成 ---
df = model.get_dataframe(st.session_state['view_date'], days=days_to_show)

# ---------------------------------------------------------
# 作業可能時間の計算
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
            
            # 作業時間を計算 (例: 1:30)
            duration = end_t - start_t
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            dur_str = f"{hours}:{minutes:02}" # 英語表記に変更
            
            safe_windows.append({
                "date_str": start_t.strftime('%m/%d (%a)'),
                "start": start_t.strftime("%H:%M"),
                "end": end_t.strftime("%H:%M"),
                "duration": dur_str, # リスト表示用
                "graph_label": f"Work Time\n{dur_str}", # グラフ表示用
                "min_time": min_time,
                "min_level": min_lvl
            })

# ---------------------------------------------------------
# グラフ描画 (All English)
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(14, 7))

# 潮位線 & 基準線
ax.plot(df['time'], df['level'], color='#0066cc', linewidth=2, label="Level", zorder=2)
ax.axhline(y=target_cm, color='orange', linestyle='--', linewidth=2, label=f"Limit {target_cm}cm", zorder=1)
ax.fill_between(df['time'], df['level'], target_cm, where=df['is_safe'], color='#ffcc00', alpha=0.4, label="Workable")

# --- 1. 現在位置 (Now) ---
curr_time, curr_lvl = model.get_current_level()
graph_start = df['time'].iloc[0]
graph_end = df['time'].iloc[-1]

if graph_start <= curr_time <= graph_end:
    ax.scatter(curr_time, curr_lvl, color='gold', edgecolors='black', s=150, zorder=10)
    # 英語 "Now" に変更
    ax.annotate(f"Now\n{int(curr_lvl)}cm", (curr_time, curr_lvl), xytext=(0, 20), 
                textcoords='offset points', ha='center', fontsize=10, fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gold", alpha=0.9))

# --- 2. ピーク (High/Low) ---
levels = df['level'].values
times = df['time'].tolist()
for i in range(1, len(levels)-1):
    t, l = times[i], levels[i]
    
    # 満潮 (High)
    if levels[i-1] < l and l > levels[i+1] and l > 180:
        ax.scatter(t, l, color='red', marker='^', s=40, zorder=3)
        off_y = 15 if (t.day % 2 == 0) else 30
        # 時刻と高さのみ (数字なので文字化けしない)
        ax.annotate(f"{t.strftime('%H:%M')}\n{int(l)}", (t, l), xytext=(0, off_y), 
                    textcoords='offset points', ha='center', fontsize=9, color='#cc0000', fontweight='bold')

    # 干潮 (Low)
    if levels[i-1] > l and l < levels[i+1] and l < 180:
        ax.scatter(t, l, color='blue', marker='v', s=40, zorder=3)
        off_y = -25 if (t.day % 2 == 0) else -40
        # 時刻と高さ
        label = f"{t.strftime('%H:%M')}\n{int(l)}"
        ax.annotate(label, (t, l), xytext=(0, off_y), 
                    textcoords='offset points', ha='center', fontsize=9, color='#0000cc', fontweight='bold')

# --- 3. 作業時間 (Work Time) ---
for win in safe_windows:
    x_pos = win['min_time']
    y_pos = win['min_level']
    
    # 英語ラベル "Work Time 4:30"
    label = win['graph_label']
    
    ax.annotate(label, (x_pos, y_pos), xytext=(0, -60), 
                textcoords='offset points', ha='center', fontsize=9, 
                color='#b8860b', fontweight='bold',
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.7))

# 軸ラベル等 (English)
ax.set_ylabel("Level (cm)")
ax.grid(True, linestyle=':', alpha=0.6)
ax.xaxis.set_major_locator(mdates.DayLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n(%a)')) # 曜日は英語環境ならMonなどになる
ax.set_ylim(bottom=-70) # ラベルスペース確保

plt.tight_layout()
st.pyplot(fig)

# ---------------------------------------------------------
# 作業可能時間リスト (ここは日本語でもOKだが、念のためシンプルに)
# ---------------------------------------------------------
st.markdown(f"### 📋 Workable Time List (Level <= {target_cm}cm)")

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
            "duration": st.column_config.TextColumn("Duration", width="medium"),
        }
    )
