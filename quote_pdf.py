# quote_pdf.py
# -------------------------------------------------------------------
# Renderizador de PDF profesional para las cotizaciones de JRS.
#
# Una sola funcion publica:
#     generar_pdf_cotizacion(quote_data, output_path, logo_path=None) -> str
#
# Recibe los datos de la cotizacion como un diccionario ESTRUCTURADO
# (no texto suelto) y los pinta en una plantilla con encabezado de marca,
# tabla de partidas con estilo y las 10 secciones del Documento de
# estimacion. Devuelve la ruta del PDF generado.
#
# El renderizador NO hace matematicas: los precios llegan ya formateados
# como strings (ej. "$21,000"). Asi el numero que ve el cliente es
# exactamente el que calculo el agente, sin riesgo de redondeos raros.
#
# ESQUEMA DE quote_data (todas las claves son opcionales salvo las del
# encabezado; las secciones vacias simplemente no se dibujan):
# {
#   "quote_number": "JRS-LC-2026-0629",
#   "date": "June 29, 2026",
#   "prepared_for": "LensCrafters",
#   "project_name": "LensCrafters Clinic Remodel (Labor Only)",
#   "store_number": "TBD",
#   "location": "San Bernardino, CA",
#   "prepared_by": "Richard Bodington / JRS Retail Services",
#   "phone": "832-361-6551",
#   "project_summary": "Labor-only remodel of ...",        # parrafo(s)
#   "scope_items": ["Light interior demo ...", ...],        # vinetas
#   "line_items": [
#       {"description": "...", "qty": "6,000", "unit": "SF",
#        "unit_price": "$3.50", "line_total": "$21,000"}, ...
#   ],
#   "labor_subtotal": "$99,375",
#   "travel_items": [{"description": "...", "amount": "$1,250"}, ...],
#   "travel_subtotal": "$10,326",
#   "total_text": "Approximately $105,000 - $122,000",
#   "assumptions": [...],
#   "exclusions": [...],
#   "clarifications": [...],
#   "terms": [...],
#   "compliance_note": "Any altered accessible route ...",  # opcional
# }
# -------------------------------------------------------------------

import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, HRFlowable, KeepTogether,
)

# ---- Paleta de marca JRS ----
NAVY = colors.HexColor("#1F3A5F")      # azul corporativo (encabezados)
GOLD = colors.HexColor("#C8922A")      # dorado del logo (acentos)
LIGHT = colors.HexColor("#EEF2F7")     # gris-azul muy claro (filas)
DARK = colors.HexColor("#222222")      # texto principal
MUTED = colors.HexColor("#666666")     # texto secundario


def _estilos():
    base = getSampleStyleSheet()
    estilos = {}
    estilos["company"] = ParagraphStyle(
        "company", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=18, textColor=NAVY, leading=20,
    )
    estilos["tagline"] = ParagraphStyle(
        "tagline", parent=base["Normal"], fontName="Helvetica",
        fontSize=8.5, textColor=MUTED, leading=11,
    )
    estilos["quotemeta"] = ParagraphStyle(
        "quotemeta", parent=base["Normal"], fontName="Helvetica",
        fontSize=9, textColor=DARK, leading=13, alignment=TA_RIGHT,
    )
    estilos["h2"] = ParagraphStyle(
        "h2", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=11, textColor=colors.white, leading=14,
        backColor=NAVY, borderPadding=(4, 6, 4, 6), spaceBefore=12,
        spaceAfter=6,
    )
    estilos["body"] = ParagraphStyle(
        "body", parent=base["Normal"], fontName="Helvetica",
        fontSize=9.5, textColor=DARK, leading=13,
    )
    estilos["bullet"] = ParagraphStyle(
        "bullet", parent=base["Normal"], fontName="Helvetica",
        fontSize=9.5, textColor=DARK, leading=13,
        leftIndent=12, bulletIndent=2,
    )
    estilos["meta_label"] = ParagraphStyle(
        "meta_label", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=9, textColor=NAVY, leading=13,
    )
    estilos["meta_val"] = ParagraphStyle(
        "meta_val", parent=base["Normal"], fontName="Helvetica",
        fontSize=9, textColor=DARK, leading=13,
    )
    estilos["total"] = ParagraphStyle(
        "total", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=12, textColor=NAVY, leading=15,
    )
    estilos["note"] = ParagraphStyle(
        "note", parent=base["Normal"], fontName="Helvetica-Oblique",
        fontSize=8, textColor=MUTED, leading=11,
    )
    estilos["cellL"] = ParagraphStyle(
        "cellL", parent=base["Normal"], fontName="Helvetica",
        fontSize=8.5, textColor=DARK, leading=11,
    )
    estilos["cellR"] = ParagraphStyle(
        "cellR", parent=base["Normal"], fontName="Helvetica",
        fontSize=8.5, textColor=DARK, leading=11, alignment=TA_RIGHT,
    )
    estilos["cellHdr"] = ParagraphStyle(
        "cellHdr", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=8.5, textColor=colors.white, leading=11,
    )
    estilos["cellHdrR"] = ParagraphStyle(
        "cellHdrR", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=8.5, textColor=colors.white, leading=11, alignment=TA_RIGHT,
    )
    return estilos


