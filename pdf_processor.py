# pdf_processor.py
# Procesa PDFs de códigos de construcción para cargarlos a ChromaDB
 
import os
import re
from pathlib import Path
from typing import List, Dict
import pypdf
import pdfplumber
 
# Opcional — solo si vas a usar OCR
try:
    import pytesseract
    from PIL import Image
    OCR_DISPONIBLE = True
except ImportError:
    OCR_DISPONIBLE = False

def extraer_texto_pdf(ruta_pdf: str) -> Dict:
    """
    Extrae texto completo de un PDF.

    Returns:
        Dict con keys: texto, num_paginas, requirio_ocr, error.
    """
    if not os.path.exists(ruta_pdf):
        return {"texto": "", "num_paginas": 0, "requirio_ocr": False,
                "error": f"Archivo no encontrado: {ruta_pdf}"}

    texto_completo = []
    num_paginas = 0

    # Intento 1: pdfplumber (mejor calidad para texto)
    try:
        with pdfplumber.open(ruta_pdf) as pdf:
            num_paginas = len(pdf.pages)
            for i, pagina in enumerate(pdf.pages):
                txt = pagina.extract_text() or ""
                if txt.strip():
                    texto_completo.append(f"[PAGE {i+1}]\n{txt}")
                if (i + 1) % 50 == 0:
                    print(f"   ... procesadas {i+1}/{num_paginas} páginas")

        texto = "\n\n".join(texto_completo).strip()
        if len(texto) > 1000:  # Si extrajo texto significativo
            return {"texto": texto, "num_paginas": num_paginas,
                    "requirio_ocr": False, "error": None}
    except Exception as e:
        print(f"   pdfplumber falló: {e}, intentando con pypdf...")

    # Intento 2: pypdf (fallback)
    try:
        with open(ruta_pdf, "rb") as f:
            reader = pypdf.PdfReader(f)
            num_paginas = len(reader.pages)
            texto_completo = []
            for i, pagina in enumerate(reader.pages):
                txt = pagina.extract_text() or ""
                if txt.strip():
                    texto_completo.append(f"[PAGE {i+1}]\n{txt}")

        texto = "\n\n".join(texto_completo).strip()
        if len(texto) > 1000:
            return {"texto": texto, "num_paginas": num_paginas,
                    "requirio_ocr": False, "error": None}
    except Exception as e:
        return {"texto": "", "num_paginas": 0, "requirio_ocr": False,
                "error": f"Ambos métodos fallaron. Último error: {e}"}

    # Si llegamos aquí, ambos métodos extrajeron casi nada → es PDF escaneado
    return {"texto": "", "num_paginas": num_paginas, "requirio_ocr": True,
            "error": "Texto extraído mínimo. Es un PDF escaneado, necesita OCR."}
def extraer_texto_pdf_ocr(ruta_pdf: str) -> Dict:
    """
    Extrae texto de un PDF escaneado usando OCR.
    Más lento (1-3 segundos por página) pero funciona en imágenes.
    """
    if not OCR_DISPONIBLE:
        return {"texto": "", "num_paginas": 0, "requirio_ocr": True,
                "error": "pytesseract/tesseract no instalados."}

    try:
        from pdf2image import convert_from_path
    except ImportError:
        return {"texto": "", "num_paginas": 0, "requirio_ocr": True,
                "error": "pdf2image no instalado. pip install pdf2image"}

    try:
        print(f"   Convirtiendo páginas a imagen (puede tardar)...")
        imagenes = convert_from_path(ruta_pdf, dpi=200)
        num_paginas = len(imagenes)

        texto_completo = []
        for i, imagen in enumerate(imagenes):
            texto_pagina = pytesseract.image_to_string(imagen, lang="eng")
            if texto_pagina.strip():
                texto_completo.append(f"[PAGE {i+1}]\n{texto_pagina}")
            if (i + 1) % 10 == 0:
                print(f"   ... OCR procesó {i+1}/{num_paginas} páginas")

        texto = "\n\n".join(texto_completo).strip()
        return {"texto": texto, "num_paginas": num_paginas,
                "requirio_ocr": True, "error": None}
    except Exception as e:
        return {"texto": "", "num_paginas": 0, "requirio_ocr": True,
                "error": f"Error en OCR: {e}"}
