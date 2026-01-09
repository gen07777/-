import streamlit as st
import requests
import datetime
import pandas as pd

# ==========================================
# 設定エリア
# ==========================================
OPENWEATHER_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"
STATION_CODE = "344311"  # 竹原
TARGET_YEAR = 2026

# 大西港 補正定数
TIME_OFFSET_MIN = 1       # 時間補正 +1分
LEVEL_BASE_OFFSET = 13    # 基準面補正 +13cm
STANDARD_PRESSURE = 1013  # 標準気圧

# ==========================================
# バックアップデータ (通信エラー時用)
# ==========================================
# 気象庁のサーバーにつながらない場合、このデータを使用します
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
# 関数定義
# ==========================================

@st.cache_data
def fetch_jma_tide_data(year, station_code):
    """気象庁からデータを取得。失敗したらバックアップを返す"""
    url = f"https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt/{year}/{station_code}.txt"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        # タイムアウトを少し長めに設定
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        
        if response.status_code == 200:
            return parse_jma_text(response.text, year)
        else:
            return None # ステータスエラー
            
    except Exception as e:
        return None # 通信エラー

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
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            return data["main"]["pressure"]
    except Exception:
        pass
    return STANDARD_PRESSURE

# ==========================================
# メイン画面構築
# ==========================================
def main():
    st.set_page_config(page_title="大西港 潮汐予測", page_icon="🌊")
    
    st.title("🌊 大西港 (大崎上島) 潮汐予測")
    st.caption("紙面の潮汐表を再現 + リアルタイム気圧補正")

    # 今日の日付をデフォルトに
    today = datetime.date.today()
    # テスト用に2026年に強制変換（システム日付が2025などの場合のため）
    default_date = datetime.date(2026, 1, 9) if today.year != 2026 else today
    
    selected_date = st.date_input("日付を選択してください", default_date)
    date_str = selected_date.strftime("%Y-%m-%d")

    # データ取得プロセス
    with st.spinner('データを更新中...'):
        tide_db = fetch_jma_tide_data(TARGET_YEAR, STATION_CODE)
        current_hpa = get_current_pressure()

    # DB取得失敗時のフォールバック処理
    is_backup = False
    tide_data = []
    
    if tide_db and date_str in tide_db:
        tide_data = tide_db[date_str]
    elif date_str in BACKUP_DATA_JAN_2026:
        # 通信失敗したが、バックアップにある場合
        tide_data = BACKUP_DATA_JAN_2026[date_str]
        is_backup = True
    else:
        # データが全くない場合
        pass

    # 気圧表示エリア
    pressure_diff = STANDARD_PRESSURE - current_hpa
    col1, col2 = st.columns(2)
    with col1:
        st.metric("現在気圧", f"{current_hpa} hPa")
    with col2:
        st.metric("気圧補正値", f"{pressure_diff:+} cm", help="基準1013hPaとの差")

    st.divider()

    if tide_data:
        if is_backup:
            st.warning("⚠️ 気象庁サーバへの接続に失敗したため、内蔵バックアップデータを表示しています。")
        
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
                "予測潮位": final_level,
                "タイプ": tide['type'],
                "詳細": f"竹原{tide['level']} + 補正{LEVEL_BASE_OFFSET+pressure_diff}"
            })
        
        # テーブル表示
        df = pd.DataFrame(display_data)
        st.subheader(f"📅 {date_str} の予測結果")
        
        st.dataframe(
            df,
            column_config={
                "予測潮位": st.column_config.NumberColumn(format="%d cm"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        # グラフ
        chart_df = df.set_index("時刻")["予測潮位"]
        st.line_chart(chart_df)
        
    else:
        # 本当にデータがない場合
        st.error(f"❌ {date_str} のデータ取得に失敗しました。")
        st.info("※現在、バックアップデータは 1/4 と 1/9 のみ搭載されています。他の日付を選択するか、しばらく待ってリロードしてください。")

if __name__ == "__main__":
    main()
