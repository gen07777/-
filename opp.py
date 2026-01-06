import streamlit as st
import datetime
import math
import pandas as pd

# ---------------------------------------------------------
# 計算ロジック (Matplotlibなどエラーの原因になるものは排除)
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
                "Time": calc_time.strftime("%H:%M"),
                "Level_cm": round(onishi_level, 1),
                "raw_time": calc_time
            })
        return hourly_data

    def find_times_for_target_level(self, daily_data, target_level):
        found_times = []
        for i in range(len(daily_data) - 1):
            p1 = daily_data[i]
            p2 = daily_data[i+1]
            y1 = p1['Level_cm']
            y2 = p2['Level_cm']
            
            if (y1 <= target_level <= y2) or (y1 >= target_level >= y2):
                if y2 == y1: continue
                fraction = (target_level - y1) / (y2 - y1)
                minutes_add = fraction * 60
                found_time = p1['raw_time'] + datetime.timedelta(minutes=minutes_add)
                
                trend = "UP (Rising)" if y2 > y1 else "DOWN (Falling)"
                time_str = found_time.strftime("%H:%M")
                found_times.append(f"{time_str} : {trend}")
        return found_times

# ---------------------------------------------------------
# アプリ画面 (シンプル版)
# ---------------------------------------------------------
st.title("Tide Calculator")
st.write("Onishi Port")

# 入力エリア
col1, col2 = st.columns(2)
with col1:
    target_date = st.date_input("Date", datetime.date.today())
with col2:
    target_cm = st.number_input("Target Level (cm)", value=150, step=10)

# 計算実行
calculator = OnishiTideCalculator()
calc_date = datetime.datetime(target_date.year, target_date.month, target_date.day)
prediction_data = calculator.get_onishi_prediction(calc_date)

# 結果表示
st.subheader(f"Time for {target_cm} cm")
matched_times = calculator.find_times_for_target_level(prediction_data, target_cm)

if matched_times:
    for t in matched_times:
        st.success(t)
else:
    st.warning("Not reached on this date.")

# グラフ表示 (エラーが出ない標準グラフ)
st.subheader("Tide Graph")
df = pd.DataFrame(prediction_data)
df = df.set_index("Time")
st.line_chart(df["Level_cm"])

# データ表
with st.expander("Show Data"):
    st.dataframe(df)
