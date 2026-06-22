# probar_rag.py
# Verificación del flujo RAG con lo cargado actualmente (solo ADA).

from tools import consult_building_code


def mostrar(titulo, r, espera):
    print(f"\n{titulo}")
    print(f"  Reference:  {r['reference']}")
    print(f"  Section:    {repr(r['section'])}")
    print(f"  Confidence: {r['confidence']}  (esperado: {espera})")
    print(f"  Nota:       {r['jurisdiction_note']}")
    print(f"  Text (preview): {r['text'][:180]}...")


# CASO 1 — ADA (CARGADO): debe devolver texto real, confidence medium/high
r1 = consult_building_code("ADA", "door clear width minimum")
mostrar("CASO 1 — ADA door clear width [CARGADO]", r1, "medium/high")

# CASO 2 — IBC (NO cargado): debe devolver confidence low, honestamente
r2 = consult_building_code("IBC", "ceiling height for retail Group M")
mostrar("CASO 2 — IBC ceiling height [NO CARGADO]", r2, "low")

# CASO 3 — OSHA (NO cargado): debe devolver confidence low, honestamente
r3 = consult_building_code("OSHA 1926", "fall protection threshold height")
mostrar("CASO 3 — OSHA fall protection [NO CARGADO]", r3, "low")

print("\n" + "="*55)
print("VEREDICTO:")
print("  - Caso 1 con texto real y confidence medium/high  -> RAG OK")
print("  - Casos 2 y 3 con confidence low                  -> honestidad OK")
print("="*55)