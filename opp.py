import streamlit as st
import requests
import datetime
import pandas as pd

# ==========================================
# 設定エリア
# ==========================================
OPENWEATHER_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"
STATION_CODE = "344311"  # 竹原
TARGET_YEAR = 2026       # 取得対象年

# 大西港 補正定数
TIME_OFFSET_MIN = 1       # 時間補正 +1分
LEVEL_BASE_OFFSET = 13    # 基準面補正 +13cm
STANDARD_PRESSURE = 1013  # 標準気圧

# ==========================================
# 関数定義
# ==========================================

# データをキャッシュして高速化（毎回ダウンロードしない）
@st.cache_data
def fetch_jma_tide_data(year, station_code):
    url = f"https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt/{year}/{station_code}.txt"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        if response.status_code != 200:
            return None
        return parse_jma_text(response.text, year)
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
    lat, lon = 34.23, 132.83
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ja"
    try:
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            data = res.json()
            return data["main"]["pressure"]
    except Exception:
        pass
    return STANDARD_PRESSURE

# ==========================================
# メイン画面構築 (UI)
# ==========================================
def main():
    st.set_page_config(page_title="大西港 潮汐予測", page_icon="🌊")
    
    st.title("🌊 大西港 (大崎上島) 潮汐予測")
    st.caption("紙面の潮汐表を再現し、さらに気圧変化を加味した安全予測")

    # サイドバーで日付選択
    selected_date = st.date_input(
        "日付を選択してください",
        datetime.date(2026, 1, 4) # 初期値
    )
    date_str = selected_date.strftime("%Y-%m-%d")

    # データの取得
    with st.spinner('データを読み込んでいます...'):
        tide_db = fetch_jma_tide_data(TARGET_YEAR, STATION_CODE)
        current_hpa = get_current_pressure()

    # 気圧情報の表示
    pressure_diff = STANDARD_PRESSURE - current_hpa
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="現在気圧 (大崎上島)", value=f"{current_hpa} hPa")
    with col2:
        st.metric(label="気圧による潮位補正", value=f"{pressure_diff:+} cm", 
                  help="気圧が低いと海面が吸い上げられて高くなります")

    st.divider()

    # 潮汐データの表示処理
    if tide_db and date_str in tide_db:
        tide_data = tide_db[date_str]
        
        display_data = []
        for tide in tide_data:
            # 時間計算
            hh, mm = map(int, tide['time'].split(':'))
            total_m = hh * 60 + mm + TIME_OFFSET_MIN
            new_time = f"{(total_m // 60) % 24:02d}:{total_m % 60:02d}"
            
            # 潮位計算
            final_level = tide['level'] + LEVEL_BASE_OFFSET + pressure_diff
            
            display_data.append({
                "時刻": new_time,
                "予測潮位 (cm)": final_level,
                "満潮/干潮": tide['type'],
                "補正詳細": f"竹原{tide['level']} + 基準13 + 気圧{pressure_diff}"
            })
        
        # データフレームにして表示
        df = pd.DataFrame(display_data)
        st.subheader(f"📅 {date_str} の予測")
        
        # 重要な部分を強調表示するスタイル設定
        st.dataframe(
            df,
            column_config={
                "予測潮位 (cm)": st.column_config.NumberColumn(format="%d cm"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        # グラフ描画（簡易イメージ）
        st.caption("※ グラフはピークを結んだ簡易的なものです")
        chart_data = df.set_index("時刻")["予測潮位 (cm)"]
        st.line_chart(chart_data)

    else:
        st.error(f"{date_str} のデータが見つかりませんでした。(2026年のデータのみ対応しています)")
        st.info("※気象庁データ取得エラーの場合は、しばらく待ってからリロードしてください。")

if __name__ == "__main__":
    main()
