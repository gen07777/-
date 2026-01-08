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
st.set_page_config(layout="wide", page_title="Onishi Port Tide Master Pro")

# ---------------------------------------------------------
# フォント設定
# ---------------------------------------------------------
def configure_font():
    plt.rcParams['font.family'] = 'sans-serif'

configure_font()

# ---------------------------------------------------------
# セッション状態管理
# ---------------------------------------------------------
if 'view_date' not in st.session_state:
    now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    st.session_state['view_date'] = now_jst.date()

# ---------------------------------------------------------
# 潮汐計算モデル (本格的調和分解・10分潮モデル)
# ---------------------------------------------------------
class AdvancedTideModel:
    def __init__(self):
        """
        タイドグラフBI等のロジックに近づけるため、
        主要4分潮だけでなく、10分潮を用いて精密計算を行う。
        基準は1/7の大西港の実測値(画像)に合わせる。
        """
        # 基準日時: 2026/1/7 12:39 満潮 342cm
        self.epoch_time = datetime.datetime(2026, 1, 7, 12, 39)
        self.epoch_level = 342.0
        self.msl = 180.0
        
        # 【改良】日本沿岸の潮汐計算に使われる主要10分潮
        # 呉港の調和定数比率を参考に設定
        # speed: 角速度(度/時間), factor: 振幅の重み付け(M2を基準とした比率)
        self.consts = [
            # 半日周潮 (1日2回)
            {'name': 'M2',  'speed': 28.984104, 'factor': 1.00}, # 主太陰
            {'name': 'S2',  'speed': 30.000000, 'factor': 0.45}, # 主太陽
            {'name': 'N2',  'speed': 28.439730, 'factor': 0.22}, # 大陰楕円率
            {'name': 'K2',  'speed': 30.082137, 'factor': 0.12}, # 太陽・月
            
            # 日周潮 (1日1回)
            {'name': 'K1',  'speed': 15.041069, 'factor': 0.38}, # 主太陰太陽
            {'name': 'O1',  'speed': 13.943036, 'factor': 0.28}, # 主太陰
            {'name': 'P1',  'speed': 14.958931, 'factor': 0.12}, # 主太陽
            {'name': 'Q1',  'speed': 13.398661, 'factor': 0.05}, # 大陰楕円率
            
            # 浅海分潮 (地形の影響) - 波の歪みを再現
            {'name': 'M4',  'speed': 57.968208, 'factor': 0.03}, 
            {'name': 'MS4', 'speed': 58.984104, 'factor': 0.02}
        ]
        
        # スケール補正 (基準日の高さに合うように全体の振幅係数を逆算)
        # 基準時(1/7 12:39)は満潮なので、位相が揃っていると仮定して最大値を計算
        total_factor = sum(c['factor'] for c in self.consts)
        actual_amp = self.epoch_level - self.msl
        
        # これが「大西港の地形係数」に相当します
        self.base_amp = actual_amp / total_factor

    def _calc_raw(self, target_dt):
        delta_hours = (target_dt - self.epoch_time).total_seconds() / 3600.0
        level = self.msl
        
        for c in self.consts:
            # 各分潮の合成
            theta_rad = math.radians(c['speed'] * delta_hours)
            # 振幅 = 基礎振幅 × 各分潮の比率
            level += (self.base_amp * c['factor']) * math.cos(theta_rad)
            
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
# タイトル
st.markdown("<h4 style='text-align: left; margin-bottom: 5px;'>⚓ Onishi Port Tide Master Pro</h4>", unsafe_allow_html=True)
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

# --- 計算実行 ---
model = AdvancedTideModel()
curr_time, curr_lvl = model.get_current_level()

# --- 情報表示 ---
info_html = f"""
<div style="font-size: 0.9rem; margin-bottom: 10px; color: #555;">
  <b>Period:</b> {st.session_state['view_date'].strftime('%Y/%m/%d')} - <br>
  <span style="color: #0066cc;"><b>Current:</b> {curr_time.strftime('%H:%M')} | <b>Level:</b> {int(curr_lvl)}cm</span>
</div>
"""
st.markdown(info_html, unsafe_allow_html=True)

# --- ナビゲーション ---
days_to_show = 10
col_prev, col_next = st.columns(2)

with col_prev:
    if st.button("<< Prev 10d", use_container_width=True):
        st.session_state['view_date'] -= datetime.timedelta(days=days_to_show)

