import streamlit as st
import datetime
import math
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ---------------------------------------------------------
# アプリ設定
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="大西港 潮汐モニター (スマホ対応版)")

# ---------------------------------------------------------
# 計算ロジック (シンプル・サインカーブ)
# ---------------------------------------------------------
class SimpleTideModel:
    def __init__(self, high_time_dt, high_level, low_level):
        self.high_time_dt = high_time_dt
        self.high_level = high_level
        self.mean_level = (high_level + low_level) / 2
        self.amplitude = (high_level - low_level) / 2
        self.period_minutes = 745.2 # 平均潮汐周期

    def calculate_level(self, target_dt):
        delta_minutes = (target_dt - self.high_time_dt).total_seconds() / 60.0
        theta = (delta_minutes / self.period_minutes) * 2 * math.pi
        return self.mean_level + self.amplitude * math.cos(theta)

    def get_period_data(self, start_dt, end_dt, interval_minutes=10):
        data = []
        curr = start_dt
        while curr <= end_dt:
            lvl = self.calculate_level(curr)
            data.append({"time": curr, "level": lvl})
            curr += datetime.timedelta(minutes=interval_minutes)
        return data

# ---------------------------------------------------------
# メイン画面
# ---------------------------------------------------------
st.title("⚓ 大西港 潮汐モニター (スマホ対応版)")

# 現在時刻 (JST)
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
now_jst = now_jst.replace(tzinfo=None, second=0, microsecond=0)

# --- サイドバー ---
with st.sidebar:
    st.header("⚙️ データ入力")
    
    input_date = st.date_input("日付", value=now_jst.date())
    
    # 画像の値(1/7)をデフォルトに
    high_time_val = st.time_input("満潮時刻", value=datetime.time(12, 39))
    high_level_val = st.number_input("満潮潮位 (cm)", value=342, step=1)
    low_level_val = st.number_input("干潮潮位 (cm)", value=16, step=1)
    
    st.markdown("---")
    st.write("▼ 表示期間")
    view_days = st.radio("期間", [1, 3, 10], format_func=lambda x: f"{x}日間", index=0)

# --- 設定エリア ---
col1, col2 = st.columns(2)
with col1:
    target_cm = st.number_input("作業基準潮位 (cm) ※これ以下を安全とする", value=150, step=10)
with col2:
    # 24時間表記のスライダー
    start_hour, end_hour = st.slider("作業可能時間帯 (時)", 0, 24, (6, 18), format="%d時")

# --- データ生成 ---
base_high_dt = datetime.datetime.combine(input_date, high_time_val)
model = SimpleTideModel(base_high_dt, high_level_val, low_level_val)

# グラフ範囲
start_plot_dt = datetime.datetime.combine(input_date, datetime.time(0, 0))
end_plot_dt = start_plot_dt + datetime.timedelta(days=view_days) - datetime.timedelta(minutes=1)

raw_data = model.get_period_data(start_plot_dt, end_plot_dt)
df = pd.DataFrame(raw_data)

# 現在潮位
current_level = model.calculate_level(now_jst)
prev_level = model.calculate_level(now_jst - datetime.timedelta(minutes=5))

# 状態判定
if current_level > prev_level + 0.1:
    status_msg = "上げ潮 ↗"
    status_color = "red"
elif current_level < prev_level - 0.1:
    status_msg = "下げ潮 ↘"
    status_color = "blue"
else:
    status_msg = "潮止まり"
    status_color = "green"

st.subheader(f"現在: :{status_color}[{status_msg}] {current_level:.0f}cm")

# ---------------------------------------------------------
# グラフ描画 (Matplotlib・固定表示版)
# ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5)) # スマホで見やすい比率

# 1. 潮位線
ax.plot(df['time'], df['level'], color='#1f77b4', linewidth=2.5, label="推算潮位")

# 2. 基準線
ax.axhline(y=target_cm, color='orange', linestyle='--', linewidth=1.5, label=f"基準 {target_cm}cm")

# 3. 塗りつぶし (作業時間帯 かつ 基準潮位以下)
# ロジック修正: 時間(hour)が範囲内 かつ 潮位が基準以下
hours = df['time'].dt.hour
is_work_time = (hours >= start_hour) & (hours < end_hour)
is_safe_level = (df['level'] <= target_cm)

# 塗りつぶし実行
ax.fill_between(df['time'], df['level'], target_cm,
                where=(is_work_time & is_safe_level),
                color='orange', alpha=0.4, label="作業可能")

# 4. 現在地の表示 (スマホ用に文字を固定配置)
if start_plot_dt <= now_jst <= end_plot_dt:
    ax.scatter(now_jst, current_level, color='gold', s=200, zorder=10, edgecolors='black', linewidth=1.5)
    
    # 吹き出し風のテキストボックス
    text_content = f"現在\n{now_jst.strftime('%H:%M')}\n{current_level:.0f}cm"
    ax.annotate(text_content, 
                xy=(now_jst, current_level), 
                xytext=(0, 40), textcoords='offset points', # 点の40ポイント上
                ha='center', va='bottom',
                fontsize=11, fontweight='bold',
                bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="black", alpha=0.9),
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0', color='black'))

# 5. ピーク(満潮)の表示
# 表示期間内のピークを探して表示
df_peaks = df[ (df['level'] > df['level'].shift(1)) & (df['level'] > df['level'].shift(-1)) ]
for _, row in df_peaks.iterrows():
    # データ数が多くなる10日モードの時は、ピーク文字を間引くなどの工夫が必要だが、
    # シンプルに「最大値に近いピーク」だけ強調する
    if row['level'] > high_level_val - 10: # メインの満潮付近のみ表示
        ax.scatter(row['time'], row['level'], color='red', marker='^', s=60, zorder=5)
        ax.text(row['time'], row['level'] + 10, 
                f"{row['time'].strftime('%H:%M')}\n{row['level']:.0f}", 
                ha='center', va='bottom', fontsize=9, color='darkred', fontweight='bold')

# グラフ設定
ax.grid(True, linestyle=':', alpha=0.6)
ax.set_ylabel("潮位 (cm)")

# 日付フォーマット調整
if view_days == 1:
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.set_xlabel("時刻")
else:
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d日 %H時'))
    plt.xticks(rotation=30) # 日付が重ならないよう斜めに

# グラフの余白調整
plt.tight_layout()

st.pyplot(fig)

with st.expander("詳細データリスト"):
    st.dataframe(df)
