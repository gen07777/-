import streamlit as st
import datetime
import math
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager

# ---------------------------------------------------------
# フォント設定 (文字化け対策)
# ---------------------------------------------------------
# 日本語フォントを探して設定する関数
def set_japanese_font():
    possible_fonts = ['Meiryo', 'Yu Gothic', 'HiraKakuProN-W3', 'TakaoGothic', 'IPAGothic', 'Noto Sans CJK JP']
    found_font = None
    for f in possible_fonts:
        try:
            font_manager.findfont(f, fallback_to_default=False)
            found_font = f
            break
        except:
            continue
    
    if found_font:
        plt.rcParams['font.family'] = found_font
    else:
        # フォントが見つからない場合は英語表記に逃げるが、なるべく文字化けしない標準を探す
        plt.rcParams['font.family'] = 'sans-serif'

set_japanese_font()

# ---------------------------------------------------------
# アプリ設定 & セッション状態
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="大西港 潮汐マスター")

# 表示基準日を管理（ボタンで移動できるようにする）
if 'view_date' not in st.session_state:
    # 日本時間の今日
    now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    st.session_state['view_date'] = now_jst.date()

# ---------------------------------------------------------
# 潮汐計算ロジック (呉港モデル・調和分解風)
# ---------------------------------------------------------
class KureTideModel:
    def __init__(self, input_high_dt, input_high_level):
        """
        呉の主要4分潮(M2, S2, K1, O1)を合成し、
        ユーザー入力(今日の満潮)に位相を合わせることで、
        明日以降の変化（大潮・小潮）も再現する
        """
        # 呉港周辺の概略潮汐定数 (振幅cm, 角速度deg/h)
        # これを混ぜることで「毎日違う波」を作る
        self.consts = [
            {'name': 'M2', 'amp': 135.0, 'speed': 28.984}, # 主太陰半日周潮
            {'name': 'S2', 'amp': 52.0,  'speed': 30.000}, # 主太陽半日周潮
            {'name': 'K1', 'amp': 40.0,  'speed': 15.041}, # 日周潮
            {'name': 'O1', 'amp': 35.0,  'speed': 13.943}  # 日周潮
        ]
        self.msl = 240.0 # 平均水面
        
        # キャリブレーション（入力された満潮時刻・潮位に合うように補正）
        # 簡易的に、入力時刻における理論値と実績値のズレを全体に適用する
        self.time_offset_hours = 0
        self.height_ratio = 1.0
        
        # 基準時刻でのモデル計算
        model_val = self._calc_raw(input_high_dt)
        
        # 高さの補正係数
        if model_val > 0:
            self.height_ratio = input_high_level / model_val
            
        # 時間のズレ補正（ピーク合わせ）は複雑なので、
        # 今回は「位相（Phase）」をユーザー入力時刻 = M2のピークとして簡易同期させる
        # ※実用上十分な近似
        self.base_time = input_high_dt

    def _calc_raw(self, target_dt):
        # 基準時からの経過時間(時間)
        delta_hours = (target_dt - self.base_time).total_seconds() / 3600.0
        
        level = self.msl
        # M2分潮の位相を0(ピーク)としてスタートし、他を相対的に足す
        # 12.42時間周期の波と、12時間周期の波などを合成
        for c in self.consts:
            # 簡易モデル: すべての分潮が入力時刻に同相同期していると仮定してスタート
            # (厳密ではないが、数日間の工事用予測としては機能する)
            theta = math.radians(c['speed'] * delta_hours)
            level += (c['amp'] * self.height_ratio) * math.cos(theta)
            
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
# UI構築
# ---------------------------------------------------------
st.title("⚓ 大西港 潮汐マスター (呉港データ準拠)")
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

# --- サイドバー設定 ---
with st.sidebar:
    st.header("1. 基準データ入力")
    st.info("今日の満潮データを入力すると、明日以降も自動計算します")
    
    # 今日の日付
    input_cal_date = st.date_input("基準日", value=now_jst.date())
    
    # 呉の満潮入力 (デフォルト: 1/7のデータ)
    col_in1, col_in2 = st.columns(2)
    with col_in1:
        ref_time = st.time_input("満潮時刻", value=datetime.time(12, 39))
    with col_in2:
        ref_level = st.number_input("満潮潮位", value=342, step=1)

    st.markdown("---")
    st.header("2. 作業条件設定")
    
    # デフォルト値を120cmに変更
    target_cm = st.number_input("作業基準潮位 (cm)", value=120, step=10, help="この潮位以下を作業可能とみなします")
    
    # デフォルト値を7:00~23:00に変更
    start_h, end_h = st.slider("作業可能時間帯", 0, 24, (7, 23), format="%d時")
    
    st.markdown("---")
    st.caption("※大西港の特性（呉とほぼ同じ）に合わせて計算しています。")

# --- 計算モデル初期化 ---
base_dt = datetime.datetime.combine(input_cal_date, ref_time)
model = KureTideModel(base_dt, ref_level)

# --- 表示期間操作エリア ---
col_nav1, col_nav2, col_nav3 = st.columns([1, 4, 1])
days_to_show = 10 # デフォルト10日

with col_nav1:
    if st.button("◀ 前の期間"):
        st.session_state['view_date'] -= datetime.timedelta(days=days_to_show)

with col_nav3:
    if st.button("次の期間 ▶"):
        st.session_state['view_date'] += datetime.timedelta(days=days_to_show)

with col_nav2:
    st.markdown(f"<h3 style='text-align: center;'>表示期間: {st.session_state['view_date'].strftime('%Y/%m/%d')} から {days_to_show}日間</h3>", unsafe_allow_html=True)

