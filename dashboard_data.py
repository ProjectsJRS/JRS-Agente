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
from typing import List, Dict, Tuple

from chromadb import PersistentClient

from ciudades_coords import resolver_coords

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

# =====================================================
# PROYECTOS ARCHIVADOS — gestion sin código ni deploy.
# La lista vive en el volumen (/data en Railway, ./ en local), igual que
# heartbeat/alerts/config. Archivar/reactivar es instantaneo desde el
# dashboard: no requiere commit ni redeploy. Un proyecto archivado deja de
# aparecer en Active Projects, Project Detail y el mapa.
# =====================================================
ARCHIVADOS_FILE = os.path.join(_VOLUME_DIR, "archivados.json")


def get_archivados() -> List[str]:
    """Devuelve la lista de codigos de proyecto archivados. [] si no existe."""
    try:
        with open(ARCHIVADOS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(p) for p in data]
    except Exception:
        pass
    return []


def _guardar_archivados(lista: List[str]) -> bool:
    try:
        # Sin duplicados, orden estable.
        unicos = sorted(set(p for p in lista if p))
        with open(ARCHIVADOS_FILE, "w", encoding="utf-8") as f:
            json.dump(unicos, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def archivar_proyecto(project: str) -> bool:
    """Marca un proyecto como archivado (deja de aparecer en las secciones activas)."""
    if not project:
        return False
    actuales = get_archivados()
    if project not in actuales:
        actuales.append(project)
    return _guardar_archivados(actuales)


def reactivar_proyecto(project: str) -> bool:
    """Quita un proyecto de la lista de archivados (vuelve a aparecer)."""
    actuales = [p for p in get_archivados() if p != project]
    return _guardar_archivados(actuales)


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

    # Ocultar los proyectos archivados (gestionados desde el dashboard).
    archivados = set(get_archivados())
    return [r for r in resultados if r.get("project") not in archivados]


# =====================================================
# STUBS — se conectaran a datos reales en pasos siguientes.
# =====================================================
ALERTS_FILE = os.path.join(_VOLUME_DIR, "alerts.jsonl")
METRICS_FILE = os.path.join(_VOLUME_DIR, "metrics.jsonl")


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


def get_operational_metrics(days: int = ACTIVE_WINDOW_DAYS) -> Dict:
    """
    Agrega metricas operativas de los ultimos `days` dias.

    Fuentes:
      - metrics.jsonl (escrito por el agente): emails_processed, avg_processing,
        reports_generated.
      - alerts.jsonl (ya existente): alerts_count.

    Robusto: si un archivo no existe o una linea esta corrupta, la salta.
    Si aun no hay datos, los contadores son 0 y avg_processing es '—'.
    Nota: 'WhatsApp messages' se elimino del alcance (no aplica a JRS).
    """
    cutoff = datetime.now() - timedelta(days=days)

    emails = 0
    reportes = 0
    duraciones: List[float] = []
    try:
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            for linea in f:
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
                if reg.get("event") == "email_processed":
                    emails += 1
                    if reg.get("report_generated"):
                        reportes += 1
                    d = reg.get("duration_sec")
                    if isinstance(d, (int, float)):
                        duraciones.append(float(d))
    except Exception:
        pass

    # Alertas: reutilizamos alerts.jsonl. No duplicamos el registro en metrics.
    alertas = 0
    try:
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    reg = json.loads(linea)
                    ts = datetime.strptime(reg["timestamp"], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
                if ts >= cutoff:
                    alertas += 1
    except Exception:
        pass

    if duraciones:
        avg = sum(duraciones) / len(duraciones)
        avg_processing = f"{avg:.0f}s" if avg >= 1 else f"{avg:.1f}s"
    else:
        avg_processing = "—"

    return {
        "emails_processed": emails,
        "reports_generated": reportes,
        "alerts_count": alertas,
        "avg_processing": avg_processing,
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

    # Ocultar archivados (esto tambien filtra el mapa, que se construye sobre esta funcion).
    archivados = set(get_archivados())
    return [r for r in resultados if r.get("project") not in archivados]


def get_crew_map_data() -> List[Dict]:
    """
    Agrega por CIUDAD para el mapa de burbujas. Cada item:
    city, state, lat, lon, count (proyectos activos en esa ubicacion),
    worst_status, projects (lista separada por coma).

    Usa resolver_coords (ciudades_coords.py) para traducir la ubicacion a
    lat/lon. Si una ubicacion no resuelve (sin ciudad ni estado reconocible)
    se omite del mapa. Proyectos que caen al mismo punto (misma ciudad o
    mismo centroide de estado por fallback) se agrupan en una sola burbuja.
    """
    detalles = get_project_details()
    por_punto: Dict[Tuple[float, float], Dict] = {}
    for d in detalles:
        location = d.get("location", "")
        state = d.get("state", "")
        coords = resolver_coords(location, state)
        if coords is None:
            continue
        e = por_punto.setdefault(
            coords,
            {
                "city": location or state,
                "state": state,
                "lat": coords[0],
                "lon": coords[1],
                "count": 0,
                "worst": 0,
                "projects": [],
            },
        )
        e["count"] += 1
        e["projects"].append(d.get("project", ""))
        sev = _STATUS_SEVERITY.get(d.get("status", ""), 0)
        if sev > e["worst"]:
            e["worst"] = sev

    salida = []
    for e in por_punto.values():
        salida.append({
            "city": e["city"],
            "state": e["state"],
            "lat": e["lat"],
            "lon": e["lon"],
            "count": e["count"],
            "worst_status": _SEVERITY_LABEL.get(e["worst"], "—"),
            "projects": ", ".join(p for p in e["projects"] if p),
        })
    return salida
