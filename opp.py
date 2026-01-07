import streamlit as st
import datetime
import math
import pandas as pd
import plotly.graph_objects as go # インタラクティブグラフ用

# ---------------------------------------------------------
# アプリ設定
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="大西港 潮汐モニター (改)")

# ---------------------------------------------------------
# 計算ロジック (シンプル・サインカーブ)
# ---------------------------------------------------------
class SimpleTideModel:
    def __init__(self, high_time_dt, high_level, low_level):
        """
        基準日時(満潮)と潮位から、向こう数日間の潮汐カーブを生成する
        """
        self.high_time_dt = high_time_dt
        self.high_level = high_level
        self.mean_level = (high_level + low_level) / 2
        self.amplitude = (high_level - low_level) / 2
        # 平均潮汐周期 (約12時間25分 = 745.2分)
        self.period_minutes = 745.2

    def calculate_level(self, target_dt):
        # 基準からの経過時間(分)
        delta_minutes = (target_dt - self.high_time_dt).total_seconds() / 60.0
        # コサイン波計算
        theta = (delta_minutes / self.period_minutes) * 2 * math.pi
        return self.mean_level + self.amplitude * math.cos(theta)

    def get_period_data(self, start_dt, end_dt, interval_minutes=10):
        data = []
        curr = start_dt
        # 少し余裕を持って計算
        while curr <= end_dt:
            lvl = self.calculate_level(curr)
            data.append({"time": curr, "level": lvl})
            curr += datetime.timedelta(minutes=interval_minutes)
        return data

# ---------------------------------------------------------
# メイン画面
# ---------------------------------------------------------
st.title("⚓ 大西港 潮汐モニター (改)")

# 現在時刻
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
now_jst = now_jst.replace(tzinfo=None, second=0, microsecond=0)

# --- サイドバー設定 ---
with st.sidebar:
    st.header("⚙️ 基準データ入力")
    st.caption("画像の表にある数値を入力してください")
    
    input_date = st.date_input("日付", value=now_jst.date())
    
    # 画像値(1/7)をデフォルトに
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        high_time_val = st.time_input("満潮時刻", value=datetime.time(12, 39))
    with col_t2:
        high_level_val = st.number_input("満潮潮位", value=342, step=1)
    
    low_level_val = st.number_input("干潮潮位 (波の大きさ基準)", value=16, step=1)
    
    st.markdown("---")
    st.write("▼ 表示期間切り替え")
    view_mode = st.radio("グラフの範囲", ["今日 (1日)", "短期 (3日)", "中期 (10日)"], index=0)

# --- ターゲット潮位設定 ---
col_tgt, col_info = st.columns([1, 2])
with col_tgt:
    target_cm = st.number_input("作業基準潮位 (cm)", value=150, step=10, help="この線より下を色付けします")

# --- データ生成 ---
# 基準点作成
base_high_dt = datetime.datetime.combine(input_date, high_time_val)
model = SimpleTideModel(base_high_dt, high_level_val, low_level_val)

# 表示範囲の決定
start_plot_dt = datetime.datetime.combine(input_date, datetime.time(0, 0))

if view_mode == "今日 (1日)":
    end_plot_dt = start_plot_dt + datetime.timedelta(days=1) - datetime.timedelta(minutes=1)
    date_format = "%H:%M" # 時間だけ表示
elif view_mode == "短期 (3日)":
    end_plot_dt = start_plot_dt + datetime.timedelta(days=3)
    date_format = "%d日 %H時"
else: # 10日
    end_plot_dt = start_plot_dt + datetime.timedelta(days=10)
    date_format = "%m/%d"

# データ取得
raw_data = model.get_period_data(start_plot_dt, end_plot_dt)
df = pd.DataFrame(raw_data)

# 現在の状態計算
current_level = model.calculate_level(now_jst)
prev_level = model.calculate_level(now_jst - datetime.timedelta(minutes=5))

# 状態メッセージ
if current_level > prev_level + 0.1:
    status_msg = "上げ潮 ↗ (満ちています)"
    status_color = "#d62728" # 赤
elif current_level < prev_level - 0.1:
    status_msg = "下げ潮 ↘ (引いています)"
    status_color = "#1f77b4" # 青
else:
    status_msg = "潮止まり (ピーク)"
    status_color = "green"

with col_info:
    st.markdown(f"### 現在の状態: <span style='color:{status_color}'>{status_msg}</span>", unsafe_allow_html=True)
    st.markdown(f"現在時刻: **{now_jst.strftime('%H:%M')}** ／ 推定潮位: **{current_level:.0f}cm**")

# ---------------------------------------------------------
# Plotlyによるグラフ描画 (ここが修正のキモ)
# ---------------------------------------------------------
fig = go.Figure()

# 1. 潮位線 (メイン)
fig.add_trace(go.Scatter(
    x=df['time'],
    y=df['level'],
    mode='lines',
    name='推算潮位',
    line=dict(color='#1f77b4', width=3),
    hovertemplate='%{x|%m/%d %H:%M}<br>潮位: %{y:.0f}cm<extra></extra>' # マウスオーバー時の表示
))

# 2. 基準線 (Target Line)
fig.add_hline(y=target_cm, line_dash="dash", line_color="orange", annotation_text=f"基準 {target_cm}cm")

# 3. 現在地 (黄色い丸)
if start_plot_dt <= now_jst <= end_plot_dt:
    fig.add_trace(go.Scatter(
        x=[now_jst],
        y=[current_level],
        mode='markers+text',
        name='現在',
        marker=dict(color='gold', size=15, line=dict(color='black', width=2)),
        text=[f"現在<br>{current_level:.0f}cm"],
        textposition="top center",
        hoverinfo='skip'
    ))

# レイアウト設定 (見やすさ調整)
fig.update_layout(
    title=f"潮汐グラフ ({view_mode})",
    height=500, # 高さを固定して大きすぎないように
    xaxis=dict(
        tickformat=date_format,
        showgrid=True,
        gridcolor='lightgray',
        zeroline=False,
    ),
    yaxis=dict(
        title="潮位 (cm)",
        showgrid=True,
        gridcolor='lightgray',
        zeroline=False,
    ),
    plot_bgcolor='white', # 背景を白く
    font=dict(size=14),   # 文字サイズ調整
    hovermode="x unified" # ホバーしたときに縦線が出る
)

# 基準線以下の塗りつぶし (Plotlyでの近似表現)
# 複雑になるため、今回は「背景色」ではなく「基準線」で見分けやすくしています

st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------
# 詳細データテーブル（必要な時だけ開く）
# ---------------------------------------------------------
with st.expander("詳細な数値データを見る"):
    st.dataframe(df.style.format({"level": "{:.1f}cm", "time": "{:%m/%d %H:%M}"}))
