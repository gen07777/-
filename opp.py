import streamlit as st
import datetime
import math
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager

# ---------------------------------------------------------
# アプリ設定 (必ず一番最初に書く)
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="大西港 潮汐マスター")

# ---------------------------------------------------------
# フォント設定 (文字化け対策)
# ---------------------------------------------------------
def set_japanese_font():
    # Streamlit Cloud (Linux) 環境などで日本語フォントを探す
    possible_fonts = ['Meiryo', 'Yu Gothic', 'HiraKakuProN-W3', 'TakaoGothic', 'IPAGothic', 'Noto Sans CJK JP', 'IPAexGothic']
    found_font = None
    for f in possible_fonts:
        try:
            # フォントがあるかチェック
            font_manager.findfont(f, fallback_to_default=False)
            found_font = f
            break
        except:
            continue
    
    if found_font:
        plt.rcParams['font.family'] = found_font
    else:
        # フォントがない場合は英語フォントにするが、エラーは出さない
        plt.rcParams['font.family'] = 'sans-serif'

set_japanese_font()

# ---------------------------------------------------------
# セッション状態管理 (期間の移動用)
# ---------------------------------------------------------
if 'view_date' not in st.session_state:
    now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)
    st.session_state['view_date'] = now_jst.date()

# ---------------------------------------------------------
# 潮汐計算モデル (呉港データ準拠)
# ---------------------------------------------------------
class KureTideModel:
    def __init__(self, input_high_dt, input_high_level):
        """
        修正点: 変数の定義順序を修正しました。
        """
        # ★ここで先に基準時間をセットする（エラー修正箇所）
        self.base_time = input_high_dt
        
        # 呉港周辺の潮汐定数 (M2, S2, K1, O1)
        self.consts = [
            {'name': 'M2', 'amp': 135.0, 'speed': 28.984},
            {'name': 'S2', 'amp': 52.0,  'speed': 30.000},
            {'name': 'K1', 'amp': 40.0,  'speed': 15.041},
            {'name': 'O1', 'amp': 35.0,  'speed': 13.943}
        ]
        self.msl = 240.0 # 平均水面
        self.height_ratio = 1.0
        
        # 基準時刻での理論値を計算し、入力値(input_high_level)に合わせて倍率を調整
        model_val = self._calc_raw(input_high_dt)
        
        # MSL(240)より高い位置にあるはずなので、その比率で波の高さを補正
        if model_val > self.msl:
            # 振幅部分に対する比率を計算
            theory_amp = model_val - self.msl
            actual_amp = input_high_level - self.msl
            if theory_amp > 0:
                self.height_ratio = actual_amp / theory_amp
        
        # 安全策: 極端な値にならないようガード
        if self.height_ratio <= 0: self.height_ratio = 1.0

    def _calc_raw(self, target_dt):
        # 基準時からの経過時間(時間)
        delta_hours = (target_dt - self.base_time).total_seconds() / 3600.0
        
        level = self.msl
        for c in self.consts:
            # 各分潮を合成
            theta = math.radians(c['speed'] * delta_hours)
            # 振幅に補正比率を掛ける
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
# メイン画面 UI
# ---------------------------------------------------------
st.title("⚓ 大西港 潮汐マスター (呉港データ準拠)")
now_jst = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

# --- サイドバー ---
with st.sidebar:
    st.header("1. 基準データ入力")
    st.caption("画像の表にある「今日の満潮」を入力してください")
    
    input_cal_date = st.date_input("日付", value=now_jst.date())
    
    # 1/7のデータをデフォルトに
    col_in1, col_in2 = st.columns(2)
    with col_in1:
        ref_time = st.time_input("満潮時刻", value=datetime.time(12, 39))
    with col_in2:
        ref_level = st.number_input("満潮潮位", value=342, step=1)

    st.markdown("---")
    st.header("2. 作業条件設定")
    
    # デフォルト: 120cm
    target_cm = st.number_input("作業基準潮位 (cm)", value=120, step=10, help="これ以下なら作業可能")
    
    # デフォルト: 7:00-23:00
    start_h, end_h = st.slider("作業可能時間帯", 0, 24, (7, 23), format="%d時")
    
    st.markdown("---")
    st.write("▼ 表示操作")
    if st.button("今日に戻る"):
        st.session_state['view_date'] = now_jst.date()