def _encabezado(quote_data, est, logo_path):
    """Banda superior: logo + nombre de empresa a la izquierda, numero
    y fecha de cotizacion a la derecha."""
    izquierda = []
    if logo_path and os.path.exists(logo_path):
        try:
            img = Image(logo_path, width=1.4 * inch, height=0.7 * inch)
            img.hAlign = "LEFT"
            izquierda.append(img)
        except Exception:
            izquierda.append(Paragraph("JRS RETAIL SERVICES", est["company"]))
    else:
        izquierda.append(Paragraph("JRS RETAIL SERVICES", est["company"]))
    izquierda.append(Paragraph(
        "Commercial Retail Construction / Retail Remodel Subcontractor",
        est["tagline"]))

    derecha = Paragraph(
        f"<b>QUOTE</b><br/>"
        f"# {quote_data.get('quote_number', 'TBD')}<br/>"
        f"{quote_data.get('date', '')}",
        est["quotemeta"])

    tabla = Table([[izquierda, derecha]], colWidths=[4.2 * inch, 2.8 * inch])
    tabla.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return tabla


def _bloque_meta(quote_data, est):
    """Bloque 'Prepared for / Project / Location / Prepared by'."""
    filas = [
        ("PREPARED FOR", quote_data.get("prepared_for", "")),
        ("PROJECT", quote_data.get("project_name", "")),
        ("STORE #", quote_data.get("store_number", "")),
        ("LOCATION", quote_data.get("location", "")),
        ("PREPARED BY", quote_data.get("prepared_by", "")),
        ("PHONE", quote_data.get("phone", "")),
    ]
    datos = [
        [Paragraph(lbl, est["meta_label"]), Paragraph(str(val), est["meta_val"])]
        for lbl, val in filas if str(val).strip()
    ]
    tabla = Table(datos, colWidths=[1.3 * inch, 5.7 * inch])
    tabla.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return tabla


def _seccion(titulo, est):
    return Paragraph(titulo, est["h2"])


def _vinetas(items, est):
    flow = []
    for it in items:
        flow.append(Paragraph(str(it), est["bullet"], bulletText="•"))
    return flow


def _tabla_partidas(line_items, est):
    """Tabla de ESTIMATE BREAKDOWN con encabezado sombreado y filas
    alternadas. Numera las lineas automaticamente."""
    encabezados = [
        Paragraph("#", est["cellHdr"]),
        Paragraph("DESCRIPTION", est["cellHdr"]),
        Paragraph("QTY", est["cellHdrR"]),
        Paragraph("UNIT", est["cellHdr"]),
        Paragraph("UNIT PRICE", est["cellHdrR"]),
        Paragraph("LINE TOTAL", est["cellHdrR"]),
    ]
    filas = [encabezados]
    for i, li in enumerate(line_items, start=1):
        filas.append([
            Paragraph(str(i), est["cellL"]),
            Paragraph(str(li.get("description", "")), est["cellL"]),
            Paragraph(str(li.get("qty", "")), est["cellR"]),
            Paragraph(str(li.get("unit", "")), est["cellL"]),
            Paragraph(str(li.get("unit_price", "")), est["cellR"]),
            Paragraph(str(li.get("line_total", "")), est["cellR"]),
        ])

    tabla = Table(
        filas,
        colWidths=[0.32 * inch, 3.0 * inch, 0.7 * inch, 0.55 * inch,
                   0.9 * inch, 1.0 * inch],
        repeatRows=1,
    )
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, NAVY),
        ("GRID", (0, 1), (-1, -1), 0.25, colors.HexColor("#CCD4DE")),
    ]
    # Filas alternadas (zebra) a partir de la fila 1 de datos
    for r in range(1, len(filas)):
        if r % 2 == 1:
            estilo.append(("BACKGROUND", (0, r), (-1, r), LIGHT))
    tabla.setStyle(TableStyle(estilo))
    return tabla


