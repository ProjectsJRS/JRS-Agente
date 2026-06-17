# cargar_codigos.py
# Procesa PDFs de códigos y los carga a las colecciones correctas de ChromaDB

import os
import re
import chromadb
from pathlib import Path
from pdf_processor import procesar_pdf_completo

# Cliente persistente de ChromaDB
cliente = chromadb.PersistentClient(path="./chroma_data")

# Mapeo de subcarpeta → nombre de colección
MAPEO_COLECCIONES = {
    "01_building_codes":      "building_codes",
    "02_safety_codes":        "safety_codes",
    "03_accessibility":       "accessibility",
    "04_osha_safety":         "osha_safety",
    "05_aia_contracts":       "aia_contracts",
    "06_state_amendments":    "state_amendments",
    "07_construction_methods": "construction_methods",
    "08_estimating_data":     "estimating_data",
}


# Inferencia de family/year/title desde el nombre de archivo
def inferir_metadatos(nombre_archivo: str, subcarpeta: str) -> dict:
    nombre = nombre_archivo.replace(".pdf", "")

    # Detectar familia
    family = "UNKNOWN"
    title = nombre
    state = None

    if "IBC" in nombre:    family, title = "IBC", "International Building Code"
    elif "IFC" in nombre:  family, title = "IFC", "International Fire Code"
    elif "IPC" in nombre:  family, title = "IPC", "International Plumbing Code"
    elif "IECC" in nombre: family, title = "IECC", "International Energy Conservation Code"
    elif "IMC" in nombre:  family, title = "IMC", "International Mechanical Code"
    elif "NFPA_101" in nombre or "NFPA101" in nombre: family, title = "NFPA 101", "Life Safety Code"
    elif "NFPA_1" in nombre and "NFPA_101" not in nombre: family, title = "NFPA 1", "Fire Code"
    elif "NFPA_13" in nombre: family, title = "NFPA 13", "Sprinkler Systems"
    elif "NFPA_70" in nombre: family, title = "NFPA 70", "National Electrical Code (NEC)"
    elif "NFPA_72" in nombre: family, title = "NFPA 72", "Fire Alarm and Signaling"
    elif "ADA" in nombre: family, title = "ADA", "ADA Standards for Accessible Design"
    elif "A117" in nombre: family, title = "ICC A117.1", "Accessible and Usable Buildings"
    elif "OSHA_29_CFR_1926" in nombre: family, title = "OSHA 1926", "Construction Safety"
    elif "OSHA_29_CFR_1910" in nombre: family, title = "OSHA 1910", "General Industry"
    elif "AIA_" in nombre: family = nombre.split("_")[1]; title = f"AIA {family}"

    # Detectar año (4 dígitos en el nombre)
    match_year = re.search(r"_(\d{4})", nombre)
    year = match_year.group(1) if match_year else ""

    # Detectar estado (prefijo de 2 letras en state_amendments)
    if subcarpeta == "06_state_amendments":
        match_state = re.match(r"^([A-Z]{2})_", nombre)
        if match_state:
            state = match_state.group(1)

    return {
        "family": family,
        "year": year,
        "title": title,
        "state": state,
        "source_file": nombre_archivo,
    }
