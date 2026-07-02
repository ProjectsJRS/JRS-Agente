# limpiar_historia.py
# Limpieza SEGURA de registros de prueba en collection_jrs_history.
#
# FASE 1 (default): solo LISTA lo que hay. No borra nada.
#   python limpiar_historia.py
#
# FASE 2: borra los IDs que le pases explicitamente.
#   python limpiar_historia.py --borrar crew_update_ABC crew_update_XYZ
#
# Regla de oro: primero mirar, luego borrar. Nunca borra sin IDs explicitos.

import os
import sys
import chromadb

CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_data")
COLECCION = "collection_jrs_history"


def _abrir():
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    return client.get_or_create_collection(name=COLECCION)


def listar():
    col = _abrir()
    data = col.get(include=["metadatas", "documents"])
    ids = data.get("ids", [])
    metas = data.get("metadatas", []) or []
    docs = data.get("documents", []) or []

    print(f"\nColeccion: {COLECCION}")
    print(f"Ruta:      {CHROMA_DB_PATH}")
    print(f"Total de registros: {len(ids)}\n")
    print("-" * 100)
    for i, doc_id in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        doc = docs[i] if i < len(docs) else ""
        fecha = meta.get("date", "?")
        proyectos = meta.get("projects", "?")
        riesgo = meta.get("risk_level", "?")
        preview = (doc[:70] + "...") if doc and len(doc) > 70 else (doc or "")
        print(f"[{i+1}] id: {doc_id}")
        print(f"     date={fecha} | risk={riesgo} | projects={proyectos}")
        print(f"     doc: {preview}")
        print("-" * 100)

    print("\nPara borrar, copia los IDs que quieras eliminar y corre:")
    print("  python limpiar_historia.py --borrar <id1> <id2> ...\n")


def borrar(ids):
    col = _abrir()
    antes = col.count()
    print(f"\nRegistros antes: {antes}")
    print("Se van a borrar estos IDs:")
    for i in ids:
        print(f"  - {i}")
    resp = input("\n¿Confirmas el borrado? (escribe 'si' para continuar): ").strip().lower()
    if resp != "si":
        print("Cancelado. No se borro nada.")
        return
    col.delete(ids=ids)
    despues = col.count()
    print(f"\nListo. Registros despues: {despues} (se borraron {antes - despues}).")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--borrar":
        borrar(sys.argv[2:])
    else:
        listar()
