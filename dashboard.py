# dashboard.py
# Dashboard ejecutivo de JRS Retail Services (Streamlit).
# v0.2 — Status del agente (heartbeat) + Active Projects (historia real).
# Las demas secciones se conectan una por una en pasos siguientes.

import pandas as pd
import streamlit as st
from datetime import datetime

from dashboard_data import get_agent_status, get_active_projects

st.set_page_config(
    page_title="JRS Operations Dashboard",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Auto-refresh cada 60 segundos (recarga la pagina completa).
st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

# ----- HEADER -----
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    st.title("🏗️ JRS Operations Dashboard")
    st.caption(f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

status = get_agent_status()

with col2:
    if status["is_alive"]:
        st.success("🟢 Agent: OPERATIONAL")
        st.caption(f"Last heartbeat: {status['last_seen_minutes']} min ago")
    else:
        st.error("🔴 Agent: DOWN")
        st.caption(f"Last heartbeat: {status['last_seen_minutes']} min ago")

with col3:
    st.metric("Last daily report", status["last_report_date"])

st.divider()

# ----- ACTIVE PROJECTS (datos reales) -----
st.subheader("📋 Active Projects")
st.caption("Últimos 7 días · estado por nivel de riesgo del reporte más reciente")

projects = get_active_projects()
if projects:
    df = pd.DataFrame(
        [
            {
                "Project": p["project"],
                "Last update": p["last_update"],
                "Risk": f'{p["status_dot"]} {p["risk_level"]}',
            }
            for p in projects
        ]
    )
    st.dataframe(df, hide_index=True, use_container_width=True)
else:
    st.info("No hay proyectos activos en los últimos 7 días.")

st.divider()

# ----- Secciones pendientes (placeholders visibles) -----
st.subheader("⚠️ Active Alerts (Last 24h)")
st.info("Próximamente — se conecta al parseo de logs.")

st.subheader("📊 Operational Metrics")
st.info("Próximamente — agregaciones de los últimos 7 días.")

st.divider()
st.caption(
    "JRS Central Operations Intelligence System │ Internal use only │ "
    "Updated every 60 seconds"
)
