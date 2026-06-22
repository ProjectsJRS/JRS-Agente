# codigos_referencia.py
# Capa de "enlazar en vez de almacenar" para códigos cuyo texto NO puede
# guardarse en ChromaDB por restricciones de copyright (NFPA 101 y NFPA 70).
#
# La NFPA ofrece acceso gratuito SOLO de lectura en línea; sus documentos
# no son descargables ni imprimibles. Almacenar su texto sería una violación
# de copyright. En su lugar, el agente RECONOCE el tema, nombra el código y
# capítulo correctos, y DIRIGE al usuario al acceso oficial gratuito,
# marcando que requiere verificación manual.
#
# Cuando JRS adquiera una licencia NFPA LiNK (o el texto legal), basta con
# quitar la familia de este mapa y cargarla a ChromaDB como cualquier otro.

from typing import Dict, Optional

# URL raíz de acceso gratuito (respaldo si un enlace específico cambia).
NFPA_FREE_ACCESS_ROOT = "https://www.nfpa.org/free-access"

# Mapa de códigos de referencia (no almacenables).
# Para cada familia: nombre, edición, temas que cubre (para detección),
# capítulos típicos relevantes a retail, y enlace oficial de acceso gratuito.
CODIGOS_REFERENCIA: Dict[str, Dict] = {
    "NFPA 101": {
        "title": "Life Safety Code",
        "edition": "2024",
        "topics": [
            "egress", "means of egress", "exit", "occupant load",
            "exit signage", "exit capacity", "travel distance",
            "occupancy", "life safety", "emergency", "evacuation",
            "egreso", "salida", "carga de ocupantes", "evacuacion",
        ],
        "chapters": "Chapter 7 (Means of Egress); Chapter 6 (Occupancy "
                    "Classification); Chapter 12-13 (Assembly/Mercantile)",
        "free_access_url": "https://link.nfpa.org/all-publications/101/2024",
    },
    "NFPA 70": {
        "title": "National Electrical Code (NEC)",
        "edition": "2023",
        "topics": [
            "electrical", "circuit", "wiring", "conductor", "grounding",
            "panel", "breaker", "voltage", "receptacle", "branch circuit",
            "electrical installation", "nec",
            "electrico", "circuito", "cableado", "conexion a tierra",
        ],
        "chapters": "Article 210 (Branch Circuits); Article 240 "
                    "(Overcurrent Protection); Article 250 (Grounding)",
        "free_access_url": "https://link.nfpa.org/free-access/publications/70/2023",
    },
}

# Alias de familia → clave canónica (tolera variantes de escritura).
_ALIAS = {
    "NFPA 101": "NFPA 101", "NFPA-101": "NFPA 101", "NFPA101": "NFPA 101",
    "LIFE SAFETY CODE": "NFPA 101",
    "NFPA 70": "NFPA 70", "NFPA-70": "NFPA 70", "NFPA70": "NFPA 70",
    "NEC": "NFPA 70", "NATIONAL ELECTRICAL CODE": "NFPA 70",
}


def es_codigo_de_referencia(code_family: str) -> bool:
    """Indica si la familia se maneja por referencia (no por ChromaDB)."""
    if not code_family:
        return False
    return _ALIAS.get(code_family.upper().strip()) in CODIGOS_REFERENCIA


def consultar_referencia(code_family: str, topic: str,
                         state: Optional[str] = None) -> Dict:
    """
    Devuelve una respuesta de ORIENTACIÓN para un código no almacenable.
    Mantiene el mismo formato que consult_building_code para encajar sin
    fricción en el agente.
    """
    clave = _ALIAS.get(code_family.upper().strip())
    info = CODIGOS_REFERENCIA.get(clave)
    if not info:
        return {
            "section": "",
            "title": "",
            "text": "",
            "reference": "",
            "confidence": "low",
            "jurisdiction_note": "Code family not recognized as reference code.",
            "is_reference_only": True,
        }

    nota_estado = (f" Verify adoption and any amendments in {state}."
                   if state else " Verify local adoption in the applicable "
                   "jurisdiction.")

    texto = (
        f"This topic is governed by {clave} ({info['title']}), "
        f"{info['edition']} edition. Relevant areas: {info['chapters']}. "
        f"NOTE: {clave} is copyrighted and not stored in this system. "
        f"Consult the official free-access text and confirm the exact "
        f"section manually before citing in any client-facing document. "
        f"Official free access: {info['free_access_url']} "
        f"(fallback: {NFPA_FREE_ACCESS_ROOT})."
    )

    return {
        "section": "",  # nunca inventamos sección para código no almacenado
        "title": f"{clave} — {info['title']} ({info['edition']})",
        "text": texto,
        "reference": f"Per {clave} {info['edition']} (verify section manually)",
        "confidence": "reference",  # estado especial: ni high/medium/low
        "jurisdiction_note": nota_estado.strip(),
        "is_reference_only": True,
    }
