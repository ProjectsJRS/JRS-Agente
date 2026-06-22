# test_ada.py
# Mini-testing honesto: solo preguntas que el ADA 2010 (cargado) puede responder.
# Cada caso incluye la respuesta oficial esperada para verificación manual contra el PDF.

from tools import consult_building_code

# (topic que se le pasa al agente, descripcion, respuesta oficial esperada)
CASOS = [
    ("minimum accessible door clear width",
     "Ancho libre minimo de puerta accesible",
     "32 in (815 mm) -- Section 404.2.3"),
    ("maximum ramp slope",
     "Pendiente maxima de rampa",
     "1:12 -- Section 405.2"),
    ("accessible sales counter height",
     "Altura maxima de mostrador accesible",
     "36 in max / porcion a 34 in -- Section 904.4"),
    ("tactile signage requirements",
     "Senaletica tactil",
     "Section 703 (raised characters / Braille)"),
    ("detectable warnings truncated domes",
     "Avisos detectables (detectable warnings)",
     "Section 705"),
    ("maximum reach range for operable controls",
     "Alcance maximo para controles",
     "48 in max (forward/side reach) -- Section 308"),
    ("maximum running slope of accessible route",
     "Pendiente maxima de ruta accesible / acera",
     "1:20 (running slope) -- Section 403.3"),
]

print("="*78)
print("  MINI-TESTING ADA 2010  --  Verificacion honesta de lo cargado")
print("="*78)

aciertos_rag = 0
for i, (topic, desc, esperado) in enumerate(CASOS, 1):
    r = consult_building_code("ADA", topic)
    encontro = r["confidence"] in ("high", "medium") and r["text"].strip()
    if encontro:
        aciertos_rag += 1
    print(f"\n[{i}] {desc}")
    print(f"    Pregunta (topic):  {topic}")
    print(f"    Esperado (oficial): {esperado}")
    print(f"    --- Respuesta del agente ---")
    print(f"    Reference:   {r['reference']}")
    print(f"    Section:     {repr(r['section'])}")
    print(f"    Confidence:  {r['confidence']}")
    print(f"    RAG recupero contenido: {'SI' if encontro else 'NO'}")
    print(f"    Text (preview): {r['text'][:160].strip()}...")
    print(f"    >>> VEREDICTO MANUAL (verificar contra PDF): [ ] OK  [ ] Parcial  [ ] Falla")

print("\n" + "="*78)
print(f"  RAG recupero contenido en {aciertos_rag}/{len(CASOS)} casos de ADA.")
print("  NOTA: el acierto final lo decides TU verificando cada cita contra el")
print("  PDF oficial del ADA. Este script solo muestra que el RAG responde;")
print("  la PRECISION tecnica la confirma el ojo humano.")
print("="*78)