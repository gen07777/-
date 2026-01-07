import streamlit as st
import datetime
import math
import calendar
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import re
import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------
# アプリ設定
# ---------------------------------------------------------
st.set_page_config(layout="wide")

# ---------------------------------------------------------
# スクレイピング関数 (大西港フェリーターミナル専用)
# ---------------------------------------------------------
def fetch_chowari_data():
    """
    Chowariのサイトから今日の満潮データを取得する
    成功すれば (time_obj, level_int) を返す
    失敗すれば None を返す
    """
    url = "https://tide.chowari.jp/34/344311/22694/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=3)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # 今日の日付を取得 (サイト上の表記に合わせる必要があるが、簡易的に「今日のデータ」を探す)
        # Chowariは通常、当日のデータがハイライトされているか、テーブルの最初の方にある
        # ここでは簡易的に「最初の満潮データ」を抽出するロジックを組む
        
        # ※サイトの構造が変わると動かなくなるリスクがあります
        # class="tide_table" などを探す
        
        # 【重要】簡易解析ロジック
        # サイト構造が複雑なため、メタタグや特定のクラスから「満潮」の数字を探す
        # ここでは失敗時の安全策を最優先し、例外処理で囲みます
        
        # 実際のChowariのテーブル構造に合わせて解析（仮定）
        # <td class="high">12:34<br>350</td> のような構造を想定
        
        # 実際にはサイトごとに構造が違うため、汎用的な「数字拾い」は難しいですが、
        # 成功率を上げるために「high_tide」等のキーワード周辺を探します。
        
        # 今回はデモとして「取得成功したフリ」ではなく、
        # 実際にアクセスして取れなければNoneを返す実装にします。
        
        # (解析ロジックが複雑になりすぎるため、アクセス可否のチェックを主目的とします)
        if response.status_code == 200:
            # ここで本来は soup.find... で値を抜きますが、
            # サイト構造の変更に弱いため、あえて「成功したら初期値に戻す」等の処理はせず
            # ユーザーに手入力を促すか、固定値を返す構造にします。
            
            # もし本当にスクレイピングするなら以下のようなコードが必要ですが
            # Streamlit Cloudではほぼブロックされるため、ダミー実装に近い形にします。
            return None 

    except Exception:
        return None
    
    return None

# ---------------------------------------------------------
# 物理計算ロジック
# ---------------------------------------------------------
class HarmonicTideModel:
    def __init__(self):
        self.SPEEDS = {
            'M2': 28.9841042, 'S2': 30.0000000,
            'K1': 15.0410686, 'O1': 13.9430356
        }
        self.base_consts = {
            'M2': {'amp': 128.0, 'phase': 203.0},
            'S2': {'amp': 48.0,  'phase': 236.0},
            'K1': {'amp': 35.0,  'phase': 187.0},
            'O1': {'amp': 30.0,  'phase': 169.0}
        }
        self.msl = 240.0 
        self.phase_offset = 0

    def calibrate(self, target_high_time, target_high_level):
        search_start = target_high_time - datetime.timedelta(hours=3)
        search_end = target_high_time + datetime.timedelta(hours=3)
        best_time = search_start
        max_level = -9999
        dt = search_start
        while dt <= search_end:
            lvl = self._calc_raw(dt, phase_shift=0, msl_shift=0)
            if lvl > max_level:
                max_level = lvl
                best_time = dt
            dt += datetime.timedelta(minutes=1)
        
        time_diff_minutes = (target_high_time - best_time).total_seconds() / 60.0
        self.phase_offset = time_diff_minutes * 0.48
        height_diff = target_high_level - max_level
        self.msl += height_diff
        return time_diff_minutes, height_diff

    def _calc_raw(self, target_dt, phase_shift=0, msl_shift=0):
        base_dt = datetime.datetime(target_dt.year, 1, 1)
        delta_hours = (target_dt - base_dt).total_seconds() / 3600.0
        level = self.msl + msl_shift
        for name, speed in self.SPEEDS.items():
            const = self.base_consts[name]
            phase = const['phase'] - phase_shift 
            theta = math.radians(speed * delta_hours - phase)
            level += const['amp'] * math.cos(theta)
        return level

    def calculate_level(self, target_dt):
        return self._calc_raw(target_dt, self.phase_offset, 0)

    def get_period_data(self, year, month, start_day, end_day, interval_minutes=5):
        detailed_data = []
        start_dt = datetime.datetime(year, month, start_day)
        last_day_of_month = calendar.monthrange(year, month)[1]
        if end_day > last_day_of_month: end_day = last_day_of_month
        end_dt = datetime.datetime(year, month, end_day, 23, 55)

        current_dt = start_dt
        while current_dt <= end_dt:
            level = self.calculate_level(current_dt)
            detailed_data.append({"raw_time": current_dt, "Level_cm": level})
            current_dt += datetime.timedelta(minutes=interval_minutes)
        return detailed_data

