import streamlit as st
import requests
import datetime
from datetime import timedelta
import pandas as pd
import numpy as np

# ==========================================
# 設定エリア
# ==========================================
OPENWEATHER_API_KEY = "f8b87c403597b305f1bbf48a3bdf8dcb"
STATION_CODE = "344311"  # 竹原
TARGET_YEAR = 2026       # デフォルト年

# 大西港 補正定数
TIME_OFFSET_MIN = 1       # 時間補正 +1分
LEVEL_BASE_OFFSET = 13    # 基準面補正 +13cm
STANDARD_PRESSURE = 1013  # 標準気圧

# ==========================================
# 1. バックアップデータ & データ補完
# ==========================================
# 基準となるデータ（1月9日）
BASE_BACKUP_DATA = [230, 275, 290, 265, 210, 140, 70, 30, 40, 100, 180, 260, 315, 330, 300, 240, 170, 110, 80, 85, 130, 190, 250, 290]

def get_fallback_data(date_str):
    """
    データがない日でもデモ用にそれっぽいデータを生成する関数
    （基準データから毎日約50分ずつ時間をずらして生成）
    """
    # 簡易ロジック: 日付の差分を計算
    base_date = datetime.date(2026, 1, 9)
    try:
        target = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        diff_days = (target - base_date).days
        
        # データを回転（シフト）させて疑似生成
        # 1日あたり約50分(データ配列のindexでいうと約0.8個分)ズレるが、
        # ここでは簡易的に1時間(index 1)ずつずらしてデモ表示する
        shift = diff_days * 1 
        data = BASE_BACKUP_DATA
        
        # 配列を回転
        num_items = len(data)
        shifted_data = [data[(i - shift) % num_items] for i in range(num_items)]
        return shifted_data
    except:
        return BASE_BACKUP_DATA

# ==========================================
# 2. データ取得 & 解析ロジック
# ==========================================
@st.cache_data(ttl=3600)
def fetch_jma_tide_data(year, station_code):
    """気象庁から年間の全データを取得"""
    url = f"https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt/{year}/{station_code}.txt"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    
    data_map = {}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            lines = response.text.splitlines()
            for line in lines:
                parts = line.split()
                if len(parts) < 28 or not parts[0].isdigit():
                    continue
                m_month = int(parts[2])
                m_day   = int(parts[3])
                d_str = f"{year}-{m_month:02d}-{m_day:02d}"
                hourly_levels = [int(h) for h in parts[4:28]]
                data_map[d_str] = hourly_levels
    except Exception:
        pass
    
    return data_map

def get_current_pressure():
    lat, lon = 34.23, 132.83
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ja"
    try:
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            return res.json()["main"]["pressure"]
    except Exception:
        pass
    return STANDARD_PRESSURE

# ==========================================
# 3. 計算ロジック
# ==========================================
def process_daily_data(date_obj, hourly_tides, work_threshold, start_h, end_h, total_correction):
    """1日分のデータを処理して、作業時間とグラフ用データを返す"""
    
    # 潮位補正
    corrected_levels = [h + total_correction for h in hourly_tides]
    
    # --- 作業可能時間の計算 ---
    workable_ranges = []
    is_working = False
    start_time = None
    
    for h in range(24):
        # 作業時間枠外チェック
        if h < start_h or h > end_h:
            if is_working:
                workable_ranges.append(f"{start_time:02d}:00 ～ {h:02d}:00")
                is_working = False
            continue
            
        level = corrected_levels[h]
        if level <= work_threshold:
            if not is_working:
                is_working = True
                start_time = h
        else:
            if is_working:
                workable_ranges.append(f"{start_time:02d}:00 ～ {h:02d}:00")
                is_working = False
                
    if is_working:
        end_display = end_h + 1 if end_h < 23 else 24
        workable_ranges.append(f"{start_time:02d}:00 ～ {end_display:02d}:00")

    # --- 満干潮の特定 ---
    peaks = []
    for i in range(1, 23):
        prev, curr, next_val = corrected_levels[i-1], corrected_levels[i], corrected_levels[i+1]
        
        # 時間補正 (+1分)
        total_m = i * 60 + TIME_OFFSET_MIN
        time_str = f"{(total_m // 60):02d}:{total_m % 60:02d}"
        
        if prev < curr and curr >= next_val:
            peaks.append(f"満 {time_str} ({curr}cm)")
        elif prev > curr and curr <= next_val:
            peaks.append(f"干 {time_str} ({curr}cm)")

    return {
        "date": date_obj,
        "levels": corrected_levels,
        "work_ranges": workable_ranges,
        "peaks": peaks
    }

