import requests
import datetime
import math

# ==========================================
# ユーザー設定エリア
# ==========================================
OPENWEATHER_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"  # 提供されたAPIキー
TARGET_YEAR = 2026       # 取得したい年
STATION_CODE = "344311"  # 竹原の地点コード (気象庁)

# 大西港 補正定数 (検証結果に基づく)
TIME_OFFSET_MIN = 1      # 時間補正 (+1分)
LEVEL_BASE_OFFSET = 13   # 基準面補正 (+13cm)
STANDARD_PRESSURE = 1013 # 標準気圧 (hPa)

# ==========================================
# 1. 気象庁データ自動取得 & 解析モジュール
# ==========================================
def fetch_jma_tide_data(year, station_code):
    """
    気象庁の公式サイトから指定された年・地点の毎時潮位データ(TXT)を取得し、
    満潮・干潮を計算して辞書形式で返す。
    """
    # 気象庁のデータURL（水産庁用・毎時潮位データ）
    # データ形式: 1行に1日分。スペース区切りで日付と0時~23時の潮位(cm)が並ぶ
    url = f"https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt/{year}/{station_code}.txt"
    
    print(f"【データ取得】気象庁サーバからデータをダウンロード中... ({url})")
    try:
        response = requests.get(url)
        if response.status_code != 200:
            print("【エラー】データの取得に失敗しました。URLまたは年を確認してください。")
            return {}
        
        raw_lines = response.text.splitlines()
        parsed_data = {}

        for line in raw_lines:
            # データ行の解析 (形式: Station YY MM DD H00 H01 ... H23)
            # ※気象庁のTXT形式は固定長に近いスペース区切り
            parts = line.split()
            if len(parts) < 28: continue # データ不足行はスキップ
            
            # 日付情報の抽出
            try:
                # 最初のカラムが地点コードでなく年等の場合もあるため、柔軟に解析
                # 標準フォーマット: [Code] [YY] [MM] [DD] [00h] [01h] ...
                # ただし最初の行やヘッダを除く必要があるが、数値のみの行を対象とする
                if not parts[0].isdigit(): continue
                
                # 年月日の取得 (parts[1]が年下2桁の場合などフォーマットに注意)
                # ここでは簡易的に配列のインデックスで取得
                m_month = int(parts[2])
                m_day   = int(parts[3])
                date_str = f"{year}-{m_month:02d}-{m_day:02d}"
                
                # 毎時データの取得 (4番目の要素から24個)
                hourly_levels = [int(h) for h in parts[4:28]]
                
                # 毎時データから満潮・干潮（ピーク）を推定計算
                peaks = detect_tide_peaks(hourly_levels, date_str)
                parsed_data[date_str] = peaks
                
            except ValueError:
                continue

        print(f"【完了】{len(parsed_data)}日分の潮汐データを解析しました。")
        return parsed_data

    except Exception as e:
        print(f"【例外】データ処理中にエラーが発生しました: {e}")
        return {}

def detect_tide_peaks(hourly, date_str):
    """
    24時間の毎時データから、ラグランジュ補間または二次関数近似を用いて
    満潮・干潮の「正確な分単位」の時刻と潮位を推定する簡易ロジック
    """
    peaks = []
    # 前日・翌日のデータがないため、当日0時〜23時の範囲で極値を探索
    # (本格的なアプリでは前後のデータも連結して計算します)
    for i in range(1, 23):
        y_prev = hourly[i-1]
        y_curr = hourly[i]
        y_next = hourly[i+1]
        
        # 極大値 (満潮) の判定
        if y_prev < y_curr and y_curr >= y_next:
            time_min, level = interpolate_peak(i, y_prev, y_curr, y_next)
            peaks.append({"type": "満潮", "time": time_min, "level": int(level)})
            
        # 極小値 (干潮) の判定
        elif y_prev > y_curr and y_curr <= y_next:
            time_min, level = interpolate_peak(i, y_prev, y_curr, y_next)
            peaks.append({"type": "干潮", "time": time_min, "level": int(level)})
            
    return peaks

