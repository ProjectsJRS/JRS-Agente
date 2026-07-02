# dashboard.py
# Dashboard ejecutivo de JRS Retail Services (Streamlit).
# v0.3 — con autenticacion (Streamlit-Authenticator 0.4.2).
# Secciones reales: status del agente, active projects, active alerts.

import os

import pandas as pd
import streamlit as st
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from datetime import datetime

from dashboard_data import get_agent_status, get_active_projects, get_recent_alerts

st.set_page_config(
    page_title="JRS Operations Dashboard",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =====================================================
# AUTENTICACION (obligatoria antes de mostrar nada)
# config.yaml vive en el mismo volumen que el resto (/data en Railway,
# ./ en local). Fuera del repo: el repo es publico.
# =====================================================
_VOLUME_DIR = os.path.dirname(os.getenv("CHROMA_DB_PATH", "./chroma_data")) or "."
CONFIG_PATH = os.path.join(_VOLUME_DIR, "config.yaml")

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
        _config = yaml.load(_f, Loader=SafeLoader)
except FileNotFoundError:
    st.error(
        "Falta config.yaml — la autenticacion no esta configurada. "
        "Genera el archivo con generar_config.py."
    )
    st.stop()

authenticator = stauth.Authenticate(
    _config["credentials"],
    _config["cookie"]["name"],
    _config["cookie"]["key"],
    _config["cookie"]["expiry_days"],
    auto_hash=False,   # las contrasenas ya vienen hasheadas (bcrypt) en config.yaml
)

authenticator.login(location="main")

_auth = st.session_state.get("authentication_status")
if _auth is False:
    st.error("Usuario o contraseña incorrectos.")
    st.stop()
elif _auth is None:
    st.warning("Ingresa tus credenciales para ver el dashboard.")
    st.stop()

# ===== A partir de aqui, el usuario esta autenticado =====

# Auto-refresh cada 60 segundos SOLO en la vista autenticada (para no recargar
# la pantalla de login mientras alguien escribe su contrasena).
st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

with st.sidebar:
    st.caption(f"Sesión: {st.session_state.get('name', '')}")
    authenticator.logout("Cerrar sesión", "sidebar")

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
    st.dataframe(df, hide_index=True, width='stretch')
else:
    st.info("No hay proyectos activos en los últimos 7 días.")

st.divider()

# ----- Secciones pendientes (placeholders visibles) -----
# ----- ACTIVE ALERTS (datos reales) -----
st.subheader("⚠️ Active Alerts (Last 24h)")

alerts = get_recent_alerts(hours=24)
if alerts:
    _sev_dot = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}
    df_alerts = pd.DataFrame(
        [
            {
                "Severity": f'{_sev_dot.get(a["severity"], "⚪")} {a["severity"]}',
                "Time": a["timestamp"],
                "Project": a["project"],
                "Summary": a["summary"],
            }
            for a in alerts
        ]
    )
    st.dataframe(df_alerts, hide_index=True, width='stretch')
else:
    st.success("No critical alerts in the last 24 hours.")

st.subheader("📊 Operational Metrics")
st.info("Próximamente — agregaciones de los últimos 7 días.")

st.divider()
st.caption(
    "JRS Central Operations Intelligence System │ Internal use only │ "
    "Updated every 60 seconds"
)
