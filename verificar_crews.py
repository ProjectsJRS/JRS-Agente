# verificar_crews.py
# Muestra la metadata del registro MAS RECIENTE en collection_jrs_history,
# para confirmar que los campos nuevos (states, crews_json) se guardaron bien.
# USO:  python verificar_crews.py

import os
import json
import chromadb

CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_data")

c = chromadb.PersistentClient(path=CHROMA_DB_PATH)
col = c.get_or_create_collection("collection_jrs_history")
d = col.get(include=["metadatas"])

metas = d.get("metadatas") or []
if not metas:
    print("La coleccion esta vacia. Manda un crew update primero.")
    raise SystemExit(0)

m = metas[-1]  # el mas reciente

print("=" * 60)
print("Registro mas reciente")
print("=" * 60)
print("date:     ", m.get("date"))
print("projects: ", m.get("projects"))
print("risk:     ", m.get("risk_level"))
print("states:   ", m.get("states", "(no existe - registro viejo?)"))
print()
print("crews_json:")
crews_raw = m.get("crews_json")
if not crews_raw:
    print("  (no existe - registro viejo, sin detalle por crew)")
else:
    try:
        crews = json.loads(crews_raw)
        print(json.dumps(crews, ensure_ascii=False, indent=2))
        print(f"\n  -> {len(crews)} crew(s) extraidos correctamente.")
    except Exception as e:
        print(f"  ERROR al leer crews_json: {e}")

print()
if m.get("states") and m.get("crews_json"):
    print("RESULTADO: OK — los campos nuevos se guardaron. Capa de datos lista.")
else:
    print("RESULTADO: REVISAR — faltan campos nuevos en este registro.")
