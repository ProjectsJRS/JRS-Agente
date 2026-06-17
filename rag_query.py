# rag_query.py
# Funciones de búsqueda en ChromaDB para RAG

import chromadb
from typing import List, Dict, Optional

# Cliente persistente (apunta a la misma carpeta que la carga)
_cliente = chromadb.PersistentClient(path="./chroma_data")

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

    # Construir el query: agregar familia y estado al texto de búsqueda
    query_text = f"{code_family} {topic}"
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

    # Determinar la mejor sección detectada
    best_section = ""
    for item in items:
        if item["metadata"].get("section_hint"):
            best_section = item["metadata"]["section_hint"]
            break

    # Determinar confianza basada en distance del top result
    top_distance = items[0]["distance"] if items else 1.0
    if top_distance < 0.5:
        confidence = "high"
    elif top_distance < 1.0:
        confidence = "medium"
    else:
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