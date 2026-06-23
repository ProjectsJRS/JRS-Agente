# rag_query.py
# Funciones de búsqueda en ChromaDB para RAG

import chromadb
import os
import re
from typing import List, Dict, Optional

# Cliente persistente. La ruta sale de la variable de entorno CHROMA_DB_PATH.
# En local no existe esa variable, asi que usa "./chroma_data" (igual que antes).
# En Railway la variable apunta al volumen persistente: /data/chroma_db.
_CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_data")
_cliente = chromadb.PersistentClient(path=_CHROMA_PATH)

# Mapeo: familia de código → colección donde buscar
FAMILIA_A_COLECCION = {
    "IBC":           "building_codes",
    "IFC":           "building_codes",
    "IPC":           "building_codes",
    "IECC":          "building_codes",
    "IMC":           "building_codes",
    "NFPA 101":      "safety_codes",
    "NFPA-101":      "safety_codes",
    "NFPA 1":        "safety_codes",
    "NFPA 13":       "safety_codes",
    "NFPA 70":       "safety_codes",
    "NFPA 72":       "safety_codes",
    "ADA":           "accessibility",
    "ICC A117.1":    "accessibility",
    "OSHA-1926":     "osha_safety",
    "OSHA 1926":     "osha_safety",
    "OSHA-1910":     "osha_safety",
    "OSHA 1910":     "osha_safety",
    "AIA":           "aia_contracts",
}


def _coleccion_para_familia(code_family: str) -> Optional[str]:
    """Resuelve qué colección consultar según la familia de código."""
    if not code_family:
        return None
    return FAMILIA_A_COLECCION.get(code_family.upper().strip())


# Patrones para detectar números de sección en el texto (orden de preferencia).
# Cubren los estilos de IBC/ADA/OSHA/NFPA.
_PATRONES_SECCION = [
    re.compile(r"Section\s+(\d{1,4}\.\d+(?:\.\d+)*)"),       # "Section 404.2.3"
    re.compile(r"§\s*(\d{3,4}\.\d+(?:\.\d+)*)"),             # "§ 1926.501"
    re.compile(r"^\s*(\d{3,4}\.\d+(?:\.\d+)*)\s+[A-Z]",     # "404.2.3 Clear Width"
               re.MULTILINE),
]


def _detectar_seccion(items: List[Dict]) -> str:
    """
    Determina el número de sección más probable entre los chunks recuperados.
    Prioridad: (1) section_hint de metadata; (2) detección por regex en el texto.
    Recorre los chunks en orden de relevancia y devuelve la primera coincidencia.
    """
    for item in items:
        # 1) metadata
        hint = item["metadata"].get("section_hint")
        if hint:
            return hint
        # 2) texto del chunk
        for patron in _PATRONES_SECCION:
            m = patron.search(item.get("text", ""))
            if m:
                return m.group(1)
    return ""


def buscar_codigo(
    code_family: str,
    topic: str,
    state: Optional[str] = None,
    n_results: int = 5,
) -> Dict:
    """
    Busca en ChromaDB los chunks más relevantes para una consulta.

    Args:
        code_family: 'IBC', 'NFPA 101', 'ADA', etc.
        topic: tema a consultar (ej: 'ceiling height for retail').
        state: opcional, código de estado de 2 letras.
        n_results: número de chunks a devolver (default 5).

    Returns:
        Dict con keys:
          - found: bool
          - results: lista de dicts con {text, metadata, distance}
          - best_section: la sección más probable (si se detectó)
          - confidence: 'high' | 'medium' | 'low'
          - jurisdiction_note: nota sobre adopción local
    """
    coleccion_nombre = _coleccion_para_familia(code_family)
    if not coleccion_nombre:
        return {
            "found": False,
            "results": [],
            "best_section": "",
            "confidence": "low",
            "jurisdiction_note": f"Familia '{code_family}' no reconocida.",
        }

    try:
        coleccion = _cliente.get_collection(name=coleccion_nombre)
    except Exception as e:
        return {
            "found": False,
            "results": [],
            "best_section": "",
            "confidence": "low",
            "jurisdiction_note": f"Colección no disponible: {e}",
        }

    # Construir el query: enriquecer con familia, términos técnicos y estado.
    # Agregar "requirements minimum maximum dimensions" acerca la búsqueda a los
    # chunks que contienen las medidas concretas, no a los genéricos.
    query_text = f"{code_family} {topic} requirements minimum maximum dimensions"
    if state:
        query_text += f" applicable to {state}"

    # Construir filtros (where) si tenemos estado y aplica
    where = None
    if state and coleccion_nombre == "state_amendments":
        where = {"state": state.upper()}
    elif coleccion_nombre != "state_amendments":
        # Filtrar por familia exacta cuando es código nacional
        where = {"family": code_family.upper()}

    # Hacer query a ChromaDB
    try:
        resultados = coleccion.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where,
        )
    except Exception:
        # Si el where falla, reintentamos sin filtro
        resultados = coleccion.query(
            query_texts=[query_text],
            n_results=n_results,
        )

    docs = resultados.get("documents", [[]])[0]
    metas = resultados.get("metadatas", [[]])[0]
    distances = resultados.get("distances", [[]])[0]

    if not docs:
        return {
            "found": False,
            "results": [],
            "best_section": "",
            "confidence": "low",
            "jurisdiction_note": "No se encontraron chunks relevantes.",
        }

    # Construir resultados estructurados
    items = []
    for i, (texto, meta, dist) in enumerate(zip(docs, metas, distances)):
        items.append({
            "text": texto,
            "metadata": meta,
            "distance": dist,
            "rank": i + 1,
        })

    # Determinar la mejor sección detectada.
    # 1) Primero intenta desde metadata (section_hint).
    # 2) Si está vacío, la detecta en el texto del chunk al vuelo.
    best_section = _detectar_seccion(items)

    # Determinar confianza combinando distancia semántica + sección detectada.
    top_distance = items[0]["distance"] if items else 1.0
    if top_distance < 0.4:
        confidence = "high"
    elif top_distance < 0.7:
        confidence = "medium"
    else:
        confidence = "low"

    # Ajuste por sección: si NO se detectó número de sección, la respuesta es
    # menos accionable → bajamos un escalón de confianza (más honesto).
    if not best_section and confidence == "high":
        confidence = "medium"
    elif not best_section and confidence == "medium":
        confidence = "low"

    # Nota de jurisdicción
    if state:
        nota = f"Verify local adoption in {state}."
    else:
        nota = "Verify local adoption in the applicable jurisdiction."

    return {
        "found": True,
        "results": items,
        "best_section": best_section,
        "confidence": confidence,
        "jurisdiction_note": nota,
    }