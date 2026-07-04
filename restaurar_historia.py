# restaurar_historia.py
# ============================================================================
# Re-inserta en collection_jrs_history las entradas de un respaldo JSON
# (el que genero limpiar_historia.py). Solo AGREGA; NO borra nada. Es
# idempotente: si una entrada ya existe, la salta (puedes correrlo dos veces
# sin duplicar).
#
#   python restaurar_historia.py                  -> usa el respaldo MAS RECIENTE
#   python restaurar_historia.py <archivo.json>   -> usa ese respaldo especifico
#
# Corre donde quieras restaurar: en LOCAL usa ./chroma_data; en Railway usaria
# /data/chroma_db. Aqui lo quieres en LOCAL (tu PowerShell), asi que restaura
# tu ./chroma_data.
# ============================================================================

import os
import sys
import glob
import json

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


def _elegir_backup():
    # Arg explicito, o el respaldo mas reciente en la carpeta del volumen.
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        return args[0]
    carpeta = os.path.dirname(CHROMA_DB_PATH) or "."
    patron = os.path.join(carpeta, "historia_backup_borrados_*.json")
    candidatos = sorted(glob.glob(patron))
    return candidatos[-1] if candidatos else None


def main():
    print("=" * 78)
    print("RESTAURAR entradas en %s" % COLECCION)
    print("CHROMA_DB_PATH = %s" % CHROMA_DB_PATH)

    backup_path = _elegir_backup()
    if not backup_path or not os.path.exists(backup_path):
        print("ERROR: no encontre archivo de respaldo. Pasa la ruta como argumento:")
        print("    python restaurar_historia.py historia_backup_borrados_XXXX.json")
        return
    print("Respaldo: %s" % backup_path)
    print("=" * 78)

    try:
        with open(backup_path, "r", encoding="utf-8") as f:
            resp = json.load(f)
    except Exception as e:
        print("ERROR leyendo el respaldo: %r" % (e,))
        return

    ids = resp.get("ids") or []
    metas = resp.get("metadatas") or []
    docs = resp.get("documents") or []
    embs = resp.get("embeddings")

    if not ids:
        print("El respaldo no tiene entradas. Nada que restaurar.")
        return

    try:
        client = PersistentClient(path=CHROMA_DB_PATH)
        col = client.get_or_create_collection(name=COLECCION)
        total_antes = col.count()
    except Exception as e:
        print("ERROR abriendo la coleccion: %r" % (e,))
        return
    print("Entradas totales antes: %d" % total_antes)

    # Idempotencia: no re-insertar lo que ya existe.
    try:
        existentes = set(col.get(ids=ids).get("ids", []) or [])
    except Exception:
        existentes = set()

    a_insertar = [i for i, id_ in enumerate(ids) if id_ not in existentes]
    ya_estan = [id_ for id_ in ids if id_ in existentes]
    if ya_estan:
        print("Ya presentes (se saltan): %s" % ya_estan)
    if not a_insertar:
        print("Todo el respaldo ya esta en la coleccion. Nada que hacer.")
        return

    add_ids = [ids[i] for i in a_insertar]
    add_metas = [metas[i] if i < len(metas) else {} for i in a_insertar]
    add_docs = [docs[i] if i < len(docs) else "" for i in a_insertar]

    kwargs = {"ids": add_ids, "metadatas": add_metas, "documents": add_docs}
    # Usar los embeddings del respaldo si estan (restauracion EXACTA). Si no,
    # add() los recalcularia con la funcion de embedding por defecto.
    if embs is not None:
        add_embs = [embs[i] for i in a_insertar]
        if all(e is not None for e in add_embs):
            kwargs["embeddings"] = add_embs
            print("Restaurando con embeddings del respaldo (exacto).")
        else:
            print("AVISO: faltan embeddings en el respaldo; se recalcularan.")
    else:
        print("AVISO: el respaldo no trae embeddings; se recalcularan.")

    print("Insertando: %s" % add_ids)
    try:
        col.add(**kwargs)
    except Exception as e:
        print("ERROR insertando: %r" % (e,))
        return

    total_despues = col.count()
    print("Entradas totales despues: %d   (restauradas: %d)" % (
        total_despues, total_despues - total_antes))
    print("Listo. Verifica con: python inventario_historia.py")


if __name__ == "__main__":
    main()
