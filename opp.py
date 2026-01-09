import requests
import datetime
import sys

# ==========================================
# ユーザー設定エリア
# ==========================================
# 提供いただいたAPIキー
OPENWEATHER_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"

# ターゲット設定
TARGET_YEAR = 2026
STATION_CODE = "344311"  # 竹原
TARGET_DATE = "2026-01-04" # テスト表示する日付（紙面と同じ日）

# 大西港 補正定数
TIME_OFFSET_MIN = 1       # 時間補正 +1分
LEVEL_BASE_OFFSET = 13    # 基準面補正 +13cm
STANDARD_PRESSURE = 1013  # 標準気圧

print("【システム】処理を開始します...")

# ==========================================
# 1. データ取得モジュール (ブロック回避・強化版)
# ==========================================
def fetch_jma_tide_data(year, station_code):
    url = f"https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt/{year}/{station_code}.txt"
    
    # 【重要】ブラウザのふりをするためのヘッダー（これがないと無視されます）
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    print(f"【データ取得】気象庁サーバに接続中... \n   URL: {url}")
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8' # 文字化け防止
        
        if response.status_code != 200:
            print(f"【警告】気象庁データの取得に失敗しました (Status Code: {response.status_code})")
            return None
        
        print("【成功】データをダウンロードしました。解析を開始します。")
        parsed_data = parse_jma_text(response.text, year)
        return parsed_data

    except Exception as e:
        print(f"【エラー】通信エラーが発生しました: {e}")
        return None

def parse_jma_text(text_data, year):
    """気象庁のテキストデータを解析して辞書にする"""
    data_map = {}
    lines = text_data.splitlines()
    count = 0
    
    for line in lines:
        parts = line.split()
        # データ行の簡易チェック (竹原のコード 344311 で始まる行などを対象)
        if len(parts) < 28:
            continue
        
        # 数値で始まっていない行（ヘッダーなど）はスキップ
        if not parts[0].isdigit():
            continue
            
        try:
            # 日付の取得 (フォーマット: Code YY MM DD ...)
            # 2列目が年、3列目が月、4列目が日
            m_month = int(parts[2])
            m_day   = int(parts[3])
            date_str = f"{year}-{m_month:02d}-{m_day:02d}"
            
            # 毎時潮位 (4番目の要素から24個)
            hourly_levels = [int(h) for h in parts[4:28]]
            
            # 満干潮の簡易判定
            peaks = detect_tide_peaks(hourly_levels)
            data_map[date_str] = peaks
            count += 1
        except ValueError:
            continue
            
    print(f"【解析完了】{count}日分のデータを読み込みました。")
    return data_map

def detect_tide_peaks(hourly):
    """毎時データから満潮・干潮を見つける簡易ロジック"""
    peaks = []
    for i in range(1, 23):
        prev, curr, next_val = hourly[i-1], hourly[i], hourly[i+1]
        
        # 満潮判定 (山)
        if prev < curr and curr >= next_val:
            peaks.append({"type": "満潮", "time": f"{i:02d}:00", "level": curr})
        # 干潮判定 (谷)
        elif prev > curr and curr <= next_val:
            peaks.append({"type": "干潮", "time": f"{i:02d}:00", "level": curr})
    return peaks

# ==========================================
# 2. バックアップデータ (通信失敗時用)
# ==========================================
def get_backup_data():
    """万が一データが取れなかった場合のための予備データ"""
    print("【情報】内蔵のバックアップデータを使用します。")
    return [
        {"type": "干潮", "time": "04:20", "level": -21},
        {"type": "満潮", "time": "11:20", "level": 364},
        {"type": "干潮", "time": "17:10", "level": 116},
        {"type": "満潮", "time": "22:40", "level": 295}
    ]

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
            loc = data.get('name', 'Unknown')
            print(f"【成功】現在気圧: {pres} hPa (観測地点: {loc})")
            return pres
        else:
            print(f"【失敗】APIエラー: {res.status_code}")
    except Exception as e:
        print(f"【失敗】通信エラー: {e}")
    
    print("【情報】標準気圧(1013hPa)を使用します。")
    return STANDARD_PRESSURE

# ==========================================
# 4. メイン処理
# ==========================================
def main():
    # 1. 潮汐データの準備
    tide_db = fetch_jma_tide_data(TARGET_YEAR, STATION_CODE)
    
    # データベースから指定日のデータを取得
    # データがない、または取得失敗した場合はバックアップを使用
    if tide_db and TARGET_DATE in tide_db:
        tide_data = tide_db[TARGET_DATE]
    else:
        print(f"【注意】{TARGET_DATE} のデータが見つかりませんでした。")
        tide_data = get_backup_data()

    # 2. 現在気圧の取得
    current_hpa = get_current_pressure()
    
    # 3. 補正計算 (吸い上げ効果)
    # 気圧が低いほど海面は上がる (1hPa低下 = +1cm)
    pressure_diff = STANDARD_PRESSURE - current_hpa
    
    print("\n" + "="*60)
    print(f" 🚢 大西港 (大崎上島) リアルタイム潮汐予測システム ")
    print(f" 📅 日付: {TARGET_DATE}")
    print(f" ☁️ 気圧: {current_hpa} hPa (補正値: {pressure_diff:+d}cm)")
    print(f" ⚙️ 定数: 基準差 +{LEVEL_BASE_OFFSET}cm / 時間 +{TIME_OFFSET_MIN}分")
    print("="*60)
    print(f" 時刻   | 予測潮位 | 潮名 | (参考:竹原生データ)")
    print("-" * 60)
    
    if not tide_data:
        print("表示できるデータがありません。")
        return

    for tide in tide_data:
        # 時間計算 (文字列処理)
        hh, mm = map(int, tide['time'].split(':'))
        total_m = hh * 60 + mm + TIME_OFFSET_MIN
        
        # 24時間を超えた場合の処理
        new_h = (total_m // 60) % 24
        new_m = total_m % 60
        new_time = f"{new_h:02d}:{new_m:02d}"
        
        # 潮位計算 (竹原 + 基準差 + 気圧補正)
        final_level = tide['level'] + LEVEL_BASE_OFFSET + pressure_diff
        
        print(f" {new_time}  | {int(final_level):4d} cm  | {tide['type']} | ({tide['time']} / {tide['level']}cm)")

    print("-" * 60)
    print("処理完了")

if __name__ == "__main__":
    main()
