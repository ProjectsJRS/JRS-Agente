# metrics.py
# Bitacora operativa del agente. Cada evento (un correo procesado) se anexa
# como UNA linea JSON a metrics.jsonl en el volumen. El dashboard la lee y
# agrega (emails, tiempo promedio, reportes). Las alertas NO se registran
# aqui: ya viven en alerts.jsonl y el dashboard las cuenta de ahi.
#
# PRINCIPIO CRITICO: registrar_metrica NUNCA lanza. El agente corre 24/7 y
# anotar una metrica jamas debe interrumpir el procesamiento de correos. Si
# algo falla (disco lleno, permisos, volumen no montado), se traga el error
# en silencio. Es una nota al margen: si la pluma se rompe, el trabajo sigue.
#
# UBICACION: mismo patron que heartbeat/alerts/archivados. Se deriva de
# CHROMA_DB_PATH -> dirname -> volumen. En Railway /data/metrics.jsonl; en
# local ./metrics.jsonl.
#
# CRECIMIENTO: append eterno. A volumen bajo son kilobytes al mes; si algun
# dia pesa demasiado, se le pone rotacion. Por ahora no se sobre-ingenieria.

import os
import json
from datetime import datetime

_VOLUME_DIR = os.path.dirname(os.getenv("CHROMA_DB_PATH", "./chroma_data")) or "."
METRICS_FILE = os.path.join(_VOLUME_DIR, "metrics.jsonl")


def registrar_metrica(evento: str, **campos) -> None:
    """
    Anexa una linea JSON a metrics.jsonl con un timestamp y el tipo de evento.
    Los campos extra (result, duration_sec, report_generated, ...) van tal cual.

    NUNCA lanza excepcion: cualquier fallo se traga para no tumbar el ciclo
    de procesamiento del agente.
    """
    try:
        registro = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event": evento,
        }
        registro.update(campos)
        with open(METRICS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except Exception:
        # Silencio deliberado: una metrica que no se pudo escribir jamas debe
        # propagar un error al agente.
        pass
