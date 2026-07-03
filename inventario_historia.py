# inventario_historia.py
# ============================================================================
# SOLO LECTURA. Este script NO borra ni modifica nada. Lista todo lo que hay
# en collection_jrs_history para decidir, con datos a la vista, que entradas
# son de prueba y cuales son reales. Correr DENTRO del contenedor de Railway
# (Console), donde CHROMA_DB_PATH apunta al volumen real /data/chroma_db.
#
# Uso:   python inventario_historia.py
#
# Cada "entrada" es UN correo/reporte guardado. Un mismo correo puede cubrir
# varios proyectos (ej. un crew update consolidado). El borrado posterior sera
# POR ENTRADA (por id), no por proyecto: una entrada se borra solo si TODOS
# sus proyectos son de prueba.
# ============================================================================

import os
import sys
import json

# Forzar UTF-8 en la salida para no reventar con acentos / guiones largos.
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


def _s(valor):
    """Convierte cualquier valor a str ASCII-safe para imprimir sin riesgo."""
    try:
        return str(valor)
    except Exception:
        return repr(valor)


def main():
    print("=" * 78)
    print("INVENTARIO (solo lectura) -- %s" % COLECCION)
    print("CHROMA_DB_PATH = %s" % CHROMA_DB_PATH)
    print("=" * 78)

    try:
        client = PersistentClient(path=CHROMA_DB_PATH)
        col = client.get_or_create_collection(name=COLECCION)
    except Exception as e:
        print("ERROR abriendo la coleccion: %r" % (e,))
        return

    # Intento con include; si la version de chromadb no lo acepta, sin include.
    try:
        data = col.get(include=["metadatas"])
    except Exception:
        try:
            data = col.get()
        except Exception as e:
            print("ERROR leyendo la coleccion: %r" % (e,))
            return

    ids = data.get("ids", []) or []
    metas = data.get("metadatas", []) or []
    # Emparejar de forma segura aunque las longitudes difieran.
    if len(metas) < len(ids):
        metas = list(metas) + [{}] * (len(ids) - len(metas))

    print("")
    print("Total de entradas: %d" % len(ids))
    print("")

    for i, id_ in enumerate(ids, 1):
        meta = metas[i - 1] if i - 1 < len(metas) else {}
        meta = meta or {}
        try:
            fecha = meta.get("date", "")
            doc_type = meta.get("doc_type", "")
            risk = meta.get("risk_level", "")
            proyectos = meta.get("projects", "")
            estados = meta.get("states", "")

            print("[%3d] id = %s" % (i, _s(id_)))
            print("      date=%s   type=%s   risk=%s" % (
                _s(fecha) or "-", _s(doc_type) or "-", _s(risk) or "-"))
            print("      projects: %s" % (_s(proyectos) or "(ninguno)"))
            if estados:
                print("      states:   %s" % _s(estados))

            crews_raw = meta.get("crews_json", "")
            if crews_raw:
                try:
                    crews = json.loads(crews_raw)
                    for c in crews:
                        print("        - %s [%s] @ %s" % (
                            _s(c.get("project", "?")),
                            _s(c.get("status", "") or "-"),
                            _s(c.get("location", "") or "-"),
                        ))
                except Exception:
                    print("        (crews_json presente pero no parseable)")
        except Exception as e:
            print("[%3d] (entrada no legible: %r)" % (i, e))
        print("")

    print("=" * 78)
    print("FIN. No se modifico nada. Copia/screenshot esta salida para decidir")
    print("que ids borrar en el paso siguiente.")
    print("=" * 78)


if __name__ == "__main__":
    main()
