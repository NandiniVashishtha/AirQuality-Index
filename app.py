import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from scipy.interpolate import griddata
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import time

# ─────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────
st.set_page_config(
    page_title="AQI Monitor – Greater Noida",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────
# GLOBAL CUSTOM CSS  (dark industrial theme)
# ─────────────────────────────────────────
st.markdown("""
<style>
  /* ── Google Font ── */
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;700&display=swap');

  /* ── Root palette ── */
  :root {
    --bg:        #0d1117;
    --surface:   #161b22;
    --border:    #30363d;
    --accent:    #00e5ff;
    --accent2:   #ff6b6b;
    --accent3:   #ffd166;
    --good:      #2ea44f;
    --moderate:  #f0883e;
    --unhealthy: #f85149;
    --text:      #e6edf3;
    --muted:     #8b949e;
  }

  /* ── App shell ── */
  .stApp { background: var(--bg); color: var(--text);
           font-family: 'DM Sans', sans-serif; }

  /* ── Sidebar ── */
  section[data-testid="stSidebar"] {
    background: var(--surface);
    border-right: 1px solid var(--border);
  }
  section[data-testid="stSidebar"] * { color: var(--text) !important; }
  section[data-testid="stSidebar"] .stRadio label {
    padding: 6px 10px; border-radius: 6px; cursor: pointer;
    transition: background .2s;
  }
  section[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(0,229,255,.08);
  }

  /* ── KPI card ── */
  .kpi-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 22px;
    text-align: center;
    transition: transform .2s, box-shadow .2s;
  }
  .kpi-card:hover { transform: translateY(-3px);
    box-shadow: 0 8px 24px rgba(0,0,0,.45); }
  .kpi-label { font-size: .75rem; letter-spacing: .12em; text-transform: uppercase;
               color: var(--muted); font-family: 'Space Mono', monospace; margin-bottom: 6px; }
  .kpi-value { font-size: 2.4rem; font-weight: 700; line-height: 1;
               font-family: 'Space Mono', monospace; }
  .kpi-unit  { font-size: .8rem; color: var(--muted); margin-top: 3px; }
  .kpi-limit { font-size: .72rem; color: var(--muted); margin-top: 8px; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 20px;
           font-size: .7rem; font-weight: 700; letter-spacing: .08em;
           text-transform: uppercase; font-family: 'Space Mono', monospace; margin-top: 6px; }
  .badge-good      { background: rgba(46,164,79,.2);  color: #2ea44f; }
  .badge-moderate  { background: rgba(240,136,62,.2); color: #f0883e; }
  .badge-unhealthy { background: rgba(248,81,73,.2);  color: #f85149; }

  /* ── Section header ── */
  .section-title {
    font-family: 'Space Mono', monospace;
    font-size: 1rem; letter-spacing: .1em; text-transform: uppercase;
    color: var(--accent); border-left: 3px solid var(--accent);
    padding-left: 10px; margin: 28px 0 14px;
  }

  /* ── Divider ── */
  hr { border-color: var(--border) !important; margin: 24px 0; }

  /* ── Streamlit metric overrides ── */
  [data-testid="metric-container"] {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 18px;
  }
  [data-testid="stMetricLabel"] { color: var(--muted) !important; font-size: .8rem; }
  [data-testid="stMetricValue"] { color: var(--text) !important; font-family: 'Space Mono',monospace; }

  /* ── Dataframe ── */
  .stDataFrame { border: 1px solid var(--border); border-radius: 8px; }

  /* ── Selectbox / radio ── */
  .stSelectbox select, .stSelectbox div[data-baseweb] {
    background: var(--surface) !important; color: var(--text) !important;
    border: 1px solid var(--border) !important;
  }
  .stSelectbox label, .stRadio label { color: var(--muted) !important; }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────
PM25_LIMIT  = 60    # µg/m³  (CPCB 24-hr standard)
PM10_LIMIT  = 100   # µg/m³
TEMP_WARN   = 40    # °C
HUM_WARN    = 80    # %

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(22,27,34,1)",
    font=dict(family="DM Sans", color="#e6edf3", size=12),
    xaxis=dict(gridcolor="#30363d", linecolor="#30363d", showgrid=True),
    yaxis=dict(gridcolor="#30363d", linecolor="#30363d", showgrid=True),
    legend=dict(bgcolor="rgba(22,27,34,.8)", bordercolor="#30363d",
                borderwidth=1, font=dict(size=11)),
    margin=dict(l=50, r=30, t=40, b=50),
    hovermode="x unified",
)

# ─────────────────────────────────────────
# DATA LOADING & CACHING
# ─────────────────────────────────────────
@st.cache_data(ttl=30)
def load_data(path="data.xlsx"):
    df = pd.read_excel(path)
    df.columns = [c.strip() for c in df.columns]

    # Build datetime from DATE + TIME columns
    if "DATE" in df.columns and "TIME" in df.columns:
        df["datetime"] = pd.to_datetime(
            df["DATE"].astype(str) + " " + df["TIME"].astype(str),
            errors="coerce"
        )
    elif "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    else:
        st.error("Excel file must have DATE+TIME or a datetime column.")
        st.stop()

    # Normalise column names to lowercase short keys
    rename = {}
    for c in df.columns:
        cl = c.strip().lower()
        if "pm2" in cl:      rename[c] = "pm25"
        elif "pm10" in cl:   rename[c] = "pm10"
        elif "aqi" in cl:    rename[c] = "aqi"
        elif "temp" in cl:   rename[c] = "temperature"
        elif "hum" in cl:    rename[c] = "humidity"
        elif "lat" in cl:    rename[c] = "latitude"
        elif "lon" in cl:    rename[c] = "longitude"
    df.rename(columns=rename, inplace=True)

    # Ensure numeric
    for col in ["pm25","pm10","aqi","temperature","humidity","latitude","longitude"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df.dropna(subset=["datetime"], inplace=True)
    df.sort_values("datetime", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df

# ─────────────────────────────────────────
# STATUS HELPERS
# ─────────────────────────────────────────
def get_status(value, limit):
    if value <= limit * 0.5:  return "Good"
    elif value <= limit:       return "Moderate"
    else:                      return "Unhealthy"

def status_badge(label):
    cls = f"badge-{label.lower()}"
    return f'<span class="badge {cls}">{label}</span>'

def status_color(label):
    return {"Good": "#2ea44f", "Moderate": "#f0883e", "Unhealthy": "#f85149"}.get(label, "#8b949e")

def kpi_card(label, value, unit, limit_text, status):
    color = status_color(status)
    badge_html = status_badge(status)
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value" style="color:{color}">{value}</div>
        <div class="kpi-unit">{unit}</div>
        <div class="kpi-limit">{limit_text}</div>
        {badge_html}
    </div>"""

# ─────────────────────────────────────────
# TIME FILTER HELPER
# ─────────────────────────────────────────
def filter_by_time(df, window):
    if window == "All Data":
        return df
    latest = df["datetime"].max()
    delta = {"Last 1 Hour": timedelta(hours=1),
             "Last 24 Hours": timedelta(hours=24),
             "Last 7 Days": timedelta(days=7)}.get(window, None)
    if delta:
        return df[df["datetime"] >= latest - delta]
    return df

# ─────────────────────────────────────────
# PLOTLY TREND HELPER
# ─────────────────────────────────────────
def trend_fig(df, col, name, color, limit=None, limit_name=None, y_title=""):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["datetime"], y=df[col],
        mode="lines+markers",
        name=name,
        line=dict(color=color, width=2.5, shape="spline", smoothing=1.2),
        marker=dict(size=5),
        fill="tozeroy",
        fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.08)",
        hovertemplate=f"<b>{name}</b>: %{{y:.1f}}<br>%{{x|%b %d %H:%M}}<extra></extra>"
    ))
    if limit is not None:
        fig.add_hline(y=limit, line_dash="dot", line_color="#f85149", line_width=1.5,
                      annotation_text=f" {limit_name}: {limit}", annotation_position="top right",
                      annotation_font_color="#f85149")
    layout = dict(**PLOTLY_LAYOUT)
    layout["yaxis"]["title"] = y_title
    fig.update_layout(**layout, height=280)
    return fig

