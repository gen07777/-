import streamlit as st
import requests
import datetime
from datetime import timedelta
import pandas as pd
import altair as alt # 高度なグラフ描画用

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
BASE_BACKUP_DATA = [230, 275, 290, 265, 210, 140, 70, 30, 40, 100, 180, 260, 315, 330, 300, 240, 170, 110, 80, 85, 130, 190, 250, 290]

def get_fallback_data(date_str):
    """データがない日のための補完データ生成"""
    try:
        base_date = datetime.date(2026, 1, 9)
        target = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        diff_days = (target - base_date).days
        shift = diff_days * 1 
        data = BASE_BACKUP_DATA
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
    """気象庁からデータを取得"""
    url = f"https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt/{year}/{station_code}.txt"
    headers = {"User-Agent": "Mozilla/5.0"}
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
def calculate_details(date_obj, hourly_tides, work_threshold, start_h, end_h, total_correction):
    """1日分の詳細データ計算"""
    corrected_levels = [h + total_correction for h in hourly_tides]
    
    # 作業時間の計算
    workable_ranges = []
    is_working = False
    start_time = None
    
    for h in range(24):
        # 作業時間枠チェック
        if h < start_h or h > end_h:
            if is_working:
                workable_ranges.append(f"{start_time:02d}:00～{h:02d}:00")
                is_working = False
            continue
            
        level = corrected_levels[h]
        if level <= work_threshold:
            if not is_working:
                is_working = True
                start_time = h
        else:
            if is_working:
                workable_ranges.append(f"{start_time:02d}:00～{h:02d}:00")
                is_working = False
                
    if is_working:
        end_display = end_h + 1 if end_h < 23 else 24
        workable_ranges.append(f"{start_time:02d}:00～{end_display:02d}:00")

    # 満干潮リスト作成
    peaks = []
    for i in range(1, 23):
        prev, curr, next_val = corrected_levels[i-1], corrected_levels[i], corrected_levels[i+1]
        total_m = i * 60 + TIME_OFFSET_MIN
        time_str = f"{(total_m // 60):02d}:{total_m % 60:02d}"
        
        if prev < curr and curr >= next_val:
            peaks.append({"時刻": time_str, "潮位": f"{curr}cm", "潮名": "満潮"})
        elif prev > curr and curr <= next_val:
            peaks.append({"時刻": time_str, "潮位": f"{curr}cm", "潮名": "干潮"})

    return {
        "date": date_obj,
        "levels": corrected_levels,
        "work_ranges": workable_ranges,
        "peaks": peaks
    }

def get_current_tide_level(hourly_levels, current_dt):
    """現在時刻の潮位を簡易補間"""
    # 簡易的に直近の時間の値を取得（本来は分単位補間推奨）
    hour = current_dt.hour
    if 0 <= hour < 24:
        return hourly_levels[hour]
    return 0

# ==========================================
# 4. メイン画面
# ==========================================
def main():
    st.set_page_config(page_title="大西港 週間潮汐", page_icon="⚓", layout="wide")
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

    # ヘッダー情報
    c1, c2, c3 = st.columns(3)
    c1.metric("現在気圧", f"{current_hpa} hPa")
    c2.metric("補正値", f"{total_level_correction:+} cm", help="基準13cm + 気圧差")
    
    # 現在時刻のポイント計算用
    now = datetime.datetime.now()
    # デモ用に年を2026年に強制補正して計算
    demo_now = now.replace(year=2026, month=1, day=9) # デモ基準日
    if selected_date == datetime.date(2026, 1, 9):
         current_point_dt = datetime.datetime.combine(selected_date, datetime.time(now.hour, now.minute))
    else:
         current_point_dt = None # 表示期間外なら点は出さない

    st.divider()

    # --- 5日分の計算処理 ---
    five_days_results = []
    graph_data_rows = []
    current_tide_val = None

    for i in range(5):
        target_date = selected_date + timedelta(days=i)
        d_str = target_date.strftime("%Y-%m-%d")
        
        if tide_db and d_str in tide_db:
            hourly = tide_db[d_str]
        else:
            hourly = get_fallback_data(d_str)
            
        res = calculate_details(target_date, hourly, work_threshold, start_h, end_h, total_level_correction)
        five_days_results.append(res)
        
        # グラフデータ作成
        for hour, level in enumerate(res["levels"]):
            dt = datetime.datetime.combine(target_date, datetime.time(hour, 0))
            graph_data_rows.append({"日時": dt, "潮位": level, "タイプ": "予測値"})
            
            # 現在時刻の潮位を取得 (グラフ上の点用)
            if current_point_dt and dt.date() == current_point_dt.date() and dt.hour == current_point_dt.hour:
                current_tide_val = level

    # ==========================================
    # 表示エリア 1: 作業可能時間リスト (独立表示)
    # ==========================================
    st.subheader("✅ 週間 作業可能時間リスト")
    st.caption(f"条件: {start_h}:00-{end_h}:00 の間で {work_threshold}cm 以下")
    
    # 横並びで見やすく配置
    cols = st.columns(5)
    for idx, day_res in enumerate(five_days_results):
        with cols[idx]:
            date_text = day_res["date"].strftime("%m/%d (%a)")
            st.markdown(f"**{date_text}**")
            if day_res["work_ranges"]:
                for r in day_res["work_ranges"]:
                    st.success(r)
            else:
                st.warning("なし")

    # ==========================================
    # 表示エリア 2: グラフ (Altairで高度化)
    # ==========================================
    st.subheader("📈 5日間の潮汐グラフ")
    
    source = pd.DataFrame(graph_data_rows)
    
    # 1. 基本の折れ線 (青)
    line = alt.Chart(source).mark_line().encode(
        x=alt.X('日時:T', axis=alt.Axis(format='%m/%d %H:%M')),
        y=alt.Y('潮位:Q', scale=alt.Scale(domain=[min(source['潮位'])-20, max(source['潮位'])+20])),
        tooltip=['日時', '潮位']
    )
    
    # 2. 作業ライン (赤)
    rule = alt.Chart(pd.DataFrame({'y': [work_threshold]})).mark_rule(color='red', strokeDash=[5, 5]).encode(
        y='y'
    )
    
    # 3. 現在地点の点 (黄色)
    points_layer = []
    if current_tide_val is not None and current_point_dt is not None:
        c3.metric("現在潮位 (推計)", f"{current_tide_val} cm")
        point_df = pd.DataFrame([{"日時": current_point_dt, "潮位": current_tide_val}])
        point = alt.Chart(point_df).mark_point(color='yellow', size=200, filled=True, stroke='black').encode(
            x='日時:T',
            y='潮位:Q',
            tooltip=['日時', '潮位']
        )
        points_layer.append(point)

    # グラフ合成
    chart = alt.layer(line, rule, *points_layer).properties(
        height=350,
        width='container'
    ).interactive()
    
    st.altair_chart(chart, use_container_width=True)

    # ==========================================
    # 表示エリア 3: 干満リスト (グラフ外に分離)
    # ==========================================
    st.subheader("🌊 満潮・干潮データ")
    
    cols_peak = st.columns(5)
    for idx, day_res in enumerate(five_days_results):
        with cols_peak[idx]:
            st.caption(day_res["date"].strftime("%m/%d"))
            if day_res["peaks"]:
                df_p = pd.DataFrame(day_res["peaks"])
                st.dataframe(df_p, hide_index=True, use_container_width=True)
            else:
                st.text("-")

if __name__ == "__main__":
    main()
