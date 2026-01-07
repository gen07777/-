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
st.set_page_config(layout="wide", page_title="大西港 潮汐マスター (修正完了版)")

# ---------------------------------------------------------
# フォント設定 (日本語対応)
# ---------------------------------------------------------
def set_japanese_font():
    possible_fonts = ['Meiryo', 'Yu Gothic', 'HiraKakuProN-W3', 'TakaoGothic', 'IPAGothic', 'Noto Sans CJK JP', 'IPAexGothic']
    for f in possible_fonts:
        try:
            font_manager.findfont(f, fallback_to_default=False)
            plt.rcParams['font.family'] = f
            return
        except:
            continue
    plt.rcParams['font.family'] = 'sans-serif'

set_japanese_font()

# ---------------------------------------------------------
# セッション状態管理 (期間移動用)
# ---------------------------------------------------------
if 'view_date' not in st.session_state:
    # デフォルトで今日を表示
    now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    st.session_state['view_date'] = now_jst.date()

# ---------------------------------------------------------
# 潮汐計算モデル (呉港データ・1/7基準)
# ---------------------------------------------------------
class FixedKureTideModel:
    def __init__(self):
        """
        1月7日 12:39 満潮 342cm (大西港/呉実績) を基準(Epoch)として、
        調和分解モデルで将来の潮汐を予測する。
        """
        # 基準日時 (1/7 12:39)
        self.epoch_time = datetime.datetime(2026, 1, 7, 12, 39)
        self.epoch_level = 342.0
        
        # 修正: 平均水面(MSL)を180cmに設定 (以前の240cmは高すぎた)
        self.msl = 180.0
        
        # 呉港周辺の主要分潮 (振幅cm, 角速度deg/h)
        # 位相(phase)は基準時(1/7 12:39)をピーク(0度)と仮定して相対計算
        self.consts = [
            {'name': 'M2', 'amp': 130.0, 'speed': 28.984}, # 主太陰半日周潮
            {'name': 'S2', 'amp': 50.0,  'speed': 30.000}, # 主太陽半日周潮
            {'name': 'K1', 'amp': 38.0,  'speed': 15.041}, # 日周潮
            {'name': 'O1', 'amp': 33.0,  'speed': 13.943}  # 日周潮
        ]
        
        # 振幅の補正係数を計算
        # 基準時の理論上の振幅合計
        total_amp_theory = sum(c['amp'] for c in self.consts)
        # 実際の振幅 (満潮342 - MSL180 = 162)
        actual_amp = self.epoch_level - self.msl
        
        # 比率を算出 (約0.6〜0.7になるはず)
        self.scale_factor = actual_amp / total_amp_theory

    def _calc_raw(self, target_dt):
        # 基準時からの経過時間(時間)
        delta_hours = (target_dt - self.epoch_time).total_seconds() / 3600.0
        
        # ベースは平均水面
        level = self.msl
        
        for c in self.consts:
            # 基準時をピーク(cos(0)=1)とするため、経過時間分だけ位相を進める
            theta_deg = c['speed'] * delta_hours
            theta_rad = math.radians(theta_deg)
            
            # 振幅 × 補正係数 × cos(位相)
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

# ---------------------------------------------------------
# メイン画面 UI
# ---------------------------------------------------------
st.title("⚓ 大西港 潮汐マスター (自動計算版)")
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

# --- サイドバー設定 (入力不要化) ---
with st.sidebar:
    st.header("⚙️ 設定")
    
    # 作業条件設定
    target_cm = st.number_input("作業基準潮位 (cm)", value=120, step=10, help="この高さ以下なら作業可能")
    start_h, end_h = st.slider("作業可能時間帯", 0, 24, (7, 23), format="%d時")
    
    st.markdown("---")
    st.info("※1月7日の実測値を基準に自動計算しています。毎日の入力は不要です。")
    
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
# 作業可能時間の判定
# ---------------------------------------------------------
df['hour'] = df['time'].dt.hour
df['is_safe'] = (df['level'] <= target_cm) & (df['hour'] >= start_h) & (df['hour'] < end_h)

