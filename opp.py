import streamlit as st
import requests
import datetime
import pandas as pd

# ==========================================
# 設定: APIキーと定数
# ==========================================
OPENWEATHER_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb" # 指定のAPIキー
STATION_CODE = "344311"  # 竹原 (気象庁データ)
TARGET_YEAR = 2026       # 取得対象年

# 補正ロジック用定数
TIME_OFFSET_MIN = 1       # 時間補正: +1分
LEVEL_BASE_OFFSET = 13    # 基準差: +13cm
STANDARD_PRESSURE = 1013  # 標準気圧: 1013hPa

# ==========================================
# 1. 気象庁から潮汐データを取得 (リアルタイム取得)
# ==========================================
@st.cache_data(ttl=3600) # 1時間キャッシュ (サーバー負荷軽減のため)
def fetch_jma_tide_data(year, station_code):
    """
    気象庁の公式サイトから指定年のテキストデータを直接ダウンロードして解析する
    """
    url = f"https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt/{year}/{station_code}.txt"
    
    # ブラウザからのアクセスに見せるためのヘッダー
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code == 200:
            return parse_jma_text(response.text, year)
        else:
            return None
    except Exception:
        return None

def parse_jma_text(text_data, year):
    """気象庁のテキスト形式を辞書データに変換"""
    data_map = {}
    lines = text_data.splitlines()
    for line in lines:
        parts = line.split()
        # データ行の判定 (要素数が足りているか、数字で始まっているか)
        if len(parts) < 28 or not parts[0].isdigit():
            continue
            
        try:
            m_month = int(parts[2])
            m_day   = int(parts[3])
            date_str = f"{year}-{m_month:02d}-{m_day:02d}"
            
            # 毎時潮位データ (0時〜23時)
            hourly_levels = [int(h) for h in parts[4:28]]
            
            # 満潮・干潮のピーク時間を計算
            peaks = detect_tide_peaks(hourly_levels)
            data_map[date_str] = peaks
        except ValueError:
            continue
    return data_map

def detect_tide_peaks(hourly):
    """毎時データから満干潮を推定"""
    peaks = []
    for i in range(1, 23):
        prev, curr, next_val = hourly[i-1], hourly[i], hourly[i+1]
        
        # 満潮 (山)
        if prev < curr and curr >= next_val:
            peaks.append({"type": "満潮", "time": f"{i:02d}:00", "level": curr})
        # 干潮 (谷)
        elif prev > curr and curr <= next_val:
            peaks.append({"type": "干潮", "time": f"{i:02d}:00", "level": curr})
    return peaks

# ==========================================
# 2. OpenWeatherMapから気圧を取得
# ==========================================
def get_current_pressure():
    """大崎上島付近の現在気圧を取得"""
    lat, lon = 34.23, 132.83
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ja"
    
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            return data["main"]["pressure"]
    except Exception:
        pass
    return STANDARD_PRESSURE # 取得失敗時は標準気圧

# ==========================================
# 3. メインアプリ画面 (計算ロジック適用)
# ==========================================
def main():
    st.set_page_config(page_title="大西港 潮汐予測", page_icon="🌊")
    st.title("🌊 大西港 (大崎上島) 潮汐予測")
    st.caption("気象庁データ(竹原) × リアルタイム気圧補正")

    # 日付選択 (2026年をデフォルトに)
    today = datetime.date.today()
    default_date = datetime.date(2026, 1, 9) if today.year != 2026 else today
    
    selected_date = st.date_input("日付を選択", default_date)
    date_str = selected_date.strftime("%Y-%m-%d")

    # データ取得
    with st.spinner('気象庁とOpenWeatherMapからデータを取得中...'):
        # 1. 竹原の潮汐データ取得
        tide_db = fetch_jma_tide_data(TARGET_YEAR, STATION_CODE)
        # 2. 現在気圧の取得
        current_hpa = get_current_pressure()

    # --- 計算ロジック: 気圧補正 ---
    # 『気圧差（1013 - 現在値）』
    pressure_correction = STANDARD_PRESSURE - current_hpa

    # 気圧情報の表示
    col1, col2 = st.columns(2)
    with col1:
        st.metric("現在気圧", f"{current_hpa} hPa")
    with col2:
        st.metric("気圧補正値", f"{pressure_correction:+} cm", help="(1013 - 現在気圧)")
    
    st.divider()

    # データの表示処理
    if tide_db and date_str in tide_db:
        tide_data = tide_db[date_str]
        display_data = []

        for tide in tide_data:
            # --- 計算ロジック: 時間補正 ---
            # 竹原の時間 + 1分
            hh, mm = map(int, tide['time'].split(':'))
            total_m = hh * 60 + mm + TIME_OFFSET_MIN
            new_time = f"{(total_m // 60) % 24:02d}:{total_m % 60:02d}"
            
            # --- 計算ロジック: 潮位補正 ---
            # 竹原潮位 + 基準差(13cm) + 気圧差
            base_level = tide['level']
            final_level = base_level + LEVEL_BASE_OFFSET + pressure_correction
            
            display_data.append({
                "時刻": new_time,
                "予測潮位": final_level,
                "タイプ": tide['type'],
                "計算式": f"{base_level}(竹原) + 13(基準) + {pressure_correction}(気圧)"
            })
        
        # 結果テーブルの表示
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
        
        # グラフ表示
        st.line_chart(df.set_index("時刻")["予測潮位"])
        
    else:
        st.error(f"データ取得エラー: {date_str} のデータが見つかりませんでした。")
        st.info("※気象庁のサーバー接続状況を確認するか、日付を変更してください。")

if __name__ == "__main__":
    main()