def limpiar_texto(texto: str) -> str:
    """
    Limpia el texto extraído de un PDF.
    Quita: headers/footers repetidos, números de página sueltos,
    watermarks comunes, espaciado raro, caracteres especiales.
    """
    if not texto:
        return ""

    # 1. Quitar watermarks típicos de códigos con copyright
    watermarks = [
        r"PROPERTY OF ICC\s*[—\-]\s*DO NOT REPRODUCE",
        r"COPYRIGHTED MATERIAL\s*\u2014\s*DO NOT DISTRIBUTE",
        r"Licensed to:.*?\n",
        r"\u00a9 \d{4} (ICC|NFPA|AIA|ADA).*?\n",
        r"For preview only\.?",
        r"Single user license.*?\n",
    ]
    for patron in watermarks:
        texto = re.sub(patron, " ", texto, flags=re.IGNORECASE)

    # 2. Normalizar espaciado
    texto = re.sub(r"[ \t]+", " ", texto)          # múltiples espacios → uno
    texto = re.sub(r"\n\s*\n\s*\n+", "\n\n", texto)  # múltiples saltos → doble

    # 3. Quitar números de página sueltos (línea con solo dígitos)
    texto = re.sub(r"^\s*\d{1,4}\s*$", "", texto, flags=re.MULTILINE)

    # 4. Reparar palabras cortadas por salto de línea (común en PDFs)
    # Ejemplo: "build-\ning" → "building"
    texto = re.sub(r"(\w+)-\n(\w+)", r"\1\2", texto)

    # 5. Quitar líneas extremadamente cortas (basura) en el medio del texto
    lineas = texto.split("\n")
    lineas_limpias = [
        l.strip() for l in lineas
        if len(l.strip()) > 3 or l.strip() == ""
    ]
    texto = "\n".join(lineas_limpias)

    # 6. Trim final
    return texto.strip()
def chunking_inteligente(
    texto: str,
    tamano_objetivo: int = 1000,
    overlap: int = 150,
) -> List[str]:
    """
    Divide el texto en chunks respetando límites naturales.
    Intenta cortar en saltos de sección, luego de párrafo, luego de oración.

    Args:
        texto: texto limpio.
        tamano_objetivo: caracteres por chunk (default 1000).
        overlap: caracteres de superposición entre chunks (default 150).

    Returns:
        Lista de strings (chunks).
    """
    if not texto or len(texto) < tamano_objetivo:
        return [texto] if texto else []

    chunks = []
    inicio = 0
    n = len(texto)

    while inicio < n:
        fin = min(inicio + tamano_objetivo, n)

        if fin < n:
            # Intentar cortar en un límite natural en orden de preferencia:
            # 1) salto doble (sección/párrafo)
            # 2) salto simple
            # 3) punto + espacio (fin de oración)
            # 4) espacio en blanco
            ventana = texto[inicio:fin]
            corte = -1
            for separador in ["\n\n", "\n", ". ", " "]:
                pos = ventana.rfind(separador)
                if pos > tamano_objetivo * 0.5:  # no cortes demasiado temprano
                    corte = pos + len(separador)
                    break
            if corte != -1:
                fin = inicio + corte

        chunk = texto[inicio:fin].strip()
        if chunk:
            chunks.append(chunk)

        # Avanzar con overlap
        if fin >= n:
            break
        inicio = max(inicio + 1, fin - overlap)

    return chunks
def procesar_pdf_completo(
    ruta_pdf: str,
    tamano_chunk: int = 1000,
    overlap: int = 150,
) -> Dict:
    """
    Procesa un PDF completo y devuelve chunks listos para ChromaDB.

    Returns:
        Dict con keys: chunks (lista), num_paginas, num_chunks,
                       requirio_ocr, error (None si todo bien).
    """
    print(f"📄 Procesando: {os.path.basename(ruta_pdf)}")

    # 1. Extraer texto
    resultado = extraer_texto_pdf(ruta_pdf)

    # 2. Si requiere OCR, intentar con OCR
    if resultado["requirio_ocr"] and OCR_DISPONIBLE:
        print("   Texto vacío. Intentando OCR...")
        resultado = extraer_texto_pdf_ocr(ruta_pdf)

    if resultado.get("error") or not resultado.get("texto"):
        return {
            "chunks": [],
            "num_paginas": resultado.get("num_paginas", 0),
            "num_chunks": 0,
            "requirio_ocr": resultado.get("requirio_ocr", False),
            "error": resultado.get("error", "Sin texto extraído."),
        }

    # 3. Limpiar
    texto_limpio = limpiar_texto(resultado["texto"])

    # 4. Chunking
    chunks = chunking_inteligente(texto_limpio, tamano_chunk, overlap)

    print(f"   ✅ {resultado['num_paginas']} páginas → {len(chunks)} chunks")

    return {
        "chunks": chunks,
        "num_paginas": resultado["num_paginas"],
        "num_chunks": len(chunks),
        "requirio_ocr": resultado["requirio_ocr"],
        "error": None,
    }
