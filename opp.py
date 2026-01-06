import streamlit as st
import datetime
import math
import calendar
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

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

    def get_period_data(self, start_date, days=1, interval_minutes=10):
        """Generates tide data for a specified period"""
        data = []
        start_dt = datetime.datetime(start_date.year, start_date.month, start_date.day)
        total_minutes = days * 24 * 60
        steps = int(total_minutes / interval_minutes)
        
        for i in range(steps): 
            calc_time = start_dt + datetime.timedelta(minutes=i * interval_minutes)
            calc_time_offset = calc_time - datetime.timedelta(minutes=self.TIME_OFFSET_MINUTES)
            base_level = self._calculate_astronomical_tide(calc_time_offset)
            onishi_level = base_level * self.CORRECTION_RATIO
            
            data.append({
                "raw_time": calc_time,
                "Level_cm": onishi_level
            })
        return data

    def find_crossing_points(self, df, target_level):
        """Finds exact times where tide crosses the target level"""
        crossings = []
        # Check where (level - target) changes sign
        # sign: +1 if above, -1 if below
        signs = np.sign(np.array(df['Level_cm']) - target_level)
        
        # Find indices where sign changes
        diffs = np.diff(signs)
        crossing_indices = np.where(diffs != 0)[0]
        
        for idx in crossing_indices:
            # Linear interpolation for precise time
            t1 = df['raw_time'].iloc[idx]
            t2 = df['raw_time'].iloc[idx+1]
            y1 = df['Level_cm'].iloc[idx]
            y2 = df['Level_cm'].iloc[idx+1]
            
            if y2 == y1: continue
            
            fraction = (target_level - y1) / (y2 - y1)
            crossing_time = t1 + (t2 - t1) * fraction
            
            trend = "UP" if y2 > y1 else "DOWN"
            crossings.append({
                "time": crossing_time,
                "level": target_level,
                "trend": trend
            })
        return crossings

# ---------------------------------------------------------
# App Layout
# ---------------------------------------------------------
st.title("Tide Visualizer")
st.write("Onishi Port")

# Global Settings
col_g1, col_g2 = st.columns(2)
with col_g1:
    target_date = st.date_input("Date", datetime.date.today())
with col_g2:
    target_cm = st.number_input("Target Level (cm)", value=150, step=10)

calculator = OnishiTideCalculator()
target_datetime = datetime.datetime(target_date.year, target_date.month, target_date.day)

# Tabs
tab1, tab2 = st.tabs(["📅 Monthly Graph", "📈 Daily Detail"])

# ==========================================
# TAB 1: Monthly Graph (1 Month)
# ==========================================
with tab1:
    st.subheader(f"Monthly View: {target_date.strftime('%Y-%m')}")
    
    # Calculate for the whole month
    days_in_month = calendar.monthrange(target_date.year, target_date.month)[1]
    start_of_month = datetime.date(target_date.year, target_date.month, 1)
    
    with st.spinner("Calculating monthly data..."):
        month_data = calculator.get_period_data(start_of_month, days=days_in_month, interval_minutes=30)
        df_month = pd.DataFrame(month_data)

    # Plot
    fig_m, ax_m = plt.subplots(figsize=(10, 4))
    ax_m.plot(df_month['raw_time'], df_month['Level_cm'], color='#1f77b4', linewidth=1, label='Tide')
    ax_m.axhline(y=target_cm, color='red', linestyle='--', linewidth=1, label=f'Target {target_cm}cm')
    
    # Layout
    ax_m.set_ylabel("cm")
    ax_m.grid(True, alpha=0.3)
    # X-axis: Show days
    ax_m.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    ax_m.xaxis.set_major_formatter(mdates.DateFormatter('%d'))
    ax_m.set_xlabel("Day")
    
    st.pyplot(fig_m)
    st.caption("※ The red line is your target level.")

# ==========================================
# TAB 2: Daily Detail (24 Hours)
# ==========================================
with tab2:
    st.subheader(f"Daily View: {target_date.strftime('%Y-%m-%d')}")
    
    # Calculate for 1 day (High precision: 5 min)
    day_data = calculator.get_period_data(target_date, days=1, interval_minutes=5)
    df_day = pd.DataFrame(day_data)
    
    # Find exact crossing points
    crossings = calculator.find_crossing_points(df_day, target_cm)
    
    # Text Result
    if crossings:
        times_str = [f"**{c['time'].strftime('%H:%M')}** ({c['trend']})" for c in crossings]
        st.success("Target Time: " + "  /  ".join(times_str))
    else:
        st.info("Level not reached on this date.")

    # Plot
    fig_d, ax_d = plt.subplots(figsize=(10, 5))
    
    # Main Line
    ax_d.plot(df_day['raw_time'], df_day['Level_cm'], label='Tide Level', color='#1f77b4', linewidth=2)
    
    # Target Line
    ax_d.axhline(y=target_cm, color='black', linestyle='--', linewidth=1)
    
    # RED FILL (Below Target)
    ax_d.fill_between(df_day['raw_time'], df_day['Level_cm'], target_cm, 
                    where=(df_day['Level_cm'] <= target_cm), 
                    color='red', alpha=0.3, interpolate=True, label='Below Target')

    # MARK DOTS (Intersection Points)
    if crossings:
        crossing_times = [c['time'] for c in crossings]
        crossing_levels = [c['level'] for c in crossings]
        ax_d.scatter(crossing_times, crossing_levels, color='red', zorder=5, s=80, marker='o', label='Time Point')
        
        # Add labels on graph
        for c in crossings:
            ax_d.text(c['time'], c['level'] + 5, c['time'].strftime('%H:%M'), 
                     color='red', fontsize=9, ha='center', fontweight='bold')

    # Layout
    ax_d.set_title(f"{target_date.strftime('%Y-%m-%d')}")
    ax_d.set_ylabel("cm")
    ax_d.grid(True, alpha=0.3)
    ax_d.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax_d.xaxis.set_major_locator(mdates.HourLocator(interval=3))
    
    st.pyplot(fig_d)
    
    # Table
    with st.expander("Detailed Data"):
        st.dataframe(df_day)
