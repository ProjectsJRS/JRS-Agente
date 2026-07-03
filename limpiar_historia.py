# limpiar_historia.py
# ============================================================================
# Borra entradas de PRUEBA de collection_jrs_history. Correr en Railway Console.
#
#   python limpiar_historia.py            -> DRY-RUN: solo muestra que borraria.
#   python limpiar_historia.py --confirm  -> respalda y borra de verdad.
#
# Antes de borrar, respalda las entradas objetivo (ids + metadata + documento +
# embedding) a un JSON en el volumen, para poder re-insertarlas si hiciera falta.
# ============================================================================

import os
import sys
import json
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from chromadb import PersistentClient
except Exception as e:
    print("ERROR: no se pudo importar chromadb: %r" % (e,))
    sys.exit(1)

CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_data")
COLECCION = "collection_jrs_history"

# Entradas de PRUEBA a borrar (confirmadas por Emmanuel el 2026-07-03).
IDS_A_BORRAR = [
    "crew_update_19f14a33da1c1850",  # Consolidated: CVS #4471, Target #1820, Lids Frisco
    "crew_update_19f23e29984c2ead",  # CVS #4471, Target #1820
    "crew_update_19f24db63ef6ece2",  # CVS #4471, Target #1820
    "crew_update_19f250c33cb81c8c",  # LensCrafters #8080
    "crew_update_19f2553ad4d9c39c",  # CVS #4471, Target #1820, LensCrafters #302
]


def main():
    confirmar = "--confirm" in sys.argv
    print("=" * 78)
    print("LIMPIEZA de %s" % COLECCION)
    print("Modo: %s" % ("CONFIRM (borra de verdad)" if confirmar else "DRY-RUN (no borra nada)"))
    print("CHROMA_DB_PATH = %s" % CHROMA_DB_PATH)
    print("=" * 78)

    try:
        client = PersistentClient(path=CHROMA_DB_PATH)
        col = client.get_or_create_collection(name=COLECCION)
        total_antes = col.count()
    except Exception as e:
        print("ERROR abriendo la coleccion: %r" % (e,))
        return

    print("Entradas totales antes: %d" % total_antes)

    # Traer las entradas objetivo (para respaldo y para confirmar que existen).
    # Embeddings best-effort: algunas versiones los devuelven como numpy.
    try:
        data = col.get(ids=IDS_A_BORRAR, include=["metadatas", "documents", "embeddings"])
    except Exception:
        try:
            data = col.get(ids=IDS_A_BORRAR, include=["metadatas", "documents"])
        except Exception as e:
            print("ERROR leyendo entradas objetivo: %r" % (e,))
            return

    encontrados = data.get("ids", []) or []
    print("Ids objetivo: %d   Encontrados en la coleccion: %d" % (len(IDS_A_BORRAR), len(encontrados)))
    faltantes = [i for i in IDS_A_BORRAR if i not in encontrados]
    if faltantes:
        print("AVISO: estos ids NO estan en la coleccion (se ignoran):")
        for i in faltantes:
            print("   - %s" % i)

    metas = data.get("metadatas") or []
    print("\nEntradas que se borrarian:")
    for idx, id_ in enumerate(encontrados):
        meta = metas[idx] if idx < len(metas) else {}
        proj = (meta or {}).get("projects", "")
        print("   - %s  ->  %s" % (id_, proj))

    if not encontrados:
        print("\nNada que borrar. Fin.")
        return

    if not confirmar:
        print("\nDRY-RUN: no se borro nada.")
        print("Para borrar de verdad (respalda primero), corre:")
        print("    python limpiar_historia.py --confirm")
        return

    # ---- Respaldo antes de borrar ----
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.dirname(CHROMA_DB_PATH) or "."
    backup_path = os.path.join(backup_dir, "historia_backup_borrados_%s.json" % ts)

    emb = data.get("embeddings")
    if emb is not None:
        try:
            emb = [list(map(float, e)) if e is not None else None for e in emb]
        except Exception:
            emb = None  # si no se puede serializar, el respaldo va sin embeddings

    respaldo = {
        "coleccion": COLECCION,
        "borrado_en": ts,
        "ids": encontrados,
        "metadatas": metas,
        "documents": data.get("documents"),
        "embeddings": emb,
    }
    try:
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(respaldo, f, ensure_ascii=False)
        print("\nRespaldo escrito en: %s" % backup_path)
    except Exception as e:
        print("\nERROR escribiendo respaldo (%r). Se ABORTA el borrado por seguridad." % (e,))
        return

    # ---- Borrado ----
    try:
        col.delete(ids=encontrados)
    except Exception as e:
        print("ERROR borrando: %r  (nada garantizado; revisa con el inventario)" % (e,))
        return

    total_despues = col.count()
    print("Entradas totales despues: %d   (borradas: %d)" % (total_despues, total_antes - total_despues))
    print("Listo. Verifica con: python inventario_historia.py")


if __name__ == "__main__":
    main()
