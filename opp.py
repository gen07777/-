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
st.set_page_config(layout="wide", page_title="大西港 潮汐アプリ")

# ---------------------------------------------------------
# フォント設定 (文字化け対策・強化版)
# ---------------------------------------------------------
def configure_font():
    """
    Matplotlibで日本語を表示するための強力なフォント設定。
    複数のフォントを優先順位付きで指定し、環境にあるものを自動選択させる。
    """
    # 日本語を表示できる可能性のあるフォントリスト（優先順位順）
    fonts = [
        'Noto Sans CJK JP', 'Meiryo', 'Yu Gothic', 
        'Hiragino Sans', 'HiraKakuProN-W3', 
        'TakaoGothic', 'IPAGothic', 'IPAexGothic', 
        'Arial Unicode MS', 'sans-serif' # 最後の砦
    ]
    # rcParamsにリストで設定することで、Matplotlibが利用可能なフォントを順に試す
    plt.rcParams['font.family'] = fonts

configure_font()

# ---------------------------------------------------------
# セッション状態管理
# ---------------------------------------------------------
if 'view_date' not in st.session_state:
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
        self.msl = 180.0 # 平均水面
        
        # 主要分潮定数
        self.consts = [
            {'name': 'M2', 'amp': 130.0, 'speed': 28.984},
            {'name': 'S2', 'amp': 50.0,  'speed': 30.000},
            {'name': 'K1', 'amp': 38.0,  'speed': 15.041},
            {'name': 'O1', 'amp': 33.0,  'speed': 13.943}
        ]
        
        # 振幅補正
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
st.title("⚓ 大西港")
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

# --- サイドバー設定 ---
with st.sidebar:
    st.header("⚙️ 作業条件設定")
    
    # 条件設定
    target_cm = st.number_input("作業基準潮位 (cm)", value=120, step=10, help="これ以下なら作業可能")
    start_h, end_h = st.slider("作業可能時間帯", 0, 24, (7, 23), format="%d時")
    
    st.markdown("---")
    st.caption("自動計算モード動作中")
    
    if st.button("今日の日付に戻る"):
        st.session_state['view_date'] = now_jst.date()

# --- 計算実行 ---
model = FixedKureTideModel()

# --- 期間切り替え ---
col_n1, col_n2, col_n3 = st.columns([1, 4, 1])
days_to_show = 10

with col_n1:
    if st.button("◀ 前の10日"):
        st.session_state['view_date'] -= datetime.timedelta(days=days_to_show)
with col_n3:
    if st.button("次の10日 ▶"):
        st.session_state['view_date'] += datetime.timedelta(days=days_to_show)
with col_n2:
    st.markdown(f"<h4 style='text-align: center;'>表示期間: {st.session_state['view_date'].strftime('%Y/%m/%d')} 〜 </h4>", unsafe_allow_html=True)

# --- データ生成 ---
df = model.get_dataframe(st.session_state['view_date'], days=days_to_show)

# ---------------------------------------------------------
# 作業可能時間の計算 & リスト作成
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
            # 干潮時刻を取得
            min_time = grp.loc[grp['level'].idxmin(), 'time']
            
            # 作業時間を計算
            duration = end_t - start_t
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            dur_str = f"{hours}時間{minutes:02}分"
            
            safe_windows.append({
                "date_str": start_t.strftime('%m/%d (%a)'),
                "start": start_t.strftime("%H:%M"),
                "end": end_t.strftime("%H:%M"),
                "duration": dur_str,
                "min_time": min_time, # グラフ描画用
                "min_level": min_lvl  # グラフ描画用
            })

# ---------------------------------------------------------
# グラフ描画
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(14, 7))

# 潮位線 & 基準線
ax.plot(df['time'], df['level'], color='#0066cc', linewidth=2, label="潮位", zorder=2)
ax.axhline(y=target_cm, color='orange', linestyle='--', linewidth=2, label=f"基準 {target_cm}cm", zorder=1)
ax.fill_between(df['time'], df['level'], target_cm, where=df['is_safe'], color='#ffcc00', alpha=0.4, label="作業可能")

# --- 1. 現在位置の表示 (黄色い点) ---
curr_time, curr_lvl = model.get_current_level()
graph_start = df['time'].iloc[0]
graph_end = df['time'].iloc[-1]
if graph_start <= curr_time <= graph_end:
    ax.scatter(curr_time, curr_lvl, color='gold', edgecolors='black', s=150, zorder=10, label="現在")
    # 文字化け対策済みフォントで描画
    ax.annotate("現在", (curr_time, curr_lvl), xytext=(0, 20), 
                textcoords='offset points', ha='center', fontsize=10, fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gold", alpha=0.9))

# --- 2. ピークの表示 (満潮・干潮) ---
levels = df['level'].values
times = df['time'].tolist()
for i in range(1, len(levels)-1):
    t, l = times[i], levels[i]
    
    # 満潮プロット (MSLより上)
    if levels[i-1] < l and l > levels[i+1] and l > 180:
        ax.scatter(t, l, color='red', marker='^', s=40, zorder=3)
        off_y = 15 if (t.day % 2 == 0) else 30
        ax.annotate(f"{t.strftime('%H:%M')}\n{int(l)}", (t, l), xytext=(0, off_y), 
                    textcoords='offset points', ha='center', fontsize=9, color='#cc0000', fontweight='bold')

    # 干潮プロット (MSLより下) - 時刻を追加して復活
    if levels[i-1] > l and l < levels[i+1] and l < 180:
        ax.scatter(t, l, color='blue', marker='v', s=40, zorder=3)
        off_y = -25 if (t.day % 2 == 0) else -40
        # 【修正】時刻と潮位を表示
        label = f"{t.strftime('%H:%M')}\n{int(l)}"
        ax.annotate(label, (t, l), xytext=(0, off_y), 
                    textcoords='offset points', ha='center', fontsize=9, color='#0000cc', fontweight='bold')

# --- 3. 作業時間の表示 (干潮の下に黄色文字) ---
for win in safe_windows:
    x_pos = win['min_time']
    y_pos = win['min_level']
    
    # 作業時間テキスト (文字化け対策済み)
    label = win['duration']
    # 干潮ラベルと重ならないよう、さらに下に表示
    ax.annotate(label, (x_pos, y_pos), xytext=(0, -55), 
                textcoords='offset points', ha='center', fontsize=10, 
                color='#b8860b', fontweight='bold',
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.7))

# 軸設定
ax.set_ylabel("潮位 (cm)")
ax.grid(True, linestyle=':', alpha=0.6)
ax.xaxis.set_major_locator(mdates.DayLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n(%a)'))
ax.set_ylim(bottom=-60) # 作業時間表示のために下限を広げる

plt.tight_layout()
st.pyplot(fig)

# ---------------------------------------------------------
# 作業可能時間検討リスト
# ---------------------------------------------------------
st.markdown(f"### 📋 作業可能時間検討リスト (基準 {target_cm}cm以下)")

if not safe_windows:
    st.warning("指定条件で作業できる時間がありません。基準を見直してください。")
else:
    res_df = pd.DataFrame(safe_windows)
    display_df = res_df[['date_str', 'start', 'end', 'duration']]
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "date_str": st.column_config.TextColumn("日付", width="medium"),
            "start": st.column_config.TextColumn("開始時刻", width="medium"),
            "end": st.column_config.TextColumn("終了時刻", width="medium"),
            "duration": st.column_config.TextColumn("作業時間", width="medium", help="この回に確保できる連続作業時間"),
        }
    )