def cargar_un_pdf(ruta_pdf: str, subcarpeta: str) -> dict:
    """
    Procesa un PDF y carga sus chunks a la colección correcta de ChromaDB.

    Returns:
        Dict con: archivo, num_chunks_cargados, error (None si ok).
    """
    nombre = os.path.basename(ruta_pdf)
    print(f"\n{'='*60}")
    print(f"📚 Cargando: {nombre}")
    print(f"   Subcarpeta: {subcarpeta}")

    # Determinar colección destino
    nombre_coleccion = MAPEO_COLECCIONES.get(subcarpeta)
    if not nombre_coleccion:
        return {"archivo": nombre, "num_chunks_cargados": 0,
                "error": f"Subcarpeta sin mapeo: {subcarpeta}"}

    coleccion = cliente.get_or_create_collection(name=nombre_coleccion)

    # Procesar el PDF
    resultado = procesar_pdf_completo(ruta_pdf, tamano_chunk=1000, overlap=150)
    if resultado["error"]:
        return {"archivo": nombre, "num_chunks_cargados": 0,
                "error": resultado["error"]}

    chunks = resultado["chunks"]
    if not chunks:
        return {"archivo": nombre, "num_chunks_cargados": 0,
                "error": "No se generaron chunks."}

    # Inferir metadatos comunes
    metadatos_base = inferir_metadatos(nombre, subcarpeta)

    # Preparar batch para inserción
    ids = []
    documents = []
    metadatas = []

    base_id = nombre.replace(".pdf", "").replace(" ", "-").lower()
    for i, chunk in enumerate(chunks):
        chunk_id = f"{base_id}-chunk-{i:05d}"
        ids.append(chunk_id)
        documents.append(chunk)

        # Detectar sección si está en el chunk (ej: 'Section 1003.2' o '§ 1926.501')
        section_hint = ""
        m1 = re.search(r"Section\s+(\d+\.\d+(?:\.\d+)?)", chunk)
        m2 = re.search(r"§\s*(\d+\.\d+(?:\.\d+)?)", chunk)
        if m1: section_hint = m1.group(1)
        elif m2: section_hint = m2.group(1)

        metadata_chunk = {
            **metadatos_base,
            "section_hint": section_hint,
            "chunk_index": i,
            "chunk_chars": len(chunk),
        }
        # ChromaDB no acepta None en metadata, reemplazar por string vacío
        metadata_chunk = {k: (v if v is not None else "") for k, v in metadata_chunk.items()}
        metadatas.append(metadata_chunk)

    # Insertar en lotes de 500 (límite recomendado de ChromaDB)
    BATCH = 500
    insertados = 0
    for i in range(0, len(ids), BATCH):
        coleccion.add(
            ids=ids[i:i+BATCH],
            documents=documents[i:i+BATCH],
            metadatas=metadatas[i:i+BATCH],
        )
        insertados += len(ids[i:i+BATCH])
        print(f"   ... insertados {insertados}/{len(ids)} chunks")

    print(f"   ✅ {nombre} → colección '{nombre_coleccion}' ({insertados} chunks)")
    return {"archivo": nombre, "num_chunks_cargados": insertados, "error": None}
def cargar_todos_los_pdfs(carpeta_raiz: str = "codigos_pdf") -> dict:
    """
    Recorre todas las subcarpetas y carga todos los PDFs a ChromaDB.

    Returns:
        Dict con resumen: total_archivos, total_chunks, errores (lista).
    """
    raiz = Path(carpeta_raiz)
    if not raiz.exists():
        return {"error": f"Carpeta {carpeta_raiz} no existe."}

    total_archivos = 0
    total_chunks = 0
    errores = []

    for subcarpeta in sorted(MAPEO_COLECCIONES.keys()):
        ruta_sub = raiz / subcarpeta
        if not ruta_sub.exists():
            print(f"⚠️  Subcarpeta no existe: {ruta_sub} (saltando)")
            continue

        pdfs = sorted(ruta_sub.glob("*.pdf"))
        print(f"\n📁 {subcarpeta} — {len(pdfs)} PDFs")

        for pdf_path in pdfs:
            resultado = cargar_un_pdf(str(pdf_path), subcarpeta)
            total_archivos += 1
            total_chunks += resultado["num_chunks_cargados"]
            if resultado["error"]:
                errores.append({
                    "archivo": resultado["archivo"],
                    "error": resultado["error"],
                })

    print(f"\n{'='*60}")
    print(f"🎉 CARGA COMPLETA")
    print(f"   Archivos procesados: {total_archivos}")
    print(f"   Chunks totales en ChromaDB: {total_chunks}")
    if errores:
        print(f"   ⚠️  Errores: {len(errores)}")
        for e in errores:
            print(f"      - {e['archivo']}: {e['error']}")

    return {
        "total_archivos": total_archivos,
        "total_chunks": total_chunks,
        "errores": errores,
    }


if __name__ == "__main__":
    cargar_todos_los_pdfs()