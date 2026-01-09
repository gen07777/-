import requests
import datetime
import sys

# ==========================================
# ユーザー設定エリア
# ==========================================
OPENWEATHER_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"
TARGET_YEAR = 2026
STATION_CODE = "344311"  # 竹原
TARGET_DATE = "2026-01-04" # テスト表示する日付

# 大西港 補正定数
TIME_OFFSET_MIN = 1
LEVEL_BASE_OFFSET = 13
STANDARD_PRESSURE = 1013

print("【システム】起動しました...")

# ==========================================
# 1. データ取得モジュール (強化版)
# ==========================================
def fetch_jma_tide_data(year, station_code):
    url = f"https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt/{year}/{station_code}.txt"
    
    # 対策: ブラウザのふりをするヘッダーを追加
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    print(f"【データ取得】気象庁サーバに接続中... ({url})")
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8' # エンコーディングを明示
        
        if response.status_code != 200:
            print(f"【警告】気象庁データの取得に失敗 (Code: {response.status_code})")
            return None
        
        parsed_data = parse_jma_text(response.text, year)
        if not parsed_data:
            print("【警告】データの解析に失敗しました。")
            return None
            
        print(f"【成功】{len(parsed_data)}日分の潮汐データを取得しました。")
        return parsed_data

    except Exception as e:
        print(f"【エラー】通信または解析エラー: {e}")
        return None

def parse_jma_text(text_data, year):
    data_map = {}
    lines = text_data.splitlines()
    for line in lines:
        parts = line.split()
        # データ行の簡易チェック (竹原のコード 344311 で始まる行など)
        if len(parts) < 28 or not parts[0].isdigit():
            continue
            
        try:
            m_month = int(parts[2])
            m_day   = int(parts[3])
            date_str = f"{year}-{m_month:02d}-{m_day:02d}"
            hourly_levels = [int(h) for h in parts[4:28]]
            
            # 満干潮の推定
            peaks = detect_tide_peaks(hourly_levels)
            data_map[date_str] = peaks
        except ValueError:
            continue
    return data_map

def detect_tide_peaks(hourly):
    # 簡易ピーク検出
    peaks = []
    for i in range(1, 23):
        prev, curr, next_val = hourly[i-1], hourly[i], hourly[i+1]
        
        # 満潮
        if prev < curr and curr >= next_val:
            peaks.append({"type": "満潮", "time": f"{i:02d}:00", "level": curr})
        # 干潮
        elif prev > curr and curr <= next_val:
            peaks.append({"type": "干潮", "time": f"{i:02d}:00", "level": curr})
    return peaks

# ==========================================
# 2. バックアップデータ (通信失敗時用)
# ==========================================
def get_backup_data(date_str):
    # 2026-01-04 竹原の推定データ
    if date_str == "2026-01-04":
        return [
            {"type": "干潮", "time": "04:20", "level": -21},
            {"type": "満潮", "time": "11:20", "level": 364},
            {"type": "干潮", "time": "17:10", "level": 116},
            {"type": "満潮", "time": "22:40", "level": 295}
        ]
    return []

# ==========================================
# 3. 気圧取得モジュール
# ==========================================
def get_current_pressure():
    lat, lon = 34.23, 132.83
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ja"
    
    print("【気象取得】OpenWeatherMapに問い合わせ中...")
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            pres = data["main"]["pressure"]
            print(f"【成功】現在気圧: {pres} hPa (場所: {data.get('name')})")
            return pres
        else:
            print(f"【失敗】APIエラー: {res.status_code}")
    except Exception as e:
        print(f"【失敗】通信エラー: {e}")
    
    return STANDARD_PRESSURE

# ==========================================
# 4. メイン処理
# ==========================================
def main():
    # 1. 潮汐データの準備
    tide_db = fetch_jma_tide_data(TARGET_YEAR, STATION_CODE)
    
    # データが取れなかった場合はバックアップを使用
    if not tide_db:
        print("【情報】オンラインデータが取得できないため、内蔵バックアップデータを使用します。")
        tide_data = get_backup_data(TARGET_DATE)
    else:
        tide_data = tide_db.get(TARGET_DATE, [])

    if not tide_data:
        print("【エラー】表示できる潮汐データがありません。")
        return

    # 2. 現在気圧の取得
    current_hpa = get_current_pressure()
    
    # 3. 補正計算
    pressure_diff = STANDARD_PRESSURE - current_hpa
    
    print("\n" + "="*50)
    print(f" 🚢 大西港 (大崎上島) リアルタイム潮汐予測 ")
    print(f" 日付: {TARGET_DATE}")
    print(f" 気圧: {current_hpa} hPa (補正値: {pressure_diff:+d}cm)")
    print("="*50)
    print(f"時刻  | 予測潮位 | 潮名 | (ベース値)")
    print("-" * 50)
    
    for tide in tide_data:
        # 時間計算 (簡易版: 文字列処理)
        hh, mm = map(int, tide['time'].split(':'))
        total_m = hh * 60 + mm + TIME_OFFSET_MIN
        new_time = f"{(total_m // 60) % 24:02d}:{total_m % 60:02d}"
        
        # 潮位計算
        final_level = tide['level'] + LEVEL_BASE_OFFSET + pressure_diff
        
        print(f"{new_time} | {int(final_level):4d} cm | {tide['type']} | ({tide['level']}cm)")

    print("-" * 50)
    print("処理完了")

if __name__ == "__main__":
    main()
