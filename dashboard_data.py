# dashboard_data.py
# Capa de datos del dashboard ejecutivo de JRS.
# Separa la logica de datos de la presentacion: lee de ChromaDB, logs,
# heartbeat y reportes, y devuelve datos estructurados al dashboard.
#
# ESTADO INCREMENTAL (segun Documento 07):
#   - get_agent_status      -> DATOS REALES (heartbeat) [LISTO]
#   - get_active_projects   -> DATOS REALES (collection_jrs_history) [LISTO]
#   - get_recent_alerts     -> stub (parse de logs) [PENDIENTE]
#   - get_operational_metrics -> stub (agregaciones) [PENDIENTE]
#   - get_crews_status      -> stub (analisis predictivo, Paso 7.4) [FUTURO]
#   - get_clients_at_risk   -> stub (analisis predictivo, Paso 7.4) [FUTURO]

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

from chromadb import PersistentClient

# Mismas rutas/variables que usa el agente, para leer del mismo volumen.
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_data")
_VOLUME_DIR = os.path.dirname(CHROMA_DB_PATH) or "."
HEARTBEAT_FILE = os.path.join(_VOLUME_DIR, "heartbeat.txt")
REPORTES_DIR = os.path.join(_VOLUME_DIR, "reportes_diarios")

# Umbral: mas de este tiempo sin latido => agente considerado caido.
HEARTBEAT_UMBRAL_MIN = 10

# Ventana para considerar un proyecto "activo".
ACTIVE_WINDOW_DAYS = 7

COLECCION_HISTORIA = "collection_jrs_history"


def get_agent_status() -> Dict:
    """
    Lee el heartbeat para saber si el agente esta vivo.

    Returns dict con:
      - is_alive: bool
      - last_seen_minutes: int (minutos desde el ultimo latido)
      - last_report_date: str (fecha del ultimo reporte diario, o 'never')
    """
    try:
        with open(HEARTBEAT_FILE, "r", encoding="utf-8") as f:
            contenido = f.read().strip()
        # El heartbeat puede traer un sufijo de version: "<iso> | BUILD xyz".
        # Nos quedamos solo con la parte de la fecha ISO antes del " | ".
        parte_fecha = contenido.split(" | ")[0].strip()
        last_beat = datetime.fromisoformat(parte_fecha)
        delta_minutes = (datetime.now() - last_beat).total_seconds() / 60
        is_alive = delta_minutes < HEARTBEAT_UMBRAL_MIN
    except Exception:
        is_alive = False
        delta_minutes = 999

    try:
        reportes = sorted(Path(REPORTES_DIR).glob("reporte_*.txt"))
        last_report_date = (
            reportes[-1].stem.replace("reporte_", "") if reportes else "never"
        )
    except Exception:
        last_report_date = "never"

    return {
        "is_alive": is_alive,
        "last_seen_minutes": int(delta_minutes),
        "last_report_date": last_report_date,
    }


# =====================================================
# ACTIVE PROJECTS — datos reales desde collection_jrs_history
# Opcion A: el estado de cada proyecto se deriva del risk_level del
# reporte mas reciente (ultimos 7 dias) que lo menciona.
# =====================================================
def _risk_a_estado(risk_level: str) -> Dict:
    r = (risk_level or "").upper()
    if r in ("CRITICAL", "HIGH"):
        return {"label": r.title(), "dot": "🔴"}
    if r == "MEDIUM":
        return {"label": "Medium", "dot": "🟡"}
    if r == "LOW":
        return {"label": "Low", "dot": "🟢"}
    return {"label": "—", "dot": "⚪"}


def get_active_projects() -> List[Dict]:
    """
    Proyectos activos (ultimos 7 dias) leidos de collection_jrs_history.

    Cada item: {project, last_update, status_dot, risk_level}.
    Robusto ante documentos historicos con otro esquema: solo considera
    los que tienen 'projects' y 'date' validos.
    """
    try:
        client = PersistentClient(path=CHROMA_DB_PATH)
        col = client.get_or_create_collection(name=COLECCION_HISTORIA)
        data = col.get(include=["metadatas"])
    except Exception:
        return []

    metadatas = data.get("metadatas") or []
    cutoff = (datetime.now() - timedelta(days=ACTIVE_WINDOW_DAYS)).date()

    # project_name -> {fecha (date), fecha_str, risk}; nos quedamos con el mas reciente.
    por_proyecto: Dict[str, Dict] = {}
    for meta in metadatas:
        if not meta:
            continue
        proyectos_raw = meta.get("projects", "")
        fecha_str = meta.get("date", "")
        if not proyectos_raw or not fecha_str:
            continue
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except Exception:
            continue
        if fecha < cutoff:
            continue
        risk = meta.get("risk_level", "")
        for proyecto in [p.strip() for p in proyectos_raw.split(",") if p.strip()]:
            actual = por_proyecto.get(proyecto)
            if actual is None or fecha >= actual["fecha"]:
                por_proyecto[proyecto] = {"fecha": fecha, "fecha_str": fecha_str, "risk": risk}

    resultados = []
    for proyecto, info in por_proyecto.items():
        estado = _risk_a_estado(info["risk"])
        resultados.append({
            "project": proyecto,
            "last_update": info["fecha_str"],
            "status_dot": estado["dot"],
            "risk_level": estado["label"],
        })

    # Orden: mas reciente primero, y luego mas riesgo arriba (dos sorts estables).
    orden_riesgo = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "—": 4}
    resultados.sort(key=lambda x: x["last_update"], reverse=True)
    resultados.sort(key=lambda x: orden_riesgo.get(x["risk_level"], 5))
    return resultados


