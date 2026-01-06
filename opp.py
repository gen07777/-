import streamlit as st
import datetime
import math
import pandas as pd
import matplotlib.pyplot as plt
import japanize_matplotlib  # 日本語文字化け防止

# ---------------------------------------------------------
# 計算ロジッククラス
# ---------------------------------------------------------
class OnishiTideCalculator:
    def __init__(self):
        self.CORRECTION_RATIO = 1.0
        self.TIME_OFFSET_MINUTES = 0
        self.MSL = 250.0 
        self.CONSTITUENTS = {
            'M2': {'amp': 130.0, 'phase': 200.0, 'speed': 28.9841042},
            'S2': {'amp': 50.0,  'phase': 230.0, 'speed': 30.0000000},
            'K1': {'amp': 35.0,  'phase': 180.0, 'speed': 15.0410686},
            'O1': {'amp': 30.0,  'phase': 160.0, 'speed': 13.9430356}
        }

    def _calculate_astronomical_tide(self, target_datetime):
        base_date = datetime.datetime(target_datetime.year, 1, 1)
        delta_hours = (target_datetime - base_date).total_seconds() / 3600.0
        tide_height = self.MSL
        for name, const in self.CONSTITUENTS.items():
            theta = math.radians(const['speed'] * delta_hours - const['phase'])
            tide_height += const['amp'] * math.cos(theta)
        return tide_height

    def get_onishi_prediction(self, target_date):
        hourly_data = []
        for hour in range(24):
            calc_time = datetime.datetime(target_date.year, target_date.month, target_date.day, hour)
            calc_time_offset = calc_time - datetime.timedelta(minutes=self.TIME_OFFSET_MINUTES)
            base_level = self._calculate_astronomical_tide(calc_time_offset)
            onishi_level = base_level * self.CORRECTION_RATIO
            
            hourly_data.append({
                "time": calc_time,
                "level": round(onishi_level, 1),
                "hour_label": calc_time.strftime("%H") # グラフ用(時間のみ)
            })
        return hourly_data

    def find_times_for_target_level(self, daily_data, target_level):
        found_times = []
        for i in range(len(daily_data) - 1):
            p1 = daily_data[i]
            p2 = daily_data[i+1]
            y1 = p1['level']
            y2 = p2['level']
            
            if (y1 <= target_level <= y2) or (y1 >= target_level >= y2):
                if y2 == y1: continue
                fraction = (target_level - y1) / (y2 - y1)
                minutes_add = fraction * 60
                found_time = p1['time'] + datetime.timedelta(minutes=minutes_add)
                trend = "↑ (上げ潮)" if y2 > y1 else "↓ (下げ潮)"
                time_str = found_time.strftime("%H:%M")
                found_times.append(f"{time_str} 頃  {trend}")
        return found_times

# ---------------------------------------------------------
# アプリ画面表示
# ---------------------------------------------------------
st.title("大西港 潮位逆算ツール")
st.write("指定した潮位になる時間を計算します。")

# 1. 入力エリア
col1, col2 = st.columns(2)
with col1:
    target_date = st.date_input("日付", datetime.date.today())
with col2:
    target_cm = st.number_input("探したい潮位 (cm)", value=150, step=10)

# 計算実行
calculator = OnishiTideCalculator()
calc_date = datetime.datetime(target_date.year, target_date.month, target_date.day)
prediction_data = calculator.get_onishi_prediction(calc_date)

# 2. 結果表示
st.subheader(f"潮位 {target_cm}cm になる時刻")
matched_times = calculator.find_times_for_target_level(prediction_data, target_cm)

if matched_times:
    for t in matched_times:
        st.info(t)
else:
    st.warning("指定された潮位になる時間帯はこの日にはありません。")

# 3. グラフ表示 (Matplotlibを使用)
st.subheader("当日の潮位グラフ")

# データフレーム作成
df = pd.DataFrame(prediction_data)

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(df["time"], df["level"], marker='o', label='予測潮位')

# 指定潮位のラインを引く
ax.axhline(y=target_cm, color='r', linestyle='--', label=f'指定潮位 ({target_cm}cm)')

ax.set_title(f"{target_date.strftime('%Y/%m/%d')} 大西港 潮位予測")
ax.set_xlabel("時刻")
ax.set_ylabel("潮位 (cm)")
ax.grid(True)
ax.legend()

# X軸を時間フォーマットで見やすく
import matplotlib.dates as mdates
ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))

st.pyplot(fig)

# データテーブル
with st.expander("詳細データを見る"):
    st.dataframe(df[["time", "level"]])