# リスト作成ロジック
safe_windows = []
if df['is_safe'].any():
    df['group'] = (df['is_safe'] != df['is_safe'].shift()).cumsum()
    groups = df[df['is_safe']].groupby('group')
    
    for _, grp in groups:
        start_t = grp['time'].iloc[0]
        end_t = grp['time'].iloc[-1]
        if (end_t - start_t).total_seconds() >= 600:
            min_lvl = grp['level'].min()
            min_row = grp.loc[grp['level'].idxmin()]
            safe_windows.append({
                "date_str": start_t.strftime('%m/%d (%a)'),
                "start": start_t.strftime("%H:%M"),
                "end": end_t.strftime("%H:%M"),
                "low_time": min_row['time'].strftime("%H:%M"),
                "min_level": f"{int(min_lvl)}cm"
            })

# ---------------------------------------------------------
# グラフ描画 (ピーク検出ロジック改善)
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(14, 6))

# 潮位線 & 基準線
ax.plot(df['time'], df['level'], color='#0066cc', linewidth=2, label="潮位", zorder=2)
ax.axhline(y=target_cm, color='orange', linestyle='--', linewidth=2, label=f"基準 {target_cm}cm", zorder=1)
ax.fill_between(df['time'], df['level'], target_cm, where=df['is_safe'], color='#ffcc00', alpha=0.5, label="作業可能")

# --- ピーク検出 (極値判定) ---
# データをnumpy配列に変換して高速処理
levels = df['level'].values
times = df['time'].tolist()
n = len(levels)

# 極大(満潮)・極小(干潮)を探す
high_indices = []
low_indices = []

# 前後関係を見てピークを探す (ウィンドウ幅3)
for i in range(1, n-1):
    # 満潮判定: 前後より高く、かつ絶対値がある程度高い(MSL以上)
    if levels[i-1] < levels[i] and levels[i] > levels[i+1]:
        if levels[i] > 180: # ノイズ除去のためMSL以上のみ
            high_indices.append(i)
    
    # 干潮判定: 前後より低く、かつ絶対値がある程度低い(MSL以下)
    if levels[i-1] > levels[i] and levels[i] < levels[i+1]:
        if levels[i] < 220: # ノイズ除去
            low_indices.append(i)

# 満潮ラベル描画
for i in high_indices:
    t = times[i]
    l = levels[i]
    ax.scatter(t, l, color='red', marker='^', s=40, zorder=3)
    # 文字重なりを防ぐため交互に高さを変える
    offset = 15 if (t.day % 2 == 0) else 30
    ax.annotate(f"{t.strftime('%H:%M')}\n{int(l)}", (t, l), xytext=(0, offset), 
                textcoords='offset points', ha='center', fontsize=9, color='#cc0000', fontweight='bold')

# 干潮ラベル描画
for i in low_indices:
    t = times[i]
    l = levels[i]
    ax.scatter(t, l, color='blue', marker='v', s=40, zorder=3)
    offset = -25 if (t.day % 2 == 0) else -40
    ax.annotate(f"{t.strftime('%H:%M')}\n{int(l)}", (t, l), xytext=(0, offset), 
                textcoords='offset points', ha='center', fontsize=9, color='#0000cc', fontweight='bold')

# 軸設定
ax.set_ylabel("潮位 (cm)")
ax.grid(True, linestyle=':', alpha=0.6)
ax.xaxis.set_major_locator(mdates.DayLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n(%a)'))
ax.set_ylim(bottom=-20) # 干潮が見切れないように下限を設定

plt.title(f"大西港 潮汐グラフ ({st.session_state['view_date'].strftime('%Y/%m/%d')} 〜)", fontsize=14)
plt.tight_layout()
st.pyplot(fig)

# ---------------------------------------------------------
# リスト表示
# ---------------------------------------------------------
st.markdown(f"### 👷 作業可能時間リスト (潮位 {target_cm}cm以下)")

if not safe_windows:
    st.warning("指定条件で作業できる時間がありません。基準を見直してください。")
else:
    res_df = pd.DataFrame(safe_windows)
    st.dataframe(
        res_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "date_str": st.column_config.TextColumn("日付", width="small"),
            "start": st.column_config.TextColumn("開始", width="small"),
            "end": st.column_config.TextColumn("終了", width="small"),
            "min_level": st.column_config.TextColumn("最干潮位", width="small"),
            "low_time": st.column_config.TextColumn("干潮時刻", width="small"),
        }
    )