# --- 計算実行 ---
base_dt = datetime.datetime.combine(input_cal_date, ref_time)
# ここでエラーが起きないよう修正済み
model = KureTideModel(base_dt, ref_level)

# --- 期間切り替えボタン ---
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

# --- データ取得 ---
df = model.get_dataframe(st.session_state['view_date'], days=days_to_show)

# ---------------------------------------------------------
# 作業可能時間の判定
# ---------------------------------------------------------
df['hour'] = df['time'].dt.hour
# 条件: 潮位 <= 基準値 AND 時間帯内
df['is_safe'] = (df['level'] <= target_cm) & (df['hour'] >= start_h) & (df['hour'] < end_h)

# リスト作成用ロジック
safe_windows = []
if df['is_safe'].any():
    # 連続区間をグループ化
    df['group'] = (df['is_safe'] != df['is_safe'].shift()).cumsum()
    groups = df[df['is_safe']].groupby('group')
    
    for _, grp in groups:
        start_t = grp['time'].iloc[0]
        end_t = grp['time'].iloc[-1]
        
        # 10分以上続く場合のみリストアップ
        if (end_t - start_t).total_seconds() >= 600:
            min_lvl = grp['level'].min()
            # その時間帯の中での最干潮時刻を探す
            min_row = grp.loc[grp['level'].idxmin()]
            
            safe_windows.append({
                "date_obj": start_t.date(),
                "date_str": start_t.strftime('%m/%d (%a)'),
                "start": start_t.strftime("%H:%M"),
                "end": end_t.strftime("%H:%M"),
                "low_time": min_row['time'].strftime("%H:%M"),
                "min_level": f"{int(min_lvl)}cm"
            })

# ---------------------------------------------------------
# グラフ描画
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(12, 6))

# 線
ax.plot(df['time'], df['level'], color='#0066cc', linewidth=2, label="Level", zorder=2)
# 基準線
ax.axhline(y=target_cm, color='orange', linestyle='--', linewidth=2, label=f"Limit {target_cm}cm", zorder=1)
# 塗りつぶし
ax.fill_between(df['time'], df['level'], target_cm, where=df['is_safe'], color='#ffcc00', alpha=0.5)

# ピーク表示 (文字重なり対策のため、極小値のみ表示するなど工夫)
# ここではご要望通り「干潮の時刻と潮位」を表示
window = 10
df['is_low'] = df['level'].rolling(window=15, center=True).apply(lambda x: 1 if x[7] == min(x) else 0, raw=True)
low_tides = df[df['is_low'] == 1]

for i, row in low_tides.iterrows():
    # 文字が重なりにくいよう、交互に高さを変える
    y_offset = -20 if i % 2 == 0 else -40
    
    # マーカー
    ax.scatter(row['time'], row['level'], color='blue', marker='v', s=30, zorder=3)
    
    # ラベル (文字化け回避のため英数字のみ推奨だが、フォント設定済みなら日本語も可)
    # ここでは見やすさ重視で時刻と潮位のみ
    label = f"{row['time'].strftime('%H:%M')}\n{int(row['level'])}"
    ax.annotate(label, (row['time'], row['level']), xytext=(0, y_offset), 
                textcoords='offset points', ha='center', fontsize=9, color='#000088', fontweight='bold')

# 軸設定
ax.set_ylabel("Level (cm)")
ax.grid(True, linestyle=':', alpha=0.6)
ax.xaxis.set_major_locator(mdates.DayLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))

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
    
    # 必要な列を選んで表示
    st.dataframe(
        res_df[['date_str', 'start', 'end', 'min_level', 'low_time']],
        use_container_width=True,
        hide_index=True,
        column_config={
            "date_str": st.column_config.TextColumn("日付", width="small"),
            "start": st.column_config.TextColumn("作業開始", width="small"),
            "end": st.column_config.TextColumn("作業終了", width="small"),
            "min_level": st.column_config.TextColumn("最干潮位", width="small"),
            "low_time": st.column_config.TextColumn("干潮時刻", width="small"),
        }
    )
