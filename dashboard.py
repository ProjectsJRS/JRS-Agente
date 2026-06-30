# dashboard.py
# Dashboard ejecutivo de JRS Retail Services (Streamlit).
# v0.1 — solo Status del agente (heartbeat). Las demas secciones se
# van conectando una por una en pasos siguientes.

import streamlit as st
from datetime import datetime

from dashboard_data import get_agent_status

st.set_page_config(
    page_title="JRS Operations Dashboard",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Auto-refresh cada 60 segundos (recarga la pagina completa).
st.markdown(
    '<meta http-equiv="refresh" content="60">',
    unsafe_allow_html=True,
)

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

# ----- Secciones pendientes (placeholders visibles) -----
st.subheader("📋 Active Projects")
st.info("Próximamente — se conecta a la memoria histórica (collection_jrs_history).")

st.subheader("⚠️ Active Alerts (Last 24h)")
st.info("Próximamente — se conecta al parseo de logs.")

st.subheader("📊 Operational Metrics")
st.info("Próximamente — agregaciones de los últimos 7 días.")

st.divider()
st.caption(
    "JRS Central Operations Intelligence System │ Internal use only │ "
    "Updated every 60 seconds"
)
