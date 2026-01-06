import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# --- 1. 設定部分 ---
TARGET_LEVEL = 140  # 指定潮位 (cm)
START_DATE = '2024-01-01'
END_DATE = '2024-02-01' # 1ヶ月分

# --- 2. データ生成 (実際はここでCSV読み込みやAPI取得を行います) ---
# 10分刻みの時間データを作成
dates = pd.date_range(start=START_DATE, end=END_DATE, freq='10T')

# 疑似的な潮汐データを作成 (サイン波の合成で潮の満ち引きを再現)
# 実際には `df['tide_level']` のように実データを使用してください
t = np.arange(len(dates))
tide_levels = 100 + 60 * np.sin(t / 70) + 30 * np.sin(t / 365) + np.random.normal(0, 2, len(t))

df = pd.DataFrame({'timestamp': dates, 'level': tide_levels})

# --- 3. 指定潮位との交点（時間）を計算するロジック ---
# 前のデータと現在のデータの間で、指定潮位をまたいだ場所を探す
# sign: 潮位が指定値より上なら1, 下なら-1
signs = np.sign(df['level'] - TARGET_LEVEL)
# diff: 符号が変わった場所（またいだ場所）が非ゼロになる
crossing_indices = np.where(np.diff(signs))[0]

# 交点の時間と潮位を取得
crossing_dates = df['timestamp'].iloc[crossing_indices]
crossing_levels = df['level'].iloc[crossing_indices]

# --- 4. グラフ描画 ---
fig, ax = plt.subplots(figsize=(15, 6)) # 1ヶ月分なので横長にする

# メインの潮位線
ax.plot(df['timestamp'], df['level'], label='Tide Level', color='blue', linewidth=1)

# 指定潮位のライン（赤色・破線）
ax.axhline(y=TARGET_LEVEL, color='red', linestyle='--', label=f'Target: {TARGET_LEVEL}cm')

# 指定潮位に到達した時間（交点）をプロット
ax.scatter(crossing_dates, crossing_levels, color='red', zorder=5, s=30, marker='o')

# --- 5. グラフの見た目を調整 ---
ax.set_title(f"Tide Graph ({START_DATE} - {END_DATE})", fontsize=14)
ax.set_ylabel("Tide Level (cm)")
ax.set_xlabel("Date")
ax.grid(True, which='both', linestyle='--', alpha=0.5)

# 横軸の日付フォーマット調整 (1ヶ月分を見やすく)
ax.xaxis.set_major_locator(mdates.DayLocator(interval=2)) # 2日おきに目盛り
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
plt.xticks(rotation=45) # 日付が重ならないように斜めにする

# 凡例を表示
ax.legend()

# レイアウト調整と表示
plt.tight_layout()
plt.show()

# --- (参考) 指定潮位になった時間をリスト表示 ---
print(f"--- 指定潮位 ({TARGET_LEVEL}cm) に到達した時間 ---")
for d in crossing_dates:
    print(d.strftime('%Y-%m-%d %H:%M'))