def interpolate_peak(hour_idx, y1, y2, y3):
    """
    3点の潮位から放物線近似を行い、ピークの時刻（分）と潮位を算出する
    """
    # 簡易的な二次補間
    # 頂点のずれ dt = (y1 - y3) / (2 * (y1 - 2*y2 + y3))
    denom = (y1 - 2*y2 + y3)
    if denom == 0:
        dt = 0
    else:
        dt = (y1 - y3) / (2 * denom) * 0.5 # 0.5倍係数で調整
    
    # ピーク時刻 (時:分)
    peak_hour = hour_idx + dt
    total_minutes = int(peak_hour * 60)
    hour = total_minutes // 60
    minute = total_minutes % 60
    time_str = f"{hour:02d}:{minute:02d}"
    
    # ピーク潮位 (y2 + 補正分)
    if denom == 0:
        peak_level = y2
    else:
        peak_level = y2 - (y1 - y3) * dt / 4 # 簡易近似
        
    return time_str, peak_level

# ==========================================
# 2. OpenWeatherMap 気圧取得モジュール
# ==========================================
def get_current_pressure():
    # 大西港付近の座標
    lat, lon = 34.23, 132.83
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ja"
    
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            pressure = data["main"]["pressure"]
            print(f"【現在気象】取得成功: {pressure} hPa (場所: {data.get('name')})")
            return pressure
        else:
            print(f"【気象APIエラー】Code: {res.status_code}")
            return STANDARD_PRESSURE
    except Exception:
        print("【通信エラー】気象データの取得に失敗。標準気圧を使用します。")
        return STANDARD_PRESSURE

# ==========================================
# 3. メイン処理 (大西港 補正実行)
# ==========================================
def main_calculate_onishi(target_date_str):
    # 1. 潮汐データの準備 (キャッシュがあればそれを使う想定)
    tide_data_db = fetch_jma_tide_data(TARGET_YEAR, STATION_CODE)
    
    if target_date_str not in tide_data_db:
        print(f"指定された日付({target_date_str})のデータが見つかりません。")
        return

    # 2. 気圧取得
    current_hpa = get_current_pressure()
    
    # 3. 補正計算
    # 吸い上げ効果: (1013 - 現在気圧) cm
    pressure_correction = int(STANDARD_PRESSURE - current_hpa)
    
    print("\n" + "="*50)
    print(f" 🚢 大西港 (大崎上島) リアルタイム潮汐予測 ")
    print(f" 日付: {target_date_str}")
    print(f" 条件: 気圧 {current_hpa}hPa (補正値: {pressure_correction:+d}cm)")
    print(f" 定数: 基準差 +{LEVEL_BASE_OFFSET}cm / 時間 +{TIME_OFFSET_MIN}分")
    print("="*50)
    print(f"時刻  | 予測潮位 | 潮名 | (参考:竹原生データ)")
    print("-" * 50)
    
    daily_tides = tide_data_db[target_date_str]
    
    for tide in daily_tides:
        # 時刻の補正
        t_hour, t_min = map(int, tide['time'].split(':'))
        # 分を加算して繰り上がり処理
        total_m = t_hour * 60 + t_min + TIME_OFFSET_MIN
        new_h = (total_m // 60) % 24
        new_m = total_m % 60
        new_time_str = f"{new_h:02d}:{new_m:02d}"
        
        # 潮位の補正
        final_level = tide['level'] + LEVEL_BASE_OFFSET + pressure_correction
        
        print(f"{new_time_str} | {int(final_level):4d} cm | {tide['type']} | {tide['time']} / {int(tide['level'])}cm")

# ==========================================
# 実行エントリーポイント
# ==========================================
if __name__ == "__main__":
    # テストとして今日の日付で実行 (または2026年の特定日)
    # 実際の運用では datetime.date.today() を使用
    today_str = f"{TARGET_YEAR}-01-04" # 紙面比較用のテスト日
    
    main_calculate_onishi(today_str)
