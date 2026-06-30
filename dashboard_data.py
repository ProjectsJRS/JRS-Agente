# dashboard_data.py
# Capa de datos del dashboard ejecutivo de JRS.
# Separa la logica de datos de la presentacion: lee de ChromaDB, logs,
# heartbeat y reportes, y devuelve datos estructurados al dashboard.
#
# ESTADO INCREMENTAL (segun Documento 07):
#   - get_agent_status      -> DATOS REALES (heartbeat) [LISTO]
#   - get_active_projects   -> stub (lee de collection_jrs_history) [PENDIENTE]
#   - get_recent_alerts     -> stub (parse de logs) [PENDIENTE]
#   - get_operational_metrics -> stub (agregaciones) [PENDIENTE]
#   - get_crews_status      -> stub (analisis predictivo, Paso 7.4) [FUTURO]
#   - get_clients_at_risk   -> stub (analisis predictivo, Paso 7.4) [FUTURO]

import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict

# Mismas rutas/variables que usa el agente, para leer del mismo volumen.
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_data")
_VOLUME_DIR = os.path.dirname(CHROMA_DB_PATH) or "."
HEARTBEAT_FILE = os.path.join(_VOLUME_DIR, "heartbeat.txt")
REPORTES_DIR = os.path.join(_VOLUME_DIR, "reportes_diarios")

# Umbral: mas de este tiempo sin latido => agente considerado caido.
HEARTBEAT_UMBRAL_MIN = 10


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
            last_beat = datetime.fromisoformat(f.read().strip())
        delta_minutes = (datetime.now() - last_beat).total_seconds() / 60
        is_alive = delta_minutes < HEARTBEAT_UMBRAL_MIN
    except Exception:
        # Sin heartbeat legible => asumimos caido (estado honesto).
        is_alive = False
        delta_minutes = 999

    # Ultimo reporte diario archivado (Fase 6). Si la carpeta no existe aun,
    # devolvemos 'never' sin romper nada.
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
# STUBS — devuelven placeholders por ahora.
# Se conectaran a datos reales en pasos siguientes (uno por uno).
# =====================================================
def get_active_projects() -> List[Dict]:
    """Proyectos activos. PENDIENTE: query a collection_jrs_history."""
    return []


def get_recent_alerts() -> List[Dict]:
    """Alertas CRITICAL/HIGH de las ultimas 24h. PENDIENTE: parse de logs."""
    return []


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