with col_next:
    if st.button("Next 10d >>", use_container_width=True):
        st.session_state['view_date'] += datetime.timedelta(days=days_to_show)

# --- サイドバー ---
with st.sidebar:
    st.header("⚙️ Settings")
    target_cm = st.number_input("Work Limit Level (cm)", value=120, step=10)
    start_h, end_h = st.slider("Workable Hours", 0, 24, (7, 23), format="%d:00")
    st.markdown("---")
    st.caption("Calculation Model: 10 Constituents (JMA Style)")
    if st.button("Back to Today"):
        st.session_state['view_date'] = now_jst.date()

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
            
            duration = end_t - start_t
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            dur_str = f"{hours}:{minutes:02}"
            
            safe_windows.append({
                "date_str": start_t.strftime('%m/%d (%a)'),
                "start": start_t.strftime("%H:%M"),
                "end": end_t.strftime("%H:%M"),
                "duration": dur_str,
                "graph_label": f"Work\n{dur_str}",
                "min_time": min_time,
                "min_level": min_lvl
            })

# ---------------------------------------------------------
# グラフ描画
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5))

# 線と基準
ax.plot(df['time'], df['level'], color='#0066cc', linewidth=2, label="Level", zorder=2)
ax.axhline(y=target_cm, color='orange', linestyle='--', linewidth=2, label=f"Limit {target_cm}cm", zorder=1)
ax.fill_between(df['time'], df['level'], target_cm, where=df['is_safe'], color='#ffcc00', alpha=0.4, label="Workable")

# 1. 現在位置
graph_start = df['time'].iloc[0]
graph_end = df['time'].iloc[-1]
if graph_start <= curr_time <= graph_end:
    ax.scatter(curr_time, curr_lvl, color='gold', edgecolors='black', s=90, zorder=10)

# 2. ピーク
levels = df['level'].values
times = df['time'].tolist()
for i in range(1, len(levels)-1):
    t, l = times[i], levels[i]
    
    # High Tide
    if levels[i-1] < l and l > levels[i+1] and l > 180:
        ax.scatter(t, l, color='red', marker='^', s=40, zorder=3)
        off_y = 15 if (t.day % 2 == 0) else 30
        ax.annotate(f"{t.strftime('%H:%M')}\n{int(l)}", (t, l), xytext=(0, off_y), 
                    textcoords='offset points', ha='center', fontsize=9, color='#cc0000', fontweight='bold')
    
    # Low Tide
    if levels[i-1] > l and l < levels[i+1] and l < 180:
        ax.scatter(t, l, color='blue', marker='v', s=40, zorder=3)
        off_y = -25 if (t.day % 2 == 0) else -40
        ax.annotate(f"{t.strftime('%H:%M')}\n{int(l)}", (t, l), xytext=(0, off_y), 
                    textcoords='offset points', ha='center', fontsize=9, color='#0000cc', fontweight='bold')

# 3. Workラベル (被らないように下へ)
for win in safe_windows:
    x = win['min_time']
    y = win['min_level']
    ax.annotate(win['graph_label'], (x, y), xytext=(0, -85), 
                textcoords='offset points', ha='center', fontsize=9, 
                color='#b8860b', fontweight='bold',
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.7))

# 軸設定
ax.set_ylabel("Level (cm)")
ax.grid(True, linestyle=':', alpha=0.6)
ax.xaxis.set_major_locator(mdates.DayLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n(%a)'))
ax.set_ylim(bottom=-110)

plt.tight_layout()
st.pyplot(fig)

# ---------------------------------------------------------
# 作業可能時間リスト (コンパクト版)
# ---------------------------------------------------------
st.markdown(f"##### 📋 Workable Time List (Level <= {target_cm}cm)")

if not safe_windows:
    st.warning("No workable time found.")
else:
    res_df = pd.DataFrame(safe_windows)
    display_df = res_df[['date_str', 'start', 'end', 'duration']]
    
    st.dataframe(
        display_df,
        use_container_width=False, 
        hide_index=True,
        column_config={
            "date_str": st.column_config.TextColumn("Date", width="small"),
            "start": st.column_config.TextColumn("Start", width="small"),
            "end": st.column_config.TextColumn("End", width="small"),
            "duration": st.column_config.TextColumn("Time", width="small"),
        }
    )