# --- データ生成 ---
df = model.get_dataframe(st.session_state['view_date'], days=days_to_show)

# ---------------------------------------------------------
# 作業可能時間の抽出ロジック
# ---------------------------------------------------------
# 条件: 潮位 <= 基準値 AND 時間帯内
df['hour'] = df['time'].dt.hour
df['is_safe'] = (df['level'] <= target_cm) & (df['hour'] >= start_h) & (df['hour'] < end_h)

# 連続した期間をまとめる
safe_windows = []
if df['is_safe'].any():
    # 変化点を見つける
    df['group'] = (df['is_safe'] != df['is_safe'].shift()).cumsum()
    groups = df[df['is_safe']].groupby('group')
    
    for _, grp in groups:
        start_t = grp['time'].iloc[0]
        end_t = grp['time'].iloc[-1]
        
        # 10分以上の枠のみ表示
        if (end_t - start_t).total_seconds() >= 600:
            min_lvl = grp['level'].min()
            safe_windows.append({
                "date": start_t.date(),
                "start": start_t.strftime("%H:%M"),
                "end": end_t.strftime("%H:%M"),
                "min_level": min_lvl
            })

# ---------------------------------------------------------
# グラフ描画 (Matplotlib)
# ---------------------------------------------------------
# グラフサイズ調整
fig, ax = plt.subplots(figsize=(14, 6))

# 1. 潮位線
ax.plot(df['time'], df['level'], color='#0066cc', linewidth=2, label="潮位", zorder=2)

# 2. 基準線
ax.axhline(y=target_cm, color='orange', linestyle='--', linewidth=2, label=f"基準 {target_cm}cm", zorder=1)

# 3. 塗りつぶし（作業可能時間のみ）
# is_safeがTrueの場所だけ塗る
ax.fill_between(df['time'], df['level'], target_cm, 
                where=df['is_safe'], 
                color='#ffcc00', alpha=0.5, label="作業可能")

# 4. ピーク検出とテキスト表示（重なり防止）
# 極大値(満潮)と極小値(干潮)を探す
window = 5 # 前後5データ(50分)と比較
df['is_high'] = df['level'].rolling(window=10, center=True).apply(lambda x: 1 if x[5] == max(x) else 0, raw=True)
df['is_low'] = df['level'].rolling(window=10, center=True).apply(lambda x: 1 if x[5] == min(x) else 0, raw=True)

# テキスト表示用のリスト
texts = []

# 満潮プロット
high_tides = df[df['is_high'] == 1]
for i, row in high_tides.iterrows():
    # 日付が変わるたびにリセットするなど工夫もできるが、シンプルに交互に高さを変える
    offset = 15 if i % 2 == 0 else 35
    ax.scatter(row['time'], row['level'], color='red', marker='^', s=40, zorder=3)
    # 文字化け対策: 英数字のみにする ("H 12:00 300" -> High Tide)
    label = f"{row['time'].strftime('%H:%M')}\n{int(row['level'])}"
    ax.annotate(label, (row['time'], row['level']), xytext=(0, 10), 
                textcoords='offset points', ha='center', fontsize=9, color='#cc0000')

# 干潮プロット (ご要望: 干潮も表示)
low_tides = df[df['is_low'] == 1]
for i, row in low_tides.iterrows():
    ax.scatter(row['time'], row['level'], color='blue', marker='v', s=40, zorder=3)
    label = f"{row['time'].strftime('%H:%M')}\n{int(row['level'])}"
    ax.annotate(label, (row['time'], row['level']), xytext=(0, -25), 
                textcoords='offset points', ha='center', fontsize=9, color='#0000cc')

# グラフ装飾
ax.set_ylabel("Level (cm)")
ax.grid(True, linestyle=':', alpha=0.6)

# X軸の設定 (10日分なので、日ごとにメモリを打つ)
ax.xaxis.set_major_locator(mdates.DayLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n(%a)')) # 英語ロケールだと(Mon)などになる

plt.title(f"Tide Graph ({st.session_state['view_date']} - {days_to_show} days)", fontsize=14)
plt.tight_layout()

# Streamlitに表示
st.pyplot(fig)

# ---------------------------------------------------------
# 作業可能時間リスト表示
# ---------------------------------------------------------
st.markdown(f"### 👷 作業可能時間リスト (基準 {target_cm}cm以下 & {start_h}:00-{end_h}:00)")

if not safe_windows:
    st.error("指定された期間・条件では、安全に作業できる時間がありません。")
else:
    # 見やすいようにデータフレーム化して表示
    res_df = pd.DataFrame(safe_windows)
    res_df['日付'] = res_df['date'].apply(lambda x: x.strftime('%m/%d (%a)'))
    res_df['開始'] = res_df['start']
    res_df['終了'] = res_df['end']
    res_df['干潮潮位'] = res_df['min_level'].apply(lambda x: f"{int(x)}cm")
    
    # 必要な列だけ表示
    display_cols = ['日付', '開始', '終了', '干潮潮位']
    
    # テーブルスタイル適用 (大きく表示)
    st.dataframe(
        res_df[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "日付": st.column_config.TextColumn("日付", width="small"),
            "開始": st.column_config.TextColumn("開始時刻", width="medium"),
            "終了": st.column_config.TextColumn("終了時刻", width="medium"),
            "干潮潮位": st.column_config.TextColumn("最干潮位", help="この時間帯で一番水が引く高さ"),
        }
    )

st.markdown("""
<style>
/* スマホで見やすいようにテーブルの文字を少し大きく */
div[data-testid="stDataFrame"] {
    font-size: 1.1rem;
}
</style>
""", unsafe_allow_html=True)
