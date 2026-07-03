# dashboard.py
# Dashboard ejecutivo de JRS Retail Services (Streamlit).
# v0.3 — con autenticacion (Streamlit-Authenticator 0.4.2).
# Secciones reales: status del agente, active projects, active alerts.

import os

import pandas as pd
import plotly.express as px
import streamlit as st
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from datetime import datetime

from dashboard_data import (
    get_agent_status,
    get_active_projects,
    get_recent_alerts,
    get_project_details,
    get_crew_map_data,
    get_archivados,
    archivar_proyecto,
    reactivar_proyecto,
)

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

# ----- PANEL DE GESTION DE PROYECTOS (solo Richard y Emmanuel) -----
# Archivar/reactivar escribe en archivados.json en el volumen: instantaneo,
# sin commit ni deploy. Un proyecto archivado desaparece de todas las secciones.
_ADMIN_USERS = {"richard", "emmanuel"}
if st.session_state.get("username") in _ADMIN_USERS:
    with st.sidebar:
        st.divider()
        st.markdown("### 🗂️ Gestionar proyectos")

        _activos = [p["project"] for p in get_active_projects()]
        if _activos:
            _sel = st.selectbox(
                "Archivar (marcar completado)",
                ["—"] + _activos,
                key="archivar_sel",
            )
            if st.button("Archivar", key="btn_archivar", disabled=(_sel == "—")):
                if archivar_proyecto(_sel):
                    st.success(f"Archivado: {_sel}")
                    st.rerun()
                else:
                    st.error("No se pudo archivar.")
        else:
            st.caption("No hay proyectos activos.")

        _arch = get_archivados()
        if _arch:
            st.caption("Archivados (clic ↩ para reactivar):")
            for _p in _arch:
                _ca, _cb = st.columns([3, 1])
                _ca.write(_p)
                if _cb.button("↩", key=f"react_{_p}", help=f"Reactivar {_p}"):
                    reactivar_proyecto(_p)
                    st.rerun()
        else:
            st.caption("Sin proyectos archivados.")

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

# ----- PROJECT DETAIL (expandible por proyecto, desde crews_json) -----
st.subheader("🔎 Project Detail")
st.caption("Detalle por crew · despliega cada proyecto para ver más")

_detalles = get_project_details()
if _detalles:
    _dot_status = {"DELAYED": "🔴", "ATTENTION": "🟡", "ON TRACK": "🟢"}
    for _d in _detalles:
        _icono = _dot_status.get(_d.get("status", ""), "⚪")
        _titulo = f'{_icono} {_d.get("project", "")} — {_d.get("location", "")}'
        with st.expander(_titulo):
            st.markdown(f"**Crew / Leader:** {_d.get('crew', '') or '—'}")
            st.markdown(f"**Members:** {_d.get('members', '') or '—'}")
            _dias = _d.get("days_on_site", "") or "—"
            st.markdown(
                f"**Status:** {_d.get('status', '') or '—'}  ·  "
                f"**Days on site:** {_dias}"
            )
            st.markdown(f"**Progress:** {_d.get('progress', '') or '—'}")
            st.markdown(f"**Incidents:** {_d.get('incidents', '') or 'none'}")
            st.caption(f"Last update: {_d.get('last_update', '')}")
else:
    st.info("Sin detalle por crew todavía. Llega con los próximos crew updates.")

st.divider()

# ----- CREW MAP BY STATE (por riesgo) -----
st.subheader("🗺️ Crew Map by State")
st.caption("Color por riesgo: peor estado de cada estado (rojo/amarillo/verde)")

_map = get_crew_map_data()
if _map:
    _df_map = pd.DataFrame(_map)
    _fig_risk = px.choropleth(
        _df_map,
        locations="state",
        locationmode="USA-states",
        scope="usa",
        color="worst_status",
        category_orders={"worst_status": ["DELAYED", "ATTENTION", "ON TRACK", "—"]},
        color_discrete_map={
            "DELAYED": "#E24B4A",
            "ATTENTION": "#BA7517",
            "ON TRACK": "#1D9E75",
            "—": "#cccccc",
        },
        labels={"worst_status": "Status"},
        hover_data=["count", "projects"],
    )
    _fig_risk.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=420)
    st.plotly_chart(_fig_risk, width='stretch')
else:
    st.info("Sin datos de ubicación todavía. Llegan con los próximos crew updates.")

st.divider()

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
