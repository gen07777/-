import streamlit as st
import datetime
import math
import pandas as pd

# ==========================================
# ロジッククラス (計算の中身)
# ==========================================
class OnishiTideCalculator:
    def __init__(self):
        self.CORRECTION_RATIO = 1.0
        self.TIME_OFFSET_MINUTES = 0
        self.MSL = 250.0 
        # 竹原エリアの概算調和定数
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
                "hour_label": calc_time.strftime("%H:00") # グラフ用ラベル
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
                found_times.append(f"**{time_str}** 頃  {trend}")
        return found_times

# ==========================================
# Webアプリ画面 (Streamlit)
# ==========================================
st.title("🌊 大西港 潮位逆算ツール")
st.caption("指定した潮位になる時刻を計算します (竹原基準補正)")

# 1. 日付選択
col1, col2 = st.columns(2)
with col1:
    target_date = st.date_input("日付を選択", datetime.date.today())
with col2:
    target_cm = st.number_input("探したい潮位 (cm)", value=150, step=10)

# 計算実行
calculator = OnishiTideCalculator()
# dateをdatetimeに変換して計算
calc_date = datetime.datetime(target_date.year, target_date.month, target_date.day)
prediction_data = calculator.get_onishi_prediction(calc_date)

# 2. 結果表示
st.subheader(f"潮位 {target_cm}cm になる時刻")
matched_times = calculator.find_times_for_target_level(prediction_data, target_cm)

if matched_times:
    for t in matched_times:
        st.success(t) # 緑色のボックスで表示
else:
    st.warning("指定された潮位になる時間帯はこの日にはありません。")

# 3. グラフ表示
st.subheader("当日の潮位グラフ")
df = pd.DataFrame(prediction_data)
df = df.set_index("hour_label") # 横軸を時間に
st.line_chart(df["level"])

# 4. 詳細データ
with st.expander("毎時データを見る"):
    st.table(df["level"])