# ─────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────
data = load_data("GRETAER_NOIDA_original.xlsx")
# ─────────────────────────────────────────
# AUTO-REFRESH
# ─────────────────────────────────────────
# (handled via st.rerun below if enabled)

# ─────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="font-family:'Space Mono',monospace;font-size:1.25rem;
                color:#00e5ff;font-weight:700;letter-spacing:.05em;padding:8px 0 4px;">
      🌿 AQI SYSTEM
    </div>
    <div style="color:#8b949e;font-size:.75rem;margin-bottom:18px;">
      Greater Noida · Real-Time IoT
    </div>
    """, unsafe_allow_html=True)

    st.markdown("**Devices**")
    selected_device = st.radio(
        "Select Sensor",
        ["🔬 SDS011", "🌡️ DHT11"],
        label_visibility="collapsed"
    )

    st.markdown("---")

    st.markdown("**⏱ Time Range**")
    time_window = st.selectbox(
        "Filter",
        ["All Data", "Last 7 Days", "Last 24 Hours", "Last 1 Hour"],
        label_visibility="collapsed"
    )

    st.markdown("---")

    # Live status in sidebar
    latest = data.iloc[-1]
    pm25_now = latest["pm25"]
    pm10_now = latest["pm10"]
    s25 = get_status(pm25_now, PM25_LIMIT)

    st.markdown(f"""
    <div style="font-size:.75rem;color:#8b949e;margin-bottom:6px;">LATEST READING</div>
    <div style="font-family:'Space Mono',monospace;font-size:1.5rem;
                color:{status_color(s25)};font-weight:700;">{pm25_now} µg/m³</div>
    <div style="font-size:.75rem;color:#8b949e;">PM2.5 · {status_badge(s25)}</div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    auto_refresh = st.toggle("🔄 Auto Refresh (10s)", value=False)

    st.markdown("---")
    ts = latest["datetime"]
    st.markdown(f"""
    <div style="font-size:.7rem;color:#8b949e;">
      Last update<br>
      <span style="color:#e6edf3;font-family:'Space Mono',monospace;">
        {ts.strftime('%Y-%m-%d %H:%M:%S')}
      </span>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────
# FILTERED DATA
# ─────────────────────────────────────────
filtered = filter_by_time(data, time_window)

if len(filtered) == 0:
    st.warning("No data in selected time range. Showing all data.")
    filtered = data

latest = filtered.iloc[-1]
pm25_now   = latest["pm25"]
pm10_now   = latest["pm10"]
temp_now   = latest.get("temperature", None)
hum_now    = latest.get("humidity", None)
aqi_now    = latest.get("aqi", None)

has_temp   = "temperature" in filtered.columns and filtered["temperature"].notna().any()
has_hum    = "humidity"    in filtered.columns and filtered["humidity"].notna().any()
has_loc    = "latitude"    in filtered.columns and filtered["latitude"].notna().any()

# ─────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────
st.markdown("""
<div style="margin-bottom:6px;">
  <span style="font-family:'Space Mono',monospace;font-size:1.65rem;
               font-weight:700;color:#e6edf3;letter-spacing:.02em;">
    Air Quality Monitoring Dashboard
  </span>
</div>
<div style="color:#8b949e;font-size:.85rem;margin-bottom:4px;">
  📍 Greater Noida, Uttar Pradesh · IoT-Based Real-Time Environmental Intelligence
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ─────────────────────────────────────────
# SECTION 1: KPI CARDS
# ─────────────────────────────────────────
st.markdown('<div class="section-title">📊 Sensor Overview</div>', unsafe_allow_html=True)

cols = st.columns(4)

s25  = get_status(pm25_now, PM25_LIMIT)
s10  = get_status(pm10_now, PM10_LIMIT)
s_t  = "Good" if (temp_now or 0) < TEMP_WARN else "Moderate"
s_h  = "Good" if (hum_now or 0) < HUM_WARN else "Moderate"

with cols[0]:
    st.markdown(kpi_card(
        "PM2.5", f"{pm25_now:.1f}", "µg/m³",
        f"Limit: {PM25_LIMIT} µg/m³", s25
    ), unsafe_allow_html=True)

with cols[1]:
    st.markdown(kpi_card(
        "PM10", f"{pm10_now:.1f}", "µg/m³",
        f"Limit: {PM10_LIMIT} µg/m³", s10
    ), unsafe_allow_html=True)

with cols[2]:
    t_val = f"{temp_now:.1f}" if temp_now is not None else "N/A"
    st.markdown(kpi_card(
        "Temperature", t_val, "°C",
        f"Warning above {TEMP_WARN}°C", s_t
    ), unsafe_allow_html=True)

with cols[3]:
    h_val = f"{hum_now:.1f}" if hum_now is not None else "N/A"
    st.markdown(kpi_card(
        "Humidity", h_val, "%",
        f"Warning above {HUM_WARN}%", s_h
    ), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# AQI badge row
if aqi_now is not None:
    aqi_s = get_status(aqi_now, 150)
    aqi_color = status_color(aqi_s)
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:16px;padding:14px 20px;
                background:#161b22;border:1px solid #30363d;border-radius:10px;">
      <div style="font-family:'Space Mono',monospace;font-size:.75rem;
                  color:#8b949e;text-transform:uppercase;letter-spacing:.1em;">AQI Index</div>
      <div style="font-family:'Space Mono',monospace;font-size:2rem;
                  font-weight:700;color:{aqi_color};">{int(aqi_now)}</div>
      {status_badge(aqi_s)}
      <div style="color:#8b949e;font-size:.8rem;margin-left:auto;">
        Based on latest sensor reading · {latest['datetime'].strftime('%d %b %Y, %H:%M')}
      </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# ─────────────────────────────────────────
# SECTION 2: POLLUTANT TRENDS (SDS011)
# ─────────────────────────────────────────
if "SDS011" in selected_device:
    st.markdown('<div class="section-title">💨 Pollutant Levels — SDS011</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**PM2.5 Trend**")
        fig_pm25 = trend_fig(
            filtered, "pm25", "PM2.5", "#00e5ff",
            limit=PM25_LIMIT, limit_name="PM2.5 Std",
            y_title="µg/m³"
        )
        st.plotly_chart(fig_pm25, width='stretch')

    with c2:
        st.markdown("**PM10 Trend**")
        fig_pm10 = trend_fig(
            filtered, "pm10", "PM10", "#ffd166",
            limit=PM10_LIMIT, limit_name="PM10 Std",
            y_title="µg/m³"
        )
        st.plotly_chart(fig_pm10, width='stretch')

    # Combined chart
    st.markdown("**Combined PM2.5 & PM10 Time-Series**")
    fig_combined = go.Figure()
    fig_combined.add_trace(go.Scatter(
        x=filtered["datetime"], y=filtered["pm25"],
        name="PM2.5", mode="lines",
        line=dict(color="#00e5ff", width=2.5, shape="spline", smoothing=1.2),
        hovertemplate="<b>PM2.5</b>: %{y:.1f} µg/m³<br>%{x|%b %d %H:%M}<extra></extra>"
    ))
    fig_combined.add_trace(go.Scatter(
        x=filtered["datetime"], y=filtered["pm10"],
        name="PM10", mode="lines",
        line=dict(color="#ffd166", width=2.5, shape="spline", smoothing=1.2),
        hovertemplate="<b>PM10</b>: %{y:.1f} µg/m³<br>%{x|%b %d %H:%M}<extra></extra>"
    ))
    fig_combined.add_hline(y=PM25_LIMIT, line_dash="dot", line_color="#00e5ff",
                           line_width=1, annotation_text=" PM2.5 Std (60)",
                           annotation_font_color="#00e5ff")
    fig_combined.add_hline(y=PM10_LIMIT, line_dash="dot", line_color="#ffd166",
                           line_width=1, annotation_text=" PM10 Std (100)",
                           annotation_font_color="#ffd166")
    fig_combined.update_layout(**PLOTLY_LAYOUT, height=380,
                                yaxis_title="Concentration (µg/m³)")
    st.plotly_chart(fig_combined, width='stretch')

    st.markdown("---")

# ─────────────────────────────────────────
# SECTION 3: TEMP & HUMIDITY (DHT11)
# ─────────────────────────────────────────
if "DHT11" in selected_device:
    st.markdown('<div class="section-title">🌡️ Environmental Conditions — DHT11</div>', unsafe_allow_html=True)

    if has_temp and has_hum:
        c3, c4 = st.columns(2)

        with c3:
            st.markdown("**Temperature Trend**")
            fig_temp = trend_fig(
                filtered, "temperature", "Temperature", "#ff6b6b",
                limit=TEMP_WARN, limit_name="Warn Threshold",
                y_title="°C"
            )
            st.plotly_chart(fig_temp, width='stretch')

        with c4:
            st.markdown("**Humidity Trend**")
            fig_hum = trend_fig(
                filtered, "humidity", "Humidity", "#c084fc",
                limit=HUM_WARN, limit_name="Warn Threshold",
                y_title="%RH"
            )
            st.plotly_chart(fig_hum, width='stretch')

        # Dual-axis chart
        st.markdown("**Temperature & Humidity — Dual Axis**")
        fig_dh = make_subplots(specs=[[{"secondary_y": True}]])
        fig_dh.add_trace(go.Scatter(
            x=filtered["datetime"], y=filtered["temperature"],
            name="Temp (°C)", mode="lines",
            line=dict(color="#ff6b6b", width=2.5, shape="spline", smoothing=1.2),
            hovertemplate="<b>Temp</b>: %{y:.1f}°C<br>%{x|%H:%M}<extra></extra>"
        ), secondary_y=False)
        fig_dh.add_trace(go.Scatter(
            x=filtered["datetime"], y=filtered["humidity"],
            name="Humidity (%)", mode="lines",
            line=dict(color="#c084fc", width=2.5, shape="spline", smoothing=1.2),
            hovertemplate="<b>Humidity</b>: %{y:.1f}%<br>%{x|%H:%M}<extra></extra>"
        ), secondary_y=True)
        layout_dh = dict(**PLOTLY_LAYOUT)
        layout_dh["legend"] = dict(orientation="h", yanchor="bottom", y=1.02)
        fig_dh.update_layout(**layout_dh, height=320)
        fig_dh.update_yaxes(title_text="Temperature (°C)",  secondary_y=False,
                             gridcolor="#30363d", color="#e6edf3")
        fig_dh.update_yaxes(title_text="Humidity (%RH)", secondary_y=True,
                             gridcolor="#30363d", color="#e6edf3")
        fig_dh.update_xaxes(gridcolor="#30363d", color="#e6edf3")
        st.plotly_chart(fig_dh, width='stretch')

    else:
        st.info("Temperature and Humidity columns not found in the dataset.")

    st.markdown("---")

# If neither selected, show both by default
if "SDS011" not in selected_device and "DHT11" not in selected_device:
    st.info("Select a sensor from the sidebar to view its data.")

# ─────────────────────────────────────────
# SECTION 4: SENSOR LOCATION MAP
# ─────────────────────────────────────────
if has_loc:
    st.markdown('<div class="section-title">📍 Sensor Location Map</div>', unsafe_allow_html=True)

    lat_center = filtered["latitude"].mean()
    lon_center = filtered["longitude"].mean()

    m = folium.Map(
        location=[lat_center, lon_center],
        zoom_start=14,
        tiles="CartoDB dark_matter"
    )

    # Plot all points as small dots
    for _, row in filtered.iterrows():
        if pd.notna(row["latitude"]) and pd.notna(row["longitude"]):
            aq_label = get_status(row["pm25"], PM25_LIMIT)
            dot_color = {"Good":"#2ea44f","Moderate":"#f0883e","Unhealthy":"#f85149"}.get(aq_label, "#8b949e")
            folium.CircleMarker(
                location=[row["latitude"], row["longitude"]],
                radius=4,
                color=dot_color,
                fill=True,
                fill_color=dot_color,
                fill_opacity=0.55,
                weight=0,
            ).add_to(m)

    # Latest reading marker with popup
    lrow = filtered.iloc[-1]
    popup_html = f"""
    <div style="font-family:sans-serif;min-width:180px;">
      <b>📍 Latest Reading</b><hr style="margin:4px 0">
      <b>PM2.5:</b> {lrow['pm25']} µg/m³<br>
      <b>PM10:</b>  {lrow['pm10']} µg/m³<br>
      {'<b>Temp:</b>  ' + str(lrow.get('temperature','')) + ' °C<br>' if has_temp else ''}
      {'<b>Hum:</b>   ' + str(lrow.get('humidity','')) + ' %<br>' if has_hum else ''}
      <b>Time:</b>  {lrow['datetime'].strftime('%Y-%m-%d %H:%M')}
    </div>"""
    folium.Marker(
        location=[lrow["latitude"], lrow["longitude"]],
        popup=folium.Popup(popup_html, max_width=220),
        icon=folium.Icon(color="red", icon="info-sign")
    ).add_to(m)

    st_folium(m, height=420, width='stretch')

    st.markdown("---")

# ─────────────────────────────────────────
# SECTION 5: SPATIAL HEATMAP
# ─────────────────────────────────────────
if has_loc and len(filtered) >= 4:
    st.markdown('<div class="section-title">🗺️ Spatial Pollution Heatmap</div>', unsafe_allow_html=True)

    lat_vals = filtered["latitude"].dropna()
    lon_vals = filtered["longitude"].dropna()
    pm_vals  = filtered.loc[lat_vals.index, "pm25"].dropna()

    # Only interpolate if we have variance in coordinates
    if lat_vals.std() > 0 and lon_vals.std() > 0:
        try:
            grid_x, grid_y = np.mgrid[
                lon_vals.min():lon_vals.max():30j,
                lat_vals.min():lat_vals.max():30j
            ]
            grid_z = griddata(
                (lon_vals.values, lat_vals.values),
                pm_vals.values,
                (grid_x, grid_y),
                method="linear"
            )
            heat_data = [
                [grid_y[i][j], grid_x[i][j], float(grid_z[i][j])]
                for i in range(grid_x.shape[0])
                for j in range(grid_x.shape[1])
                if not np.isnan(grid_z[i][j])
            ]
        except Exception:
            heat_data = [[row["latitude"], row["longitude"], row["pm25"]]
                         for _, row in filtered.iterrows()
                         if pd.notna(row["latitude"])]
    else:
        # fallback: use raw points
        heat_data = [[row["latitude"], row["longitude"], row["pm25"]]
                     for _, row in filtered.iterrows()
                     if pd.notna(row["latitude"])]

    m2 = folium.Map(
        location=[lat_vals.mean(), lon_vals.mean()],
        zoom_start=14,
        tiles="CartoDB dark_matter"
    )

    if heat_data:
        HeatMap(
            heat_data,
            radius=25,
            blur=20,
            max_zoom=16,
            gradient={"0.2":"#2ea44f","0.5":"#ffd166","0.8":"#f0883e","1.0":"#f85149"}
        ).add_to(m2)

    st_folium(m2, height=460, width='stretch')

    st.markdown("---")

# ─────────────────────────────────────────
# SECTION 6: RAW DATA TABLE
# ─────────────────────────────────────────
with st.expander("📋 Raw Sensor Data (last 100 readings)"):
    display_cols = [c for c in ["datetime","pm25","pm10","temperature","humidity","aqi","latitude","longitude"]
                    if c in filtered.columns]
    st.dataframe(
        filtered[display_cols].tail(100).sort_values("datetime", ascending=False),
        width='stretch',
        hide_index=True,
    )

# ─────────────────────────────────────────
# AUTO-REFRESH
# ─────────────────────────────────────────
if auto_refresh:
    st.markdown("""
    <div style="font-size:.72rem;color:#8b949e;text-align:center;padding:8px;">
      🔄 Auto-refresh enabled · refreshing every 10 seconds
    </div>
    """, unsafe_allow_html=True)
    time.sleep(10)
    st.rerun()
