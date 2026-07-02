# data_files.py
# -------------------------------------------------------------------
# Builder genérico de archivos de datos para solicitudes internas
# ("X File (Excel needed)"). NO es específico de "Best Buy": arma un
# Excel limpio y profesional a partir de una tabla que el agente
# estructura (título, encabezados, filas) con los datos que Richard
# provee en el correo o sus adjuntos (Opción A). El builder NO inventa
# datos: solo formatea lo que recibe.
#
# API:
#   generar_xlsx_tabla(spec, output_path) -> str
#
# spec = {
#   "title":      "Best Buy — Route Assignments",   # opcional (título en la hoja)
#   "sheet_name": "Routes",                          # opcional
#   "headers":    ["Store #", "Address", "Crew", "Date", "Status"],
#   "rows":       [ ["1234", "...", "Crew A", "2026-07-05", "Assigned"], ... ],
# }
# -------------------------------------------------------------------

NAVY_HEX = "1F3A5F"
LIGHT_HEX = "EEF2F7"
DARK_HEX = "222222"


def generar_xlsx_tabla(spec: dict, output_path: str) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.properties import PageSetupProperties

    spec = spec or {}
    headers = [str(h) for h in (spec.get("headers") or [])]
    rows = spec.get("rows") or []
    title = str(spec.get("title") or "").strip()
    sheet_name = (str(spec.get("sheet_name") or "Sheet1").strip() or "Sheet1")[:31]

    # Si no hay encabezados pero sí filas, derivar encabezados genéricos.
    if not headers and rows:
        ncols = max((len(r) for r in rows if isinstance(r, (list, tuple))), default=1)
        headers = [f"Column {i+1}" for i in range(ncols)]
    ncols = max(len(headers), 1)

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    navy_fill = PatternFill("solid", fgColor=NAVY_HEX)
    light_fill = PatternFill("solid", fgColor=LIGHT_HEX)
    white_bold = Font(bold=True, color="FFFFFF", size=10)
    dark = Font(color=DARK_HEX, size=10)
    thin = Side(style="thin", color="CCD4DE")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    left = Alignment(horizontal="left", vertical="top", wrap_text=True)

    r = 1
    # Título opcional (fila combinada arriba de la tabla).
    if title:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
        c = ws.cell(row=r, column=1, value=title)
        c.font = Font(bold=True, color=NAVY_HEX, size=13)
        r += 2

    # Encabezados.
    for j, h in enumerate(headers, start=1):
        cell = ws.cell(row=r, column=j, value=h)
        cell.fill = navy_fill
        cell.font = white_bold
        cell.border = border
        cell.alignment = left
    header_row = r
    r += 1

    # Filas de datos. Normaliza cada fila a la longitud de headers.
    for idx, fila in enumerate(rows, start=1):
        if not isinstance(fila, (list, tuple)):
            fila = [fila]
        valores = list(fila)[:ncols] + [""] * (ncols - len(fila))
        for j, v in enumerate(valores, start=1):
            cell = ws.cell(row=r, column=j, value=("" if v is None else str(v)))
            cell.font = dark
            cell.border = border
            cell.alignment = left
            if idx % 2 == 0:
                cell.fill = light_fill
        r += 1

    # Ancho de columnas aproximado por contenido (con topes).
    for j in range(1, ncols + 1):
        largo = len(str(headers[j - 1])) if j - 1 < len(headers) else 8
        for fila in rows:
            if isinstance(fila, (list, tuple)) and j - 1 < len(fila):
                largo = max(largo, len(str(fila[j - 1])))
        ws.column_dimensions[get_column_letter(j)].width = max(10, min(largo + 3, 48))

    ws.sheet_view.showGridLines = False
    if rows:
        ws.freeze_panes = f"A{header_row + 1}"
    ws.auto_filter.ref = (
        f"A{header_row}:{get_column_letter(ncols)}{header_row + len(rows)}"
    )
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)

    wb.save(output_path)
    return output_path


if __name__ == "__main__":
    demo = {
        "title": "Best Buy — Route Assignments",
        "sheet_name": "Routes",
        "headers": ["Store #", "Address", "City/State", "Crew", "Date", "Status"],
        "rows": [
            ["0421", "500 Retail Row", "Dallas, TX", "Crew A", "2026-07-06", "Assigned"],
            ["0533", "88 Mall Blvd", "Plano, TX", "Crew B", "2026-07-06", "Assigned"],
            ["0619", "12 Center Dr", "Frisco, TX", "Crew A", "2026-07-07", "Pending access"],
        ],
    }
    print("XLSX:", generar_xlsx_tabla(demo, "BestBuy_Routes_sample.xlsx"))
