import streamlit as st
import datetime
import math
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ---------------------------------------------------------
# アプリ設定
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="大西港 潮汐計算機 (シンプル・ロックオン版)")

# ---------------------------------------------------------
# 新・計算ロジック (入力された時刻にサインカーブを強制的に合わせる)
# ---------------------------------------------------------
class SimpleTideModel:
    def __init__(self, high_time_dt, high_level, low_level):
        """
        ユーザーが入力した「満潮時間」と「潮位」を基準に、
        12時間25分周期のきれいな波を生成する
        """
        self.high_time_dt = high_time_dt
        self.high_level = high_level
        self.mean_level = (high_level + low_level) / 2
        self.amplitude = (high_level - low_level) / 2
        
        # 潮汐の平均周期 (約12.42時間 = 745.2分)
        self.period_minutes = 745.2

    def calculate_level(self, target_dt):
        # 基準（満潮）からの経過時間（分）
        delta_minutes = (target_dt - self.high_time_dt).total_seconds() / 60.0
        
        # コサイン波で計算 (0=満潮, 180=干潮)
        # 角度 = (経過時間 / 周期) * 360度 * ラジアン変換
        theta = (delta_minutes / self.period_minutes) * 2 * math.pi
        
        # レベル = 平均 + 振幅 * cos(角度)
        return self.mean_level + self.amplitude * math.cos(theta)

    def get_period_data(self, start_dt, end_dt, interval_minutes=10):
        data = []
        curr = start_dt
        while curr <= end_dt:
            lvl = self.calculate_level(curr)
            data.append({"raw_time": curr, "Level_cm": lvl})
            curr += datetime.timedelta(minutes=interval_minutes)
        return data

# ---------------------------------------------------------
# メイン画面
# ---------------------------------------------------------
st.title("⚓ 大西港 潮汐モニター (修正版)")
st.markdown("""
複雑な計算を排除し、**入力された満潮時刻にグラフを強制同期**させました。
これで確実に「今の状態」が正しく表示されます。
""")

# 現在時刻 (JST)
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
now_jst = now_jst.replace(tzinfo=None, second=0, microsecond=0)

# --- サイドバー: 正解データの入力 ---
with st.sidebar:
    st.header("1. 今日のデータ入力")
    st.caption("画像(オレンジの表)の数値を入力してください")
    
    # デフォルトを画像の値(1/7)に設定
    input_date = st.date_input("日付", value=now_jst.date())
    
    # 画像より: 満潮 12:39, 342cm
    high_time_val = st.time_input("満潮時刻", value=datetime.time(12, 39))
    high_level_val = st.number_input("満潮潮位 (cm)", value=342, step=1)
    
    # 画像より: 干潮 16cm (振幅計算用)
    low_level_val = st.number_input("干潮潮位 (cm)", value=16, step=1, help="波の大きさを決めるために使います")

    st.success(f"設定: {high_time_val.strftime('%H:%M')} にピークを合わせます")

# --- メインエリア ---
col1, col2 = st.columns(2)
with col1:
    # グラフ表示範囲（今日を中心に前後）
    st.markdown("##### 表示設定")
    target_cm = st.number_input("基準潮位(cm)", value=150, step=10)
    
with col2:
    start_hour, end_hour = st.slider("活動時間帯", 0, 24, (6, 19), format="%d時")

# --- 計算実行 ---
# 基準となる満潮日時を作成
base_high_dt = datetime.datetime.combine(input_date, high_time_val)

# モデル初期化
model = SimpleTideModel(base_high_dt, high_level_val, low_level_val)

# グラフ用データ生成（今日一日）
graph_start = datetime.datetime.combine(input_date, datetime.time(0, 0))
graph_end = datetime.datetime.combine(input_date, datetime.time(23, 59))
data = model.get_period_data(graph_start, graph_end)
df = pd.DataFrame(data)

# 現在の潮位を取得
current_level = model.calculate_level(now_jst)
# 5分前の潮位と比較して「上げ/下げ」判定
prev_level = model.calculate_level(now_jst - datetime.timedelta(minutes=5))

# 状態判定ロジック
if current_level > prev_level + 0.1:
    status_msg = "上げ潮 ↗ (満ちています)"
    status_color = "red"
elif current_level < prev_level - 0.1:
    status_msg = "下げ潮 ↘ (引いています)"
    status_color = "blue"
else:
    status_msg = "潮止まり (ピーク)"
    status_color = "green"

# --- 画面描画 ---
st.subheader(f"現在の状態: :{status_color}[{status_msg}]")
st.markdown(f"現在時刻: **{now_jst.strftime('%H:%M')}** / 推定潮位: **{current_level:.0f}cm**")
st.caption(f"※満潮（{high_time_val.strftime('%H:%M')}）に向かって上昇中です" if status_color == "red" else "")

fig, ax = plt.subplots(figsize=(12, 6))

# 線グラフ
ax.plot(df['raw_time'], df['Level_cm'], color='#1f77b4', linewidth=3, label="潮位")
ax.axhline(y=target_cm, color='orange', linestyle='--', label=f"基準 {target_cm}cm")

# 塗りつぶし
hours = df['raw_time'].dt.hour
is_time_ok = (hours >= start_hour) & (hours < end_hour)
is_level_ok = (df['Level_cm'] <= target_cm)
ax.fill_between(df['raw_time'], df['Level_cm'], target_cm, 
                where=(is_level_ok & is_time_ok), color='orange', alpha=0.3)

# 現在地プロット (黄色い丸)
if graph_start <= now_jst <= graph_end:
    ax.scatter(now_jst, current_level, color='gold', s=250, zorder=10, edgecolors='black', linewidth=2)
    ax.annotate(f"現在\n{now_jst.strftime('%H:%M')}\n{current_level:.0f}cm", 
                xy=(now_jst, current_level), xytext=(0, 50),
                textcoords='offset points', ha='center', va='bottom',
                fontsize=12, fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black"))

# 満潮ピーク時刻のプロット
ax.scatter(base_high_dt, high_level_val, color='red', marker='^', s=100, zorder=5)
ax.text(base_high_dt, high_level_val + 10, f"満潮\n{base_high_dt.strftime('%H:%M')}", 
        ha='center', va='bottom', fontsize=10, color='darkred', fontweight='bold')

# グラフ装飾
ax.set_ylabel("潮位 (cm)")
ax.grid(True, linestyle=':', alpha=0.6)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
ax.set_title(f"{input_date.strftime('%Y/%m/%d')} の潮汐グラフ", fontsize=14)

st.pyplot(fig)

with st.expander("詳細データを見る"):
    st.dataframe(df)