# ==========================================
# 4. メイン画面
# ==========================================
def main():
    st.set_page_config(page_title="大西港 週間潮汐", page_icon="⚓")
    st.title("⚓ 大西港 (大崎上島) 週間潮汐")
    
    # --- サイドバー設定 ---
    with st.sidebar:
        st.header("⚙️ 設定")
        default_date = datetime.date(2026, 1, 9)
        selected_date = st.date_input("開始日", default_date)
        
        st.divider()
        st.subheader("🛠 作業条件")
        work_threshold = st.slider("潮位ライン (cm以下)", 0, 400, 120)
        work_time_range = st.slider("作業時間帯", 0, 24, (7, 23))
        start_h, end_h = work_time_range

    # --- データ準備 ---
    tide_db = fetch_jma_tide_data(TARGET_YEAR, STATION_CODE)
    current_hpa = get_current_pressure()
    pressure_diff = STANDARD_PRESSURE - current_hpa
    total_level_correction = LEVEL_BASE_OFFSET + pressure_diff

    # --- ヘッダー情報 ---
    c1, c2 = st.columns(2)
    c1.metric("現在気圧", f"{current_hpa} hPa")
    c2.metric("補正値", f"{total_level_correction:+} cm", help="基準13cm + 気圧差")
    st.divider()

    # --- 5日分のデータ処理 ---
    five_days_results = []
    graph_data_list = []
    
    for i in range(5):
        target_date = selected_date + timedelta(days=i)
        d_str = target_date.strftime("%Y-%m-%d")
        
        # データ取得 (なければ補完データ)
        if tide_db and d_str in tide_db:
            hourly = tide_db[d_str]
        else:
            hourly = get_fallback_data(d_str)
            
        # 計算実行
        res = process_daily_data(target_date, hourly, work_threshold, start_h, end_h, total_level_correction)
        five_days_results.append(res)
        
        # グラフ用データの作成 (日時index)
        for hour, level in enumerate(res["levels"]):
            dt = datetime.datetime.combine(target_date, datetime.time(hour, 0))
            graph_data_list.append({
                "日時": dt,
                "予測潮位": level,
                "作業ライン": work_threshold
            })

    # ==========================================
    # 表示 1: 5日間の連続グラフ (トップ配置)
    # ==========================================
    st.subheader(f"📈 5日間の潮汐グラフ ({selected_date.strftime('%m/%d')} ～)")
    
    df_graph = pd.DataFrame(graph_data_list).set_index("日時")
    st.line_chart(
        df_graph,
        color=["#0000FF", "#FF0000"],
        height=300 
    )

    # ==========================================
    # 表示 2: 日別リスト (印刷・スマホ用)
    # ==========================================
    st.subheader("📋 日別 作業可能時間 & 潮汐")
    st.caption(f"条件: {start_h}:00-{end_h}:00 の間で {work_threshold}cm 以下")

    for day_res in five_days_results:
        # 日付ヘッダー
        date_text = day_res["date"].strftime("%m/%d (%a)")
        
        with st.container():
            st.markdown(f"### {date_text}")
            
            col_a, col_b = st.columns([1, 1])
            
            # 左: 作業時間
            with col_a:
                st.markdown("**✅ 作業可能**")
                if day_res["work_ranges"]:
                    for r in day_res["work_ranges"]:
                        st.success(f"🕒 {r}")
                else:
                    st.warning("なし")
            
            # 右: 満干潮
            with col_b:
                st.markdown("**🌊 満潮・干潮**")
                for p in day_res["peaks"]:
                    st.text(p)
            
            st.markdown("---") # 区切り線

if __name__ == "__main__":
    main()
