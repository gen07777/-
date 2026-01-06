import streamlit as st
import datetime
import math
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ---------------------------------------------------------
# Tide Calculation Logic
# ---------------------------------------------------------
class OnishiTideCalculator:
    def __init__(self):
        self.CORRECTION_RATIO = 1.0
        self.TIME_OFFSET_MINUTES = 0
        self.MSL = 250.0 
        self.CONSTITUENTS = {
            'M2': {'amp': 130.0, 'phase': 200.0, 'speed': 28.9841042},
            'S2': {'amp': 50.0,  'phase': 230.0, 'speed': 30.0000000},
            'K1': {'amp': 35.0,  'phase': 180.0, 'speed': 15.0410686},
            'O1': {'amp': 30.0,  'phase': 160.0, 'speed': 13.9430356}
        }

    def _calculate_astronomical_tide(self, target_datetime):
        base_date = datetime.datetime(target_datetime.year, 1, 1)
        delta_hours = (target_datetime - base_date).total_seconds() / 3600.0
        tide_height = self.MSL
        for name, const in self.CONSTITUENTS.items():
            theta = math.radians(const['speed'] * delta_hours - const['phase'])
            tide_height += const['amp'] * math.cos(theta)
        return tide_height

    def get_onishi_prediction(self, target_date):
        # Create data every 10 minutes for smoother graph
        detailed_data = []
        # Calculate for 0:00 to 23:50
        start_time = datetime.datetime(target_date.year, target_date.month, target_date.day)
        
        for i in range(24 * 6): # 24 hours * 6 (every 10 mins)
            calc_time = start_time + datetime.timedelta(minutes=i * 10)
            
            # Apply offset
            calc_time_offset = calc_time - datetime.timedelta(minutes=self.TIME_OFFSET_MINUTES)
            base_level = self._calculate_astronomical_tide(calc_time_offset)
            onishi_level = base_level * self.CORRECTION_RATIO
            
            detailed_data.append({
                "raw_time": calc_time,
                "Level_cm": onishi_level
            })
        return detailed_data

    def find_times_for_target_level(self, detailed_data, target_level):
        found_times = []
        # Check intervals
        for i in range(len(detailed_data) - 1):
            p1 = detailed_data[i]
            p2 = detailed_data[i+1]
            y1 = p1['Level_cm']
            y2 = p2['Level_cm']
            
            if (y1 <= target_level <= y2) or (y1 >= target_level >= y2):
                # Linear interpolation
                if y2 == y1: continue
                fraction = (target_level - y1) / (y2 - y1)
                minutes_add = fraction * 10 # 10 minute interval
                found_time = p1['raw_time'] + datetime.timedelta(minutes=minutes_add)
                
                trend = "UP" if y2 > y1 else "DOWN"
                time_str = found_time.strftime("%H:%M")
                found_times.append(f"{time_str} ({trend})")
        return found_times

# ---------------------------------------------------------
# App Layout
# ---------------------------------------------------------
st.title("Tide Visualizer")
st.write("Onishi Port")

# 1. Inputs
col1, col2 = st.columns(2)
with col1:
    target_date = st.date_input("Date", datetime.date.today())
with col2:
    target_cm = st.number_input("Target Level (cm)", value=150, step=10)

# 2. Calculation
calculator = OnishiTideCalculator()
# Ensure correct date type
calc_date = datetime.datetime(target_date.year, target_date.month, target_date.day)
prediction_data = calculator.get_onishi_prediction(calc_date)

# 3. Result Text
st.subheader(f"Time for {target_cm} cm")
matched_times = calculator.find_times_for_target_level(prediction_data, target_cm)

if matched_times:
    st.success(" / ".join(matched_times))
else:
    st.info("Level not reached on this date.")

# 4. Matplotlib Graph (Fixes 'removeChild' error and allows fill)
st.subheader("Visual Graph")

# Prepare DataFrame
df = pd.DataFrame(prediction_data)

# Create Plot
fig, ax = plt.subplots(figsize=(10, 5))

# Plot the main tide line
ax.plot(df['raw_time'], df['Level_cm'], label='Tide Level', color='#1f77b4', linewidth=2)

# Plot the target line
ax.axhline(y=target_cm, color='black', linestyle='--', linewidth=1, label=f'Target ({target_cm}cm)')

# FILL LOGIC: Fill red where tide is BELOW target
# "where" condition: Level <= target
ax.fill_between(df['raw_time'], df['Level_cm'], target_cm, 
                where=(df['Level_cm'] <= target_cm), 
                color='red', alpha=0.3, interpolate=True, label='Below Target')

# Formatting
ax.set_ylabel("Level (cm)")
ax.set_title(f"Tide on {target_date.strftime('%Y-%m-%d')}")
ax.grid(True, alpha=0.3)
ax.legend(loc='upper right')

# X-axis formatting (Hours)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
ax.xaxis.set_major_locator(mdates.HourLocator(interval=3)) # Show every 3 hours
plt.xticks(rotation=0)

# Display in Streamlit
st.pyplot(fig)

# Show data table inside expander
with st.expander("Show Detailed Data"):
    # Format time for display
    display_df = df.copy()
    display_df['Time'] = display_df['raw_time'].apply(lambda x: x.strftime('%H:%M'))
    display_df['Level_cm'] = display_df['Level_cm'].round(1)
    st.dataframe(display_df[['Time', 'Level_cm']])
