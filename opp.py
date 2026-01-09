def calculate_onishi_tide(takehara_tide_data, current_pressure_hpa):
    """
    竹原のデータと気圧から、紙面（大西港）相当の予測値を算出する
    """
    
    # 1. 定数の定義
    TIME_OFFSET_MINUTES = 1    # 時間補正：常に+1分（紙面の傾向に合わせる）
    LEVEL_OFFSET_CM = 13       # 基準面補正：常に+13cm（底上げ）
    STANDARD_PRESSURE = 1013   # 標準気圧 (hPa)

    # 2. 気圧補正値の計算（吸い上げ効果）
    # 気圧が1hPa下がると、潮位は約1cm上昇する
    # (例: 983hPaなら +30cm)
    pressure_correction = (STANDARD_PRESSURE - current_pressure_hpa) * 1.0

    # 3. 最終予測値の算出
    predicted_tides = []
    
    for tide in takehara_tide_data:
        # 時間の補正
        onishi_time = tide['time'] + minutes(TIME_OFFSET_MINUTES)
        
        # 潮位の補正 (竹原の潮位 + 基準面補正 + 気圧補正)
        onishi_level = tide['level'] + LEVEL_OFFSET_CM + pressure_correction
        
        predicted_tides.append({
            'time': onishi_time,
            'level': int(onishi_level), # センチメートル
            'type': tide['type'] # 満潮/干潮
        })

    return predicted_tides