def _tabla_totales(quote_data, est):
    """Subtotales + total final destacado."""
    filas = []
    if quote_data.get("labor_subtotal"):
        filas.append(["Labor subtotal", quote_data["labor_subtotal"]])
    if quote_data.get("travel_subtotal"):
        filas.append(["Travel / lodging / equipment", quote_data["travel_subtotal"]])

    datos = [
        [Paragraph(lbl, est["body"]),
         Paragraph(str(val), ParagraphStyle("r", parent=est["body"], alignment=TA_RIGHT))]
        for lbl, val in filas
    ]
    bloque = []
    if datos:
        t = Table(datos, colWidths=[5.0 * inch, 2.0 * inch])
        t.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.HexColor("#CCD4DE")),
        ]))
        bloque.append(t)

    if quote_data.get("total_text"):
        bloque.append(Spacer(1, 6))
        caja = Table(
            [[Paragraph("BUDGETARY LABOR-ONLY TOTAL", est["meta_label"]),
              Paragraph(str(quote_data["total_text"]),
                        ParagraphStyle("tot", parent=est["total"], alignment=TA_RIGHT))]],
            colWidths=[3.5 * inch, 3.5 * inch])
        caja.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
            ("BOX", (0, 0), (-1, -1), 1, GOLD),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        bloque.append(caja)
    return bloque