# ---------------------------------------------------------
# メイン画面構成
# ---------------------------------------------------------
st.title("大西港 潮位ビジュアライザー (自動同調版)")

# 現在時刻 (JST)
now_utc = datetime.datetime.now(datetime.timezone.utc)
now_jst = now_utc + datetime.timedelta(hours=9)
now_jst = now_jst.replace(tzinfo=None, second=0, microsecond=0)

# --- サイドバー: サイト合わせ込み ---
with st.sidebar:
    st.header("🔧 補正設定")
    
    # 自動取得ボタン
    if st.button("📡 サイトから自動取得（試行）"):
        # 実際にスクレイピングを試みるロジック
        # (Streamlit Cloudではブロックされる可能性が高いですが、トライします)
        try:
            url = "https://tide.chowari.jp/34/344311/22694/"
            res = requests.get(url, timeout=3)
            if res.status_code == 200:
                soup = BeautifulSoup(res.content, "html.parser")
                # Chowariのテーブル構造から今日の満潮を探す(非常に簡易的な探索)
                # ※サイト構造が変わると動作しません
                
                # 今日の日付セルを探す (例: "7(水)" のような表記)
                day_str = f"{now_jst.day}("
                found = False
                
                # テーブル内の全セルを走査
                for td in soup.find_all("td"):
                    if day_str in td.text:
                        # 日付が見つかったら、その行(tr)の満潮セルを探す
                        parent = td.parent
                        high_tides = parent.find_all("td", class_="red") # 満潮は赤字クラス等の場合が多い
                        
                        if high_tides:
                            # 最初の満潮テキスト "12:34 350" のような形式を解析
                            text = high_tides[0].get_text(strip=True)
                            # 正規表現で時間と数値を抜く
                            m = re.search(r"(\d{1,2}:\d{2}).*?(\d{2,3})", text)
                            if m:
                                t_str = m.group(1)
                                l_str = m.group(2)
                                
                                # session_stateに保存して再描画
                                st.session_state['auto_time'] = datetime.datetime.strptime(t_str, "%H:%M").time()
                                st.session_state['auto_level'] = int(l_str)
                                st.session_state['auto_msg'] = "✅ 取得成功!"
                                found = True
                                break
                
                if not found:
                    st.error("データの解析に失敗しました(サイト構造不一致)")
            else:
                st.error("サイトにアクセスできませんでした(IP制限)")
        except:
            st.error("通信エラー: 自動取得できませんでした")

    # session_stateから値を取り出す（なければデフォルト）
    def_time = st.session_state.get('auto_time', datetime.time(12, 0))
    def_level = st.session_state.get('auto_level', 350)
    
    if 'auto_msg' in st.session_state:
        st.success(st.session_state['auto_msg'])

    st.info("補正基準値を入力 (サイトの今日の満潮データ)")
    cal_date = st.date_input("日付", value=now_jst.date())
    cal_time = st.time_input("満潮時刻", value=def_time)
    cal_height = st.number_input("満潮潮位 (cm)", value=def_level, step=10)
    
    st.markdown("---")
    st.write("※1点を合わせれば全体が補正されます")

# --- 設定エリア ---
col1, col2 = st.columns(2)
with col1:
    st.markdown("##### 1. 期間設定")
    year_sel = st.number_input("年", value=now_jst.year)
    period_options = [f"{m}月前半" for m in range(1, 13)] + [f"{m}月後半" for m in range(1, 13)]
    period_options = sorted(period_options, key=lambda x: int(x.split('月')[0]) + (0.5 if '後半' in x else 0))
    current_idx = (now_jst.month - 1) * 2
    if now_jst.day > 15: current_idx += 1
    selected_period = st.selectbox("期間", period_options, index=current_idx)

with col2:
    st.markdown("##### 2. ターゲット設定")
    target_cm = st.number_input("基準潮位(cm)", value=130, step=10)
    start_hour, end_hour = st.slider("活動時間", 0, 24, (7, 23), format="%d時")

# --- 計算 & キャリブレーション ---
model = HarmonicTideModel()
target_cal_dt = datetime.datetime.combine(cal_date, cal_time)
diff_min, diff_cm = model.calibrate(target_cal_dt, cal_height)

# --- 期間データ生成 ---
try:
    month_match = re.match(r"(\d+)月", selected_period)
    month_sel = int(month_match.group(1))
    is_first_half = "前半" in selected_period
except:
    month_sel = now_jst.month
    is_first_half = True

last_day = calendar.monthrange(year_sel, month_sel)[1]
if is_first_half:
    start_d, end_d = 1, 15
else:
    start_d, end_d = 16, last_day

data = model.get_period_data(year_sel, month_sel, start_d, end_d)
df = pd.DataFrame(data)
current_tide_level = model.calculate_level(now_jst)

if df.empty:
    st.error("データがありません。")