# =====================================================
# STUBS — se conectaran a datos reales en pasos siguientes.
# =====================================================
ALERTS_FILE = os.path.join(_VOLUME_DIR, "alerts.jsonl")


def get_recent_alerts(hours: int = 24) -> List[Dict]:
    """
    Lee alerts.jsonl y devuelve las alertas de las ultimas `hours` horas.

    Cada item: {timestamp, severity, project, summary}.
    Robusto: si el archivo no existe o una linea esta corrupta, la salta
    sin romper el dashboard. Devuelve las mas recientes primero.
    """
    try:
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            lineas = f.readlines()
    except Exception:
        return []

    cutoff = datetime.now() - timedelta(hours=hours)
    alertas = []
    for linea in lineas:
        linea = linea.strip()
        if not linea:
            continue
        try:
            reg = json.loads(linea)
            ts = datetime.strptime(reg["timestamp"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if ts < cutoff:
            continue
        alertas.append({
            "timestamp": reg.get("timestamp", ""),
            "severity": (reg.get("severity", "") or "").upper(),
            "project": reg.get("project", ""),
            "summary": reg.get("summary", ""),
        })

    alertas.sort(key=lambda a: a["timestamp"], reverse=True)
    return alertas


def get_operational_metrics() -> Dict:
    """Metricas operativas. PENDIENTE: agregaciones de logs.
    Nota: 'WhatsApp messages' se elimino del alcance (no aplica a JRS)."""
    return {
        "emails_processed": "—",
        "alerts_count": "—",
        "reports_generated": "—",
        "avg_processing": "—",
    }


def get_crews_status() -> List[Dict]:
    """Crews requiriendo atencion. FUTURO: analisis predictivo (Paso 7.4)."""
    return []


def get_clients_at_risk() -> List[Dict]:
    """Clientes en pre-escalacion. FUTURO: analisis predictivo (Paso 7.4).
    RECORDATORIO: esta seccion es SOLO para Richard."""
    return []


# =====================================================
# DETALLE POR CREW / MAPA — leen el crews_json guardado por el agente.
# Ambas usan la ventana de ACTIVE_WINDOW_DAYS y se quedan con el reporte
# mas reciente por proyecto. Robustas ante registros viejos sin crews_json.
# =====================================================
_STATUS_SEVERITY = {"DELAYED": 3, "ATTENTION": 2, "ON TRACK": 1, "": 0}
_SEVERITY_LABEL = {3: "DELAYED", 2: "ATTENTION", 1: "ON TRACK", 0: "—"}


def get_project_details() -> List[Dict]:
    """
    Detalle por proyecto (ultimos 7 dias) desde crews_json.
    Cada item trae los campos del crew mas reciente de ese proyecto:
    project, location, state, crew, members, status, days_on_site,
    progress, incidents, last_update.
    """
    try:
        client = PersistentClient(path=CHROMA_DB_PATH)
        col = client.get_or_create_collection(name=COLECCION_HISTORIA)
        data = col.get(include=["metadatas"])
    except Exception:
        return []

    metadatas = data.get("metadatas") or []
    cutoff = (datetime.now() - timedelta(days=ACTIVE_WINDOW_DAYS)).date()

    best: Dict[str, Dict] = {}  # project -> {fecha, crew, fecha_str}
    for meta in metadatas:
        if not meta:
            continue
        crews_raw = meta.get("crews_json", "")
        fecha_str = meta.get("date", "")
        if not crews_raw or not fecha_str:
            continue
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except Exception:
            continue
        if fecha < cutoff:
            continue
        try:
            crews = json.loads(crews_raw)
        except Exception:
            continue
        for crew in crews:
            proj = crew.get("project", "")
            if not proj:
                continue
            actual = best.get(proj)
            if actual is None or fecha >= actual["fecha"]:
                best[proj] = {"fecha": fecha, "crew": crew, "fecha_str": fecha_str}

    resultados = []
    for proj, info in best.items():
        item = dict(info["crew"])
        item["project"] = proj
        item["last_update"] = info["fecha_str"]
        resultados.append(item)

    # Orden: peor status primero, luego mas reciente.
    resultados.sort(key=lambda x: x.get("last_update", ""), reverse=True)
    resultados.sort(key=lambda x: _STATUS_SEVERITY.get(x.get("status", ""), 0), reverse=True)
    return resultados


def get_crew_map_data() -> List[Dict]:
    """
    Agrega por estado (2 letras) para el mapa. Cada item:
    state, count (proyectos activos), worst_status, projects (lista).
    """
    detalles = get_project_details()
    por_estado: Dict[str, Dict] = {}
    for d in detalles:
        est = d.get("state", "")
        if not est:
            continue
        e = por_estado.setdefault(
            est, {"state": est, "count": 0, "worst": 0, "projects": []}
        )
        e["count"] += 1
        e["projects"].append(d.get("project", ""))
        sev = _STATUS_SEVERITY.get(d.get("status", ""), 0)
        if sev > e["worst"]:
            e["worst"] = sev

    salida = []
    for e in por_estado.values():
        salida.append({
            "state": e["state"],
            "count": e["count"],
            "worst_status": _SEVERITY_LABEL.get(e["worst"], "—"),
            "projects": ", ".join(p for p in e["projects"] if p),
        })
    return salida
