import streamlit as st
import requests
import datetime
import pandas as pd

# ==========================================
# 1. APIキーと定数の登録 (図の "User" & "DB" 部分)
# ==========================================
# 先ほどお伝えいただいたOpenWeatherMapのAPIキー
OPENWEATHER_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"

STATION_CODE = "344311"  # 竹原 (気象庁データ)
TARGET_YEAR = 2026       # 対象年

# 大西港 補正エンジン用定数 (図の "Step1, Step2")
TIME_OFFSET_MIN = 1       # 時間補正 +1分
LEVEL_BASE_OFFSET = 13    # 基準面補正 +13cm
STANDARD_PRESSURE = 1013  # 標準気圧

# ==========================================
# 2. バックアップデータ (通信エラー時の保険)
# ==========================================
BACKUP_DATA_JAN_2026 = {
    "2026-01-09": [
        {"type": "満潮", "time": "01:21", "level": 284},
        {"type": "干潮", "time": "07:23", "level": 26},
        {"type": "満潮", "time": "13:54", "level": 329},
        {"type": "干潮", "time": "20:07", "level": 94}
    ],
    "2026-01-04": [
        {"type": "干潮", "time": "04:20", "level": -21},
        {"type": "満潮", "time": "11:20", "level": 364},
        {"type": "干潮", "time": "17:10", "level": 116},
        {"type": "満潮", "time": "22:40", "level": 295}
    ]
}

# ==========================================
# 3. 内部処理ロジック (図の "App" & "Logic" 部分)
# ==========================================

@st.cache_data
def fetch_jma_tide_data(year, station_code):
    """DB: 竹原データの取得"""
    url = f"https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt/{year}/{station_code}.txt"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            return parse_jma_text(response.text, year)
        return None
    except Exception:
        return None

def parse_jma_text(text_data, year):
    data_map = {}
    lines = text_data.splitlines()
    for line in lines:
        parts = line.split()
        if len(parts) < 28 or not parts[0].isdigit():
            continue
        try:
            m_month = int(parts[2])
            m_day   = int(parts[3])
            date_str = f"{year}-{m_month:02d}-{m_day:02d}"
            hourly_levels = [int(h) for h in parts[4:28]]
            peaks = detect_tide_peaks(hourly_levels)
            data_map[date_str] = peaks
        except ValueError:
            continue
    return data_map

def detect_tide_peaks(hourly):
    peaks = []
    for i in range(1, 23):
        prev, curr, next_val = hourly[i-1], hourly[i], hourly[i+1]
        if prev < curr and curr >= next_val:
            peaks.append({"type": "満潮", "time": f"{i:02d}:00", "level": curr})
        elif prev > curr and curr <= next_val:
            peaks.append({"type": "干潮", "time": f"{i:02d}:00", "level": curr})
    return peaks

def get_current_pressure():
    """OWM: 現在気圧の取得 (APIリクエスト)"""
    lat, lon = 34.23, 132.83
    # ここで登録したAPIキーを使用します
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ja"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            return data["main"]["pressure"]
    except Exception:
        pass
    return STANDARD_PRESSURE

# ==========================================
# 4. 画面表示 (図の "User" & "Result" 部分)
# ==========================================
def main():
    st.set_page_config(page_title="大西港 潮汐予測", page_icon="🌊")
    st.title("🌊 大西港 (大崎上島) 潮汐予測")

    # 今日の日付取得 (デフォルト設定)
    today = datetime.date.today()
    default_date = datetime.date(2026, 1, 9) if today.year != 2026 else today
    
    selected_date = st.date_input("日付を選択してください", default_date)
    date_str = selected_date.strftime("%Y-%m-%d")

    # データ取得
    with st.spinner('データを計算中...'):
        tide_db = fetch_jma_tide_data(TARGET_YEAR, STATION_CODE)
        current_hpa = get_current_pressure()

    # データ準備 (バックアップ判定)
    tide_data = []
    is_backup = False
    
    if tide_db and date_str in tide_db:
        tide_data = tide_db[date_str]
    elif date_str in BACKUP_DATA_JAN_2026:
        tide_data = BACKUP_DATA_JAN_2026[date_str]
        is_backup = True

    # --- 計算ロジック (Step 3: 気圧補正) ---
    pressure_diff = STANDARD_PRESSURE - current_hpa

    # 気圧表示
    col1, col2 = st.columns(2)
    with col1:
        st.metric("現在気圧", f"{current_hpa} hPa")
    with col2:
        st.metric("気圧補正", f"{pressure_diff:+} cm", help="基準1013hPaとの差")
    st.divider()

    if tide_data:
        if is_backup:
            st.warning("⚠️ 現在、内蔵バックアップデータを表示しています。")
        
        display_data = []
        for tide in tide_data:
            # --- 計算ロジック (Step 1: 時間補正 +1分) ---
            hh, mm = map(int, tide['time'].split(':'))
            total_m = hh * 60 + mm + TIME_OFFSET_MIN
            new_time = f"{(total_m // 60) % 24:02d}:{total_m % 60:02d}"
            
            # --- 計算ロジック (Step 2: 潮位補正 +13cm + 気圧補正) ---
            final_level = tide['level'] + LEVEL_BASE_OFFSET + pressure_diff
            
            display_data.append({
                "時刻": new_time,
                "予測潮位": final_level,
                "タイプ": tide['type'],
                "詳細": f"竹原{tide['level']} + 補正{LEVEL_BASE_OFFSET+pressure_diff}"
            })
        
        # 結果表示
        df = pd.DataFrame(display_data)
        st.subheader(f"📅 {date_str} の予測結果")
        st.dataframe(df, column_config={"予測潮位": st.column_config.NumberColumn(format="%d cm")}, use_container_width=True, hide_index=True)
        st.line_chart(df.set_index("時刻")["予測潮位"])
        
    else:
        st.error(f"❌ {date_str} のデータがありません。")

if __name__ == "__main__":
    main()
