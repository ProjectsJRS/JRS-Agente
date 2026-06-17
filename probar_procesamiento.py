# probar_procesamiento.py
from pdf_processor import procesar_pdf_completo

resultado = procesar_pdf_completo(
    "C:\\Users\\Emmanuel Mendoza\\Desktop\\jrs-agente\\codigos_pdf\\03_accessibility\\ADA_Standards_2010.pdf",
    tamano_chunk=1000,
    overlap=150,
)

if resultado["error"]:
    print(f"❌ Error: {resultado['error']}")
else:
    print(f"\n📊 Resumen:")
    print(f"   Páginas: {resultado['num_paginas']}")
    print(f"   Chunks generados: {resultado['num_chunks']}")
    print(f"   Requirió OCR: {resultado['requirio_ocr']}")
    print(f"\n📝 Primer chunk (preview):")
    print(resultado['chunks'][368][:500])
    print("\n...")