else:
    # ---------------------------------------------------------
    # グラフ描画
    # ---------------------------------------------------------
    st.subheader(f"潮位グラフ: {selected_period}")
    st.success(f"✅ 自動補正完了: モデルを {diff_min:+.1f}分 / {diff_cm:+.1f}cm シフトしました")

    fig, ax = plt.subplots(figsize=(15, 10))

    # メイン線
    ax.plot(df['raw_time'], df['Level_cm'], color='#1f77b4', linewidth=1.5, alpha=0.9, label="潮位")
    ax.axhline(y=target_cm, color='black', linestyle='--', linewidth=1, label=f"基準 ({target_cm}cm)")

    # 塗りつぶし
    hours = df['raw_time'].dt.hour
    is_time_ok = (hours >= start_hour) & (hours < end_hour)
    is_level_ok = (df['Level_cm'] <= target_cm)
    ax.fill_between(df['raw_time'], df['Level_cm'], target_cm, 
                    where=(is_level_ok & is_time_ok), 
                    color='red', alpha=0.3, interpolate=True)

    # ピーク検出
    levels = df['Level_cm'].values
    times = df['raw_time'].tolist()
    
    for i in range(1, len(levels) - 1):
        if levels[i-1] < levels[i] and levels[i] > levels[i+1]:
            ax.scatter(times[i], levels[i], color='red', s=30, zorder=5, marker='^')
            ax.annotate(f"{times[i].strftime('%H:%M')}\n{levels[i]:.0f}",
                        xy=(times[i], levels[i]), xytext=(0, 15),
                        textcoords='offset points', ha='center', va='bottom',
                        fontsize=9, color='#AA0000', fontweight='bold')
        elif levels[i-1] > levels[i] and levels[i] < levels[i+1]:
            ax.scatter(times[i], levels[i], color='blue', s=30, zorder=5, marker='v')
            ax.annotate(f"{times[i].strftime('%H:%M')}\n{levels[i]:.0f}",
                        xy=(times[i], levels[i]), xytext=(0, -25),
                        textcoords='offset points', ha='center', va='top',
                        fontsize=9, color='#0000AA', fontweight='bold')

    # 現在時刻
    graph_start = df['raw_time'].iloc[0]
    graph_end = df['raw_time'].iloc[-1]
    
    if graph_start <= now_jst <= graph_end:
        ax.scatter(now_jst, current_tide_level, color='yellow', s=180, zorder=10, edgecolors='black', linewidth=1.5)
        ax.annotate(f"Now\n{now_jst.strftime('%H:%M')}\n{current_tide_level:.0f}cm", 
                    xy=(now_jst, current_tide_level), xytext=(0, 50),
                    textcoords='offset points', ha='center', va='bottom',
                    fontsize=10, fontweight='bold', color='black',
                    bbox=dict(boxstyle="round,pad=0.3", fc="yellow", ec="black", alpha=0.8),
                    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0', color='black'))

    # Start/End/Duration
    df['in_target'] = is_level_ok & is_time_ok
    df['change'] = df['in_target'].ne(df['in_target'].shift()).cumsum()
    groups = df[df['in_target']].groupby('change')
    
    label_offset_counter = 0
    for _, group in groups:
        start_t = group['raw_time'].iloc[0]
        end_t = group['raw_time'].iloc[-1]
        duration = end_t - start_t
        total_minutes = int(duration.total_seconds() / 60)
        
        if total_minutes < 10: continue

        stagger = (label_offset_counter % 2) * 20
        label_offset_counter += 1
        font_size = 8
        
        y_pos_start = target_cm + 20 + stagger
        ax.annotate(start_t.strftime("%H:%M"), 
                    xy=(start_t, target_cm), xytext=(0, y_pos_start - target_cm),
                    textcoords='offset points', ha='center', va='bottom', 
                    fontsize=font_size, color='blue', fontweight='bold',
                    arrowprops=dict(arrowstyle='-', color='blue', linewidth=0.5, linestyle=':'))

        y_pos_end = target_cm - 20 - stagger
        ax.annotate(end_t.strftime("%H:%M"), 
                    xy=(end_t, target_cm), xytext=(0, y_pos_end - target_cm), 
                    textcoords='offset points', ha='center', va='top', 
                    fontsize=font_size, color='green', fontweight='bold',
                    arrowprops=dict(arrowstyle='-', color='green', linewidth=0.5, linestyle=':'))

        hours_dur = total_minutes // 60
        mins_dur = total_minutes % 60
        dur_str = f"{hours_dur}h{mins_dur}m"
        mid_time = start_t + (duration / 2)
        y_pos_dur = y_pos_end - 25 
        
        ax.text(mid_time, y_pos_dur, dur_str, 
                ha='center', va='top', 
                fontsize=font_size, fontweight='bold', color='#cc0000',
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.6))

    ax.set_ylabel("Level (cm)")
    ax.grid(True, which='both', linestyle='--', alpha=0.3)
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d'))
    ax.set_xlim(df['raw_time'].iloc[0], df['raw_time'].iloc[-1])
    
    st.pyplot(fig)
