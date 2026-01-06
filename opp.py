import streamlit as st
import datetime
import math
import calendar
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ---------------------------------------------------------
# 計算ロジック (変更なし)
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

    def get_period_data(self, year, month, start_day, end_day, interval_minutes=5):
        """期間データ生成"""
        detailed_data = []
        
        # 開始・終了日時の設定
        start_dt = datetime.datetime(year, month, start_day)
        
        # 月末日の処理
        last_day_of_month = calendar.monthrange(year, month)[1]
        
        # end_dayが月の最終日より大きい場合の安全策
        if end_day > last_day_of_month:
            end_day = last_day_of_month

        # 終了日時の設定（その日の23:55まで）
        end_dt = datetime.datetime(year, month, end_day, 23, 55)

        current_dt = start_dt
        while current_dt <= end_dt:
            calc_time_offset = current_dt - datetime.timedelta(minutes=self.TIME_OFFSET_MINUTES)
            base_level = self._calculate_astronomical_tide(calc_time_offset)
            onishi_level = base_level * self.CORRECTION_RATIO
            
            detailed_data.append({
                "raw_time": current_dt,
                "Level_cm": onishi_level
            })
            current_dt += datetime.timedelta(minutes=interval_minutes)
            
        return detailed_data

# ---------------------------------------------------------
# アプリケーション画面構成
# ---------------------------------------------------------
st.set_page_config(layout="wide")
st.title("大西港 潮位ビジュアライザー")

# --- サイドバー設定エリア ---
with st.sidebar:
    st.header("条件設定")
    
    # 1. 年の選択
    year_sel = st.number_input("対象年", value=datetime.date.today().year)
    
    # 2. 期間選択リストの作成 (1月前半, 1月後半 ... 12月後半)
    period_options = []
    for m in range(1, 13):
        period_options.append(f"{m}月前半 (1日-15日)")
        period_options.append(f"{m}月後半 (16日-末日)")
    
    # デフォルトのインデックス（現在の月を選択状態にする）
    current_month = datetime.date.today().month
    default_index = (current_month - 1) * 2 # 簡易計算
    
    selected_period = st.selectbox(
        "表示する期間を選択",
        period_options,
        index=default_index
    )
    
    st.divider()
    
    # 3. 潮位と時間の設定
    target_cm = st.number_input("基準潮位 (cm)", value=150, step=10, help="この高さより低い時間を探します")
    
    st.subheader("活動時間フィルタ")
    start_hour, end_hour = st.slider(
        "グラフに色を塗る時間帯:",
        0, 24, (7, 23),
        format="%d時"
    )

# --- メイン処理 ---

# 選択された期間文字列から「月」と「前半/後半」を解析
# 例: "10月後半 (16日-末日)" -> "10" と "後半"
import re
match = re.match(r"(\d+)月(..)", selected_period)
if match:
    month_sel = int(match.group(1))
    period_type = match.group(2)
else:
    month_sel = 1
    period_type = "前半"

# 日付範囲の決定
last_day = calendar.monthrange(year_sel, month_sel)[1]
if "前半" in period_type:
    start_d, end_d = 1, 15
else:
    start_d, end_d = 16, last_day

# データ計算実行
calculator = OnishiTideCalculator()
data = calculator.get_period_data(year_sel, month_sel, start_d, end_d)
df = pd.DataFrame(data)

# データが空でないか確認
if df.empty:
    st.error("データ生成に失敗しました。日付設定を確認してください。")
else:
    # ---------------------------------------------------------
    # グラフ描画ロジック (Matplotlib)
    # ---------------------------------------------------------
    st.subheader(f"グラフ表示: {selected_period}")

    fig, ax = plt.subplots(figsize=(15, 8))