def _pie(canvas, doc):
    """Pie de pagina con numero de pagina y nota de confidencialidad."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(
        0.75 * inch, 0.5 * inch,
        "JRS Retail Services  |  Labor-Only Subcontractor Quote  |  Confidential")
    canvas.drawRightString(
        7.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.setStrokeColor(colors.HexColor("#CCD4DE"))
    canvas.line(0.75 * inch, 0.65 * inch, 7.75 * inch, 0.65 * inch)
    canvas.restoreState()


def generar_pdf_cotizacion(quote_data: dict, output_path: str,
                           logo_path: str = None) -> str:
    """Genera el PDF de la cotizacion y devuelve la ruta del archivo."""
    est = _estilos()
    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.7 * inch, bottomMargin=0.85 * inch,
        title=f"JRS Quote {quote_data.get('quote_number', '')}",
        author="JRS Retail Services",
    )

    flow = []
    # --- Encabezado de marca ---
    flow.append(_encabezado(quote_data, est, logo_path))
    flow.append(Spacer(1, 4))
    flow.append(HRFlowable(width="100%", thickness=2, color=GOLD,
                           spaceBefore=2, spaceAfter=8))

    # --- Bloque de metadatos ---
    flow.append(_bloque_meta(quote_data, est))
    flow.append(Spacer(1, 4))

    # --- 1. Project Summary ---
    if quote_data.get("project_summary"):
        flow.append(_seccion("1. PROJECT SUMMARY", est))
        for parrafo in str(quote_data["project_summary"]).split("\n"):
            if parrafo.strip():
                flow.append(Paragraph(parrafo.strip(), est["body"]))

    # --- 2. Scope of Work Included ---
    if quote_data.get("scope_items"):
        flow.append(_seccion("2. SCOPE OF WORK INCLUDED (LABOR ONLY)", est))
        flow.extend(_vinetas(quote_data["scope_items"], est))

    # --- 3. Estimate Breakdown ---
    if quote_data.get("line_items"):
        flow.append(_seccion("3. ESTIMATE BREAKDOWN (LABOR-ONLY SELL RATES)", est))
        flow.append(_tabla_partidas(quote_data["line_items"], est))

    # --- 4. Travel / Lodging / Equipment ---
    if quote_data.get("travel_items"):
        flow.append(_seccion("4. TRAVEL / LODGING / EQUIPMENT (ALLOWANCES)", est))
        datos = [[Paragraph(str(t.get("description", "")), est["cellL"]),
                  Paragraph(str(t.get("amount", "")), est["cellR"])]
                 for t in quote_data["travel_items"]]
        t = Table(datos, colWidths=[6.0 * inch, 1.0 * inch])
        t.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        flow.append(t)

    # --- 5. Total Price ---
    flow.append(_seccion("5. TOTAL PRICE", est))
    flow.extend(_tabla_totales(quote_data, est))

    # --- 6. Assumptions ---
    if quote_data.get("assumptions"):
        flow.append(_seccion("6. ASSUMPTIONS", est))
        flow.extend(_vinetas(quote_data["assumptions"], est))

    # --- 7. Exclusions ---
    if quote_data.get("exclusions"):
        flow.append(_seccion("7. EXCLUSIONS", est))
        flow.extend(_vinetas(quote_data["exclusions"], est))

    # --- 8. Clarifications / Open Items ---
    if quote_data.get("clarifications"):
        flow.append(_seccion("8. CLARIFICATIONS / OPEN ITEMS", est))
        flow.extend(_vinetas(quote_data["clarifications"], est))

    # --- 9. Terms ---
    if quote_data.get("terms"):
        flow.append(_seccion("9. TERMS", est))
        flow.extend(_vinetas(quote_data["terms"], est))

    # --- 10. Authorization ---
    flow.append(_seccion("10. AUTHORIZATION", est))
    auth = Table([
        [Paragraph("Accepted by:", est["body"]), Paragraph("_________________________", est["body"])],
        [Paragraph("Name / Title:", est["body"]), Paragraph("_________________________", est["body"])],
        [Paragraph("Date:", est["body"]), Paragraph("_________________________", est["body"])],
    ], colWidths=[1.3 * inch, 5.7 * inch])
    auth.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    flow.append(auth)

    # --- Nota de compliance (opcional) ---
    if quote_data.get("compliance_note"):
        flow.append(Spacer(1, 8))
        flow.append(HRFlowable(width="100%", thickness=0.5,
                               color=colors.HexColor("#CCD4DE")))
        flow.append(Spacer(1, 4))
        flow.append(Paragraph("COMPLIANCE NOTE: " + str(quote_data["compliance_note"]),
                              est["note"]))

    doc.build(flow, onFirstPage=_pie, onLaterPages=_pie)
    return output_path


# -------------------------------------------------------------------
# Prueba de aislamiento: corre este archivo directo para generar un
# PDF de muestra con los numeros reales de la cotizacion de LensCrafters.
#     python quote_pdf.py
# -------------------------------------------------------------------
if __name__ == "__main__":
    ejemplo = {
        "quote_number": "JRS-LC-2026-0629",
        "date": "June 29, 2026",
        "prepared_for": "LensCrafters",
        "project_name": "LensCrafters Clinic Remodel (Labor Only)",
        "store_number": "0290",
        "location": "San Bernardino, CA",
        "prepared_by": "Richard Bodington / JRS Retail Services",
        "phone": "832-361-6551",
        "project_summary": (
            "Labor-only remodel of an approximately 6,000 SF LensCrafters clinic "
            "(back room ~1,000 SF; sales, offices and remaining areas ~5,000 SF). "
            "JRS provides labor, equipment, travel and lodging only; all materials, "
            "fixtures, ceiling tile, flooring and paint are furnished by others.\n"
            "Basis: standard 10-hour production shifts; medical-retail / occupied-store "
            "conditions with night work for customer-facing areas (premium applied); "
            "4-person crew (incl. lead) over an estimated 7-9 shifts."
        ),
        "scope_items": [
            "Light interior demo and prep across clinic (~6,000 SF), debris consolidated to one point.",
            "Wallcovering removal where applicable, then skim coat, sand and paint prep (no painting over wallcovering).",
            "Patch, prime and two-coat retail paint of walls in sales, offices and back room.",
            "Ceiling tile replacement labor; tiles to match existing exactly (tiles by others).",
            "Flooring installation labor (LVT/resilient or carpet tile, client material), incl. floor prep/adhesive scrape; flooring under cabinets where possible.",
            "Fixture / millwork install and remove-and-reset labor as directed.",
            "Final detailed clean, dust control throughout, and punchlist completion to client punchlist angles.",
        ],
        "line_items": [
            {"description": "Interior demo & prep, occupied store", "qty": "6,000", "unit": "SF", "unit_price": "$3.50", "line_total": "$21,000"},
            {"description": "Wallcovering removal + skim/sand prep", "qty": "2,500", "unit": "SF", "unit_price": "$3.25", "line_total": "$8,125"},
            {"description": "Patch + two-coat retail paint, walls", "qty": "9,000", "unit": "SF", "unit_price": "$1.75", "line_total": "$15,750"},
            {"description": "Ceiling tile replacement (labor)", "qty": "6,000", "unit": "SF", "unit_price": "$1.75", "line_total": "$10,500"},
            {"description": "Floor prep / adhesive scrape", "qty": "6,000", "unit": "SF", "unit_price": "$1.50", "line_total": "$9,000"},
            {"description": "LVT/resilient flooring install (labor)", "qty": "6,000", "unit": "SF", "unit_price": "$4.00", "line_total": "$24,000"},
            {"description": "Fixture/millwork R&R (allowance)", "qty": "1", "unit": "LS", "unit_price": "$6,500", "line_total": "$6,500"},
            {"description": "Final clean + punchlist (allowance)", "qty": "1", "unit": "LS", "unit_price": "$4,500", "line_total": "$4,500"},
        ],
        "labor_subtotal": "$99,375",
        "travel_items": [
            {"description": "Out-of-town mobilization (allowance)", "amount": "$1,250"},
            {"description": "Lodging allowance (4 rooms x ~8 nights @ $110+tax)", "amount": "$4,400"},
            {"description": "Per diem / M&IE (4 workers x ~8 days @ $68)", "amount": "$2,176"},
            {"description": "Scissor lift allowance (~8 days @ $250)", "amount": "$2,000"},
            {"description": "Lift delivery/pickup allowance", "amount": "$500"},
        ],
        "travel_subtotal": "$10,326",
        "total_text": "Approximately $105,000 - $122,000",
        "assumptions": [
            "Labor only; 10-hour production shifts.",
            "All materials, fixtures, ceiling tile, flooring and paint furnished by client/GC unless listed.",
            "Quantities based on the ~6,000 SF breakdown provided; not yet field-verified.",
            "Site access provided during scheduled hours; merchandise and sensitive clinic/OD equipment moved/protected by store.",
            "Debris consolidated by JRS; haul-off/dumpster by others unless listed.",
            "Medical-retail protocol assumed (dust control, exact ceiling tile match, no painting over wallcovering, punchlist-angle photos).",
        ],
        "exclusions": [
            "All materials unless specifically listed.",
            "Permits, taxes (unless required), engineering and design.",
            "Dumpster / haul-off unless listed.",
            "Licensed electrical, plumbing, HVAC, fire alarm, sprinkler and low-voltage work.",
            "Disconnection/reconnection of OD or clinic equipment (requires authorized OD tech).",
            "Merchandise moving, hazmat, asbestos/mold/lead/environmental abatement.",
            "Structural modifications, unforeseen/hidden conditions, repairs to existing damage unless listed.",
            "After-hours mall/security fees unless listed; extra mobilizations by others; work outside listed scope.",
        ],
        "clarifications": [
            "Confirm store number and project location/state (affects regional pricing, travel, code/ADA verification).",
            "Confirm occupied vs. vacant and required work hours (night work).",
            "Confirm flooring type and whether floor prep/scrape is required.",
            "Confirm fixture/millwork count for Line 7.",
            "Confirm dumpster/haul-off and debris responsibility.",
            "Confirm whether OD/clinic equipment disconnection is required.",
        ],
        "terms": [
            "Quote valid 15 days from date above.",
            "Work outside the listed scope handled via change order.",
            "Schedule subject to crew availability and site readiness; delays caused by others may add charges.",
            "Payment terms: per subcontract agreement.",
        ],
        "compliance_note": (
            "Any altered accessible route or clearances should be verified against ADA 2010 "
            "Standards. The exact ADA section must be verified manually against the official "
            "text and local code adoption once the project location is confirmed."
        ),
    }

    salida = generar_pdf_cotizacion(ejemplo, "JRS_Quote_sample.pdf")
    print(f"PDF generado: {salida}")
