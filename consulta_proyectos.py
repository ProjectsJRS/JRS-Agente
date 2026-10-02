"""
consulta_proyectos.py — Etapa 3: consulta de reportes por proyecto
==================================================================
Modulo STANDALONE (no toca agent.py ni tools.py todavia).

Reparto de trabajo:
  - Joe (el modelo) interpreta el lenguaje libre ("lo del 29-09 de Carmel",
    "ayer en Macy's") y lo convierte en parametros: codigo, nombre, fechas.
  - Este modulo RESUELVE el proyecto contra el catalogo real de JRS OPS
    (determinístico) y BUSCA los reportes en ChromaDB.

resolver_proyecto() devuelve uno de estos estados:
    RESUELTO       -> un solo proyecto identificado
    AMBIGUO        -> el nombre coincide con varios proyectos (Joe pregunta)
    CONFLICTO      -> el codigo y el nombre apuntan a proyectos distintos
    NO_ENCONTRADO  -> ni codigo ni nombre coinciden (con sugerencias)
    NO_VERIFICADO  -> JRS OPS no respondio (se busca solo por texto)

consultar_proyecto() agrega:
    NO_REGISTRADO  -> el NOMBRE no esta en JRS OPS (proyecto anterior al
                      sistema), pero si hay reportes en el historial por texto.
                      Joe debe aclararlo al responder.
Un CODIGO inexistente nunca se "adivina" por texto: se devuelve NO_ENCONTRADO.

Fechas: el campo `date` de la historia es la fecha en que Joe PROCESO el
correo, no el dia de trabajo. Un reporte del 28 enviado de noche queda con
fecha 29. Por eso, al pedir un dia D, se incluyen D y D+1, marcando cual es.

Uso desde la consola (local o Railway):
    python consulta_proyectos.py                         -> autotests
    python consulta_proyectos.py --resolver "best buy carmel"
    python consulta_proyectos.py --consultar 20260910-01 2026-09-29
"""

import os
import re
import sys
import json
import difflib
import logging
import unicodedata
from datetime import date, datetime, timedelta

from codigos_proyecto import (
    obtener_catalogo,
    normalizar_codigo,
    CatalogoNoDisponible,
)

log = logging.getLogger("consulta_proyectos")

RESUELTO = "RESUELTO"
AMBIGUO = "AMBIGUO"
CONFLICTO = "CONFLICTO"
NO_ENCONTRADO = "NO_ENCONTRADO"
NO_VERIFICADO = "NO_VERIFICADO"
NO_REGISTRADO = "NO_REGISTRADO"   # el nombre no esta en JRS OPS, pero hay historial

COLECCION_HISTORIA = "collection_jrs_history"
MAX_CHARS_REPORTE = 3500      # protege el contexto de Joe
LIMITE_POR_DEFECTO = 5
UMBRAL_NOMBRE = 0.6           # fraccion minima de palabras que deben coincidir

# Abreviaturas que el equipo usa al hablar. Se expanden antes de comparar.
ALIAS = {
    "bb": "best buy",
    "bestbuy": "best buy",
    "tjmaxx": "tj maxx",
    "tj": "tj",
    "macys": "macy s",
    "hyvee": "hy vee",
}

# Palabras que no ayudan a distinguir un proyecto de otro.
_RELLENO = {"de", "del", "la", "el", "en", "the", "of", "at", "project", "proyecto",
            "store", "tienda", "reporte", "report", "#", "y", "and"}

# Abreviaturas de estados de EE. UU. que aparecen en los nombres.
_ESTADOS_US = {"al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
               "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
               "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
               "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
               "wi", "wy"}


# ---------------------------------------------------------------------------
# Normalizacion de nombres
# ---------------------------------------------------------------------------
def _sin_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto or "")
                   if not unicodedata.combining(c))


def tokens_nombre(texto, quitar_estados=False):
    """'BEST BUY #490 CARMEL, IN' -> ['best', 'buy', '490', 'carmel', 'in']"""
    t = _sin_acentos(texto).lower().replace("'", " ").replace("’", " ")
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    crudos = t.split()
    expandidos = []
    for tok in crudos:
        expandidos.extend(ALIAS.get(tok, tok).split())
    salida = [x for x in expandidos if x not in _RELLENO]
    if quitar_estados:
        salida = [x for x in salida if x not in _ESTADOS_US]
    return salida


def _coincide_token(tok, candidatos):
    """Coincidencia exacta, por prefijo (>=4 letras) o con error de tipeo."""
    if tok in candidatos:
        return True
    for c in candidatos:
        if len(tok) >= 4 and (c.startswith(tok) or tok.startswith(c)) and len(c) >= 4:
            return True
        if not tok.isdigit() and len(tok) >= 5 and \
                difflib.SequenceMatcher(None, tok, c).ratio() >= 0.8:
            return True
    return False


def puntaje_nombre(consulta, nombre_proyecto):
    """Fraccion de palabras de la consulta presentes en el nombre del proyecto."""
    q = tokens_nombre(consulta, quitar_estados=True) or tokens_nombre(consulta)
    p = tokens_nombre(nombre_proyecto)
    if not q:
        return 0.0
    aciertos = sum(1 for tok in q if _coincide_token(tok, p))
    return aciertos / len(q)


# ---------------------------------------------------------------------------
# Resolucion del proyecto
# ---------------------------------------------------------------------------
def _publico(p):
    return {"code": p.get("code"), "name": p.get("name"),
            "status": p.get("status"), "id": p.get("id")}


def _por_nombre(nombre, catalogo):
    puntajes = sorted(
        ((puntaje_nombre(nombre, p["name"] or ""), p) for p in catalogo.values()),
        key=lambda x: x[0], reverse=True,
    )
    mejores = [p for s, p in puntajes if s >= UMBRAL_NOMBRE and s == puntajes[0][0]]
    cercanos = [p for s, p in puntajes if s >= UMBRAL_NOMBRE]
    return mejores, cercanos


def resolver_proyecto(codigo=None, nombre=None, _fetch=None):
    """Decide de forma deterministica a que proyecto se refiere la consulta."""
    res = {"estado": None, "proyecto": None, "candidatos": [], "nota": ""}
    codigo = normalizar_codigo(codigo) if codigo else ""
    nombre = (nombre or "").strip()

    if not codigo and not nombre:
        res.update(estado=NO_ENCONTRADO, nota="No project code or name was provided.")
        return res

    try:
        catalogo = obtener_catalogo(_fetch=_fetch)
    except CatalogoNoDisponible as e:
        res.update(estado=NO_VERIFICADO,
                   nota=f"JRS Operations System is not reachable ({e}). "
                        "Searching history by text only.")
        return res

    proy_codigo = catalogo.get(codigo) if codigo else None

    # 1) Codigo exacto
    if proy_codigo:
        if nombre and puntaje_nombre(nombre, proy_codigo["name"] or "") < 0.5:
            mejores, _ = _por_nombre(nombre, catalogo)
            otros = [p for p in mejores if p["code"] != proy_codigo["code"]]
            if otros:
                res.update(
                    estado=CONFLICTO, proyecto=_publico(proy_codigo),
                    candidatos=[_publico(p) for p in otros],
                    nota=(f"Code {proy_codigo['code']} belongs to '{proy_codigo['name']}', "
                          f"but the name '{nombre}' matches a different project. "
                          "Ask which one is meant before answering."))
                return res
        res.update(estado=RESUELTO, proyecto=_publico(proy_codigo))
        return res

    # 2) Codigo con error o sin codigo: intentar por nombre
    if nombre:
        mejores, cercanos = _por_nombre(nombre, catalogo)
        if len(mejores) == 1:
            nota = ""
            if codigo:
                nota = (f"Code {codigo} does not exist in JRS Operations System; "
                        f"the project was identified by name. Correct code: "
                        f"{mejores[0]['code']}.")
            res.update(estado=RESUELTO, proyecto=_publico(mejores[0]), nota=nota)
            return res
        if len(mejores) > 1:
            res.update(estado=AMBIGUO, candidatos=[_publico(p) for p in mejores],
                       nota=f"'{nombre}' matches {len(mejores)} projects. "
                            "List them and ask which one is meant.")
            return res

    # 3) Nada coincide: sugerencias
    sugeridos = []
    if codigo:
        for c in difflib.get_close_matches(codigo, list(catalogo.keys()), n=3, cutoff=0.75):
            sugeridos.append(_publico(catalogo[c]))
    res.update(estado=NO_ENCONTRADO, candidatos=sugeridos,
               nota="No project matches that code or name in JRS Operations System."
                    + (" Close codes are listed in 'candidatos'." if sugeridos else ""))
    return res


# ---------------------------------------------------------------------------
# Fechas
# ---------------------------------------------------------------------------
def _a_fecha(texto):
    if not texto:
        return None
    try:
        return datetime.strptime(str(texto)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _rango(fecha_desde, fecha_hasta):
    """Devuelve (desde, hasta, es_dia_unico). Un dia unico se amplia a D+1."""
    d = _a_fecha(fecha_desde)
    h = _a_fecha(fecha_hasta) or d
    if d and h and h < d:
        d, h = h, d
    if d and h and d == h:
        return d, d + timedelta(days=1), True
    return d, h, False


# ---------------------------------------------------------------------------
# ChromaDB
# ---------------------------------------------------------------------------
def obtener_coleccion():
    """Abre la coleccion de historia (solo para la consola; en produccion
    tools.py pasa la coleccion del cliente que ya tiene abierto)."""
    import chromadb
    ruta = os.environ.get("CHROMA_DB_PATH", "./chroma_db")
    cliente = chromadb.PersistentClient(path=ruta)
    try:
        from embeddings_config import EMBEDDING_FUNCTION
        return cliente.get_collection(COLECCION_HISTORIA, embedding_function=EMBEDDING_FUNCTION)
    except ImportError:
        return cliente.get_collection(COLECCION_HISTORIA)


def _empaquetar(doc, meta, origen, dia_pedido=None):
    texto = doc or ""
    recortado = len(texto) > MAX_CHARS_REPORTE
    fecha_reg = _a_fecha((meta or {}).get("date"))
    item = {
        "fecha_registro": fecha_reg.isoformat() if fecha_reg else (meta or {}).get("date", ""),
        "project_code": (meta or {}).get("project_code", ""),
        "project_name": (meta or {}).get("project_name", "") or (meta or {}).get("projects", ""),
        "code_status": (meta or {}).get("code_status", ""),
        "risk_level": (meta or {}).get("risk_level", ""),
        "doc_type": (meta or {}).get("doc_type", ""),
        "origen": origen,   # "codigo" (etiquetado) o "historico" (por texto, sin codigo)
        "texto": texto[:MAX_CHARS_REPORTE] + (" [...]" if recortado else ""),
    }
    if dia_pedido and fecha_reg:
        item["coincidencia"] = ("mismo_dia" if fecha_reg == dia_pedido
                                else "registrado_dia_siguiente")
    return item


def _reportes_etiquetados(coleccion, proyecto):
    condiciones = []
    if proyecto.get("id"):
        condiciones.append({"project_id": proyecto["id"]})
    if proyecto.get("code"):
        condiciones.append({"project_code": normalizar_codigo(proyecto["code"])})
        if proyecto["code"] != normalizar_codigo(proyecto["code"]):
            condiciones.append({"project_code": proyecto["code"]})
    if not condiciones:
        return []
    where = condiciones[0] if len(condiciones) == 1 else {"$or": condiciones}
    r = coleccion.get(where=where, include=["documents", "metadatas"])
    return list(zip(r.get("documents") or [], r.get("metadatas") or []))


def _reportes_historicos(coleccion, nombre, pregunta, n=30):
    """Reportes anteriores a los codigos: busqueda semantica por nombre y
    filtro de seguridad: el texto debe mencionar las palabras distintivas."""
    if not nombre:
        return []
    consulta = f"{nombre} {pregunta or ''}".strip()
    r = coleccion.query(query_texts=[consulta], n_results=n,
                        include=["documents", "metadatas"])
    docs = (r.get("documents") or [[]])[0]
    metas = (r.get("metadatas") or [[]])[0]
    claves = [t for t in tokens_nombre(nombre, quitar_estados=True)
              if t not in {"best", "buy", "tj", "maxx"} or len(tokens_nombre(nombre)) <= 2]
    salida = []
    for doc, meta in zip(docs, metas):
        if (meta or {}).get("project_code"):
            continue   # los etiquetados ya se buscaron por codigo
        texto_tokens = set(tokens_nombre(doc or ""))
        if claves and sum(1 for c in claves if _coincide_token(c, texto_tokens)) >= \
                max(1, len(claves) // 2):
            salida.append((doc, meta))
    return salida


# ---------------------------------------------------------------------------
# Consulta principal (la que usara el tool de Joe)
# ---------------------------------------------------------------------------
def consultar_proyecto(codigo=None, nombre=None, fecha_desde=None, fecha_hasta=None,
                       pregunta=None, limite=LIMITE_POR_DEFECTO,
                       _coleccion=None, _fetch=None):
    resolucion = resolver_proyecto(codigo=codigo, nombre=nombre, _fetch=_fetch)
    salida = {
        "resolucion": resolucion["estado"],
        "proyecto": resolucion["proyecto"],
        "candidatos": resolucion["candidatos"],
        "nota": resolucion["nota"],
        "reportes": [],
        "fechas_disponibles": [],
    }

    # Ambiguo / conflicto: Joe debe preguntar, no adivinar.
    if resolucion["estado"] in (AMBIGUO, CONFLICTO):
        return salida

    # No encontrado: solo se busca en el historial si se dio un NOMBRE.
    # Un codigo con error se queda en NO_ENCONTRADO (con sugerencias).
    if resolucion["estado"] == NO_ENCONTRADO:
        if not (nombre or "").strip():
            return salida
        coleccion = _coleccion or obtener_coleccion()
        pares = _reportes_historicos(coleccion, nombre, pregunta)
        if not pares:
            return salida
        desde, hasta, dia_unico = _rango(fecha_desde, fecha_hasta)
        todas = sorted({_a_fecha((m or {}).get("date")) for _, m in pares} - {None})
        filtrados = [(d, m) for d, m in pares
                     if not desde or ((f := _a_fecha((m or {}).get("date"))) and desde <= f <= hasta)]
        filtrados.sort(key=lambda x: (_a_fecha((x[1] or {}).get("date")) or date.min), reverse=True)
        salida["resolucion"] = NO_REGISTRADO
        salida["reportes"] = [
            _empaquetar(d, m, "historico", dia_pedido=desde if dia_unico else None)
            for d, m in filtrados[:max(1, int(limite or LIMITE_POR_DEFECTO))]
        ]
        salida["nota"] = (
            f"'{nombre}' is NOT registered in JRS Operations System (likely a project "
            "from before the system). These results come from project history by text "
            "match: tell the user the project is not registered and that the data comes "
            "from history.")
        if desde and not salida["reportes"]:
            antes = [f for f in todas if f < desde][-3:]
            despues = [f for f in todas if f > hasta][:3]
            salida["fechas_disponibles"] = [f.isoformat() for f in antes + despues]
            salida["nota"] += (" No report in the requested dates; 'fechas_disponibles' "
                               "lists the closest dates with reports.")
        return salida

    coleccion = _coleccion or obtener_coleccion()
    proyecto = resolucion["proyecto"] or {}
    nombre_busqueda = proyecto.get("name") or nombre or ""

    pares = []
    if proyecto:
        pares += [(d, m, "codigo") for d, m in _reportes_etiquetados(coleccion, proyecto)]
    pares += [(d, m, "historico")
              for d, m in _reportes_historicos(coleccion, nombre_busqueda, pregunta)]

    # Deduplicar por email_id / texto
    vistos, unicos = set(), []
    for d, m, o in pares:
        clave = (m or {}).get("email_id") or (d or "")[:200]
        if clave not in vistos:
            vistos.add(clave)
            unicos.append((d, m, o))

    todas = sorted({_a_fecha((m or {}).get("date")) for _, m, _ in unicos} - {None})
    desde, hasta, dia_unico = _rango(fecha_desde, fecha_hasta)

    if desde:
        filtrados = [(d, m, o) for d, m, o in unicos
                     if (f := _a_fecha((m or {}).get("date"))) and desde <= f <= hasta]
    else:
        filtrados = unicos

    filtrados.sort(key=lambda x: (_a_fecha((x[1] or {}).get("date")) or date.min), reverse=True)
    salida["reportes"] = [
        _empaquetar(d, m, o, dia_pedido=desde if dia_unico else None)
        for d, m, o in filtrados[:max(1, int(limite or LIMITE_POR_DEFECTO))]
    ]

    if desde and not salida["reportes"]:
        # Fechas mas cercanas con reporte (3 antes y 3 despues)
        antes = [f for f in todas if f < desde][-3:]
        despues = [f for f in todas if f > hasta][:3]
        salida["fechas_disponibles"] = [f.isoformat() for f in antes + despues]
        salida["nota"] = (salida["nota"] + " " if salida["nota"] else "") + (
            "No report in the requested dates. 'fechas_disponibles' lists the closest "
            "dates that do have reports." if todas else
            "There are no reports stored for this project yet.")
    elif dia_unico and salida["reportes"]:
        salida["nota"] = (salida["nota"] + " " if salida["nota"] else "") + (
            "Stored dates are the day Joe PROCESSED the email. Reports marked "
            "'registrado_dia_siguiente' may describe the requested day: check the "
            "DATE inside the text.")
    elif not salida["reportes"]:
        salida["nota"] = (salida["nota"] + " " if salida["nota"] else "") + \
            "There are no reports stored for this project yet."
    return salida


# ---------------------------------------------------------------------------
# Autotests
# ---------------------------------------------------------------------------
_CATALOGO_REAL = [
    {"id": "u1", "code": "09082026-1", "name": "BEST BUY #230  GREENWOOD, IN", "status": "active"},
    {"id": "u2", "code": "20260831-1", "name": "MARSHALLS (CORINTH, MS)", "status": "paused"},
    {"id": "u3", "code": "20260904-1", "name": "TJ MAXX (MADISON AL)", "status": "finished"},
    {"id": "u4", "code": "20260904-2", "name": "TJ MAXX (TUPELO, MS)", "status": "finished"},
    {"id": "u5", "code": "20260905-1", "name": "PROJECT TEST", "status": "finished"},
    {"id": "u6", "code": "20260908-1", "name": "MACY'S (RICHMOND, VIRGINIA)", "status": "active"},
    {"id": "u7", "code": "20260908-2", "name": "BEST BUY #549 WATERFORD, CT", "status": "active"},
    {"id": "u8", "code": "20260910-01", "name": "BEST BUY #490 CARMEL, IN", "status": "active"},
    {"id": "u9", "code": "20260911-1", "name": "BEST BUY #360 WILLISTON, VT", "status": "active"},
]


class _ColeccionFalsa:
    """Imita get()/query() de ChromaDB con filtros simples y $or."""

    def __init__(self, filas):
        self.filas = filas   # lista de (doc, meta)

    @staticmethod
    def _cumple(meta, where):
        if not where:
            return True
        if "$or" in where:
            return any(_ColeccionFalsa._cumple(meta, w) for w in where["$or"])
        return all(meta.get(k) == v for k, v in where.items())

    def get(self, where=None, include=None):
        sel = [(d, m) for d, m in self.filas if self._cumple(m, where)]
        return {"documents": [d for d, _ in sel], "metadatas": [m for _, m in sel]}

    def query(self, query_texts, n_results=10, include=None):
        q = set(tokens_nombre(query_texts[0]))
        orden = sorted(self.filas, key=lambda f: -len(q & set(tokens_nombre(f[0]))))
        sel = orden[:n_results]
        return {"documents": [[d for d, _ in sel]], "metadatas": [[m for _, m in sel]]}


def _autotest():
    fetch_ok = lambda: _CATALOGO_REAL

    def fetch_falla():
        raise CatalogoNoDisponible("simulado")

    from codigos_proyecto import _reset_cache

    col = _ColeccionFalsa([
        ("DATE: 2026-09-28 Best Buy Carmel lock installed", {"date": "2026-09-29", "email_id": "e1",
         "project_code": "20260910-01", "project_id": "u8", "doc_type": "crew_update"}),
        ("DATE: 2026-09-29 Best Buy Carmel filler measured", {"date": "2026-09-29", "email_id": "e2",
         "project_code": "20260910-01", "project_id": "u8", "doc_type": "crew_update"}),
        ("DATE: 2026-09-25 Best Buy Carmel kickoff", {"date": "2026-09-25", "email_id": "e3",
         "project_code": "20260910-01", "project_id": "u8", "doc_type": "crew_update"}),
        ("Macy's Richmond Virginia fixtures delivered", {"date": "2026-09-29", "email_id": "e4",
         "project_code": "20260908-1", "project_id": "u6", "doc_type": "crew_update"}),
        ("Old report Best Buy 490 Carmel IN survey", {"date": "2026-09-05", "email_id": "e5",
         "doc_type": "crew_update"}),                                   # historico sin codigo
        ("Old report Best Buy Waterford CT survey", {"date": "2026-09-06", "email_id": "e6",
         "doc_type": "crew_update"}),                                   # historico, otro proyecto
        ("Hy-Vee (West Point, NE) FRP install and checkout demo", {"date": "2026-09-29",
         "email_id": "e7", "doc_type": "crew_update"}),                 # proyecto no registrado
        ("Hy-Vee (West Point, NE) painting and ceiling signage", {"date": "2026-09-30",
         "email_id": "e8", "doc_type": "crew_update"}),
    ])

    pruebas = []

    def caso(n, c):
        pruebas.append((n, bool(c)))

    def R(**kw):
        _reset_cache()
        return resolver_proyecto(_fetch=fetch_ok, **kw)

    # Resolucion
    caso("01 codigo exacto", R(codigo="20260910-01")["proyecto"]["code"] == "20260910-01")
    caso("02 codigo en minusculas / con espacios", R(codigo=" 20260910-01 ")["estado"] == RESUELTO)
    caso("03 nombre completo 'Best Buy Carmel'",
         R(nombre="Best Buy Carmel")["proyecto"]["code"] == "20260910-01")
    caso("04 solo ciudad 'carmel'", R(nombre="carmel")["proyecto"]["code"] == "20260910-01")
    caso("05 abreviatura 'BB 490'", R(nombre="BB 490")["proyecto"]["code"] == "20260910-01")
    caso("06 error de tipeo 'Best Buy Carmle'",
         R(nombre="Best Buy Carmle")["proyecto"]["code"] == "20260910-01")
    r = R(nombre="Best Buy")
    caso("07 'Best Buy' es AMBIGUO (4 proyectos)", r["estado"] == AMBIGUO and len(r["candidatos"]) == 4)
    caso("08 'Macy's Richmond'", R(nombre="Macy's Richmond")["proyecto"]["code"] == "20260908-1")
    caso("09 'macys' sin apostrofe", R(nombre="macys")["proyecto"]["code"] == "20260908-1")
    r = R(nombre="TJ Maxx")
    caso("10 'TJ Maxx' es AMBIGUO (Madison y Tupelo)", r["estado"] == AMBIGUO and len(r["candidatos"]) == 2)
    caso("11 'TJ Maxx Tupelo'", R(nombre="TJ Maxx Tupelo")["proyecto"]["code"] == "20260904-2")
    caso("12 codigo + nombre coherentes",
         R(codigo="20260910-01", nombre="Carmel")["estado"] == RESUELTO)
    r = R(codigo="20260910-01", nombre="Macy's Richmond")
    caso("13 codigo + nombre en CONFLICTO", r["estado"] == CONFLICTO
         and r["candidatos"][0]["code"] == "20260908-1")
    r = R(codigo="20260910-02", nombre="Best Buy Carmel")
    caso("14 codigo con error + nombre -> resuelve y corrige",
         r["estado"] == RESUELTO and "20260910-01" in r["nota"])
    r = R(codigo="20260910-02")
    caso("15 codigo con error solo -> sugerencia",
         r["estado"] == NO_ENCONTRADO and r["candidatos"][0]["code"] == "20260910-01")
    caso("16 nombre inexistente", R(nombre="Walgreens Dallas")["estado"] == NO_ENCONTRADO)
    caso("17 sin datos", R()["estado"] == NO_ENCONTRADO)
    _reset_cache()
    caso("18 JRS OPS caido -> NO_VERIFICADO",
         resolver_proyecto(codigo="20260910-01", _fetch=fetch_falla)["estado"] == NO_VERIFICADO)

    # Consulta
    def C(**kw):
        _reset_cache()
        return consultar_proyecto(_coleccion=col, _fetch=fetch_ok, **kw)

    r = C(codigo="20260910-01", fecha_desde="2026-09-29")
    textos = " ".join(x["texto"] for x in r["reportes"])
    caso("19 dia 29 incluye reportes registrados el 29",
         "filler measured" in textos and "lock installed" in textos)
    r = C(codigo="20260910-01", fecha_desde="2026-09-28")
    caso("20 dia 28 encuentra el reporte registrado el 29 (dia siguiente)",
         any(x.get("coincidencia") == "registrado_dia_siguiente" for x in r["reportes"]))
    r = C(nombre="carmel", fecha_desde="2026-09-27")
    caso("21 sin reporte ese dia -> fechas cercanas",
         not r["reportes"] and "2026-09-25" in r["fechas_disponibles"]
         and "2026-09-29" in r["fechas_disponibles"])
    r = C(codigo="20260910-01", fecha_desde="2026-09-20", fecha_hasta="2026-09-30")
    caso("22 rango de fechas ordenado del mas reciente",
         r["reportes"][0]["fecha_registro"] >= r["reportes"][-1]["fecha_registro"])
    r = C(codigo="20260910-01")
    caso("23 sin fecha -> incluye historico sin codigo de Carmel",
         any(x["origen"] == "historico" and "490 Carmel" in x["texto"] for x in r["reportes"]))
    caso("24 historico NO mezcla otros proyectos (Waterford)",
         not any("Waterford" in x["texto"] for x in r["reportes"]))
    caso("25 no mezcla Macy's en consulta de Carmel",
         not any("Macy" in x["texto"] for x in r["reportes"]))
    r = C(nombre="Best Buy")
    caso("26 AMBIGUO no busca reportes", r["resolucion"] == AMBIGUO and not r["reportes"])
    r = C(codigo="20260910-01", limite=2)
    caso("27 respeta el limite", len(r["reportes"]) == 2)
    col_larga = _ColeccionFalsa([("x" * 9000, {"date": "2026-09-29", "email_id": "z",
                                              "project_code": "20260910-01", "project_id": "u8"})])
    _reset_cache()
    r = consultar_proyecto(codigo="20260910-01", _coleccion=col_larga, _fetch=fetch_ok)
    caso("28 recorta reportes muy largos", r["reportes"][0]["texto"].endswith("[...]"))
    r = C(codigo="20260910-01", fecha_desde="2026-09-30", fecha_hasta="2026-09-29")
    caso("29 fechas invertidas se corrigen", len(r["reportes"]) >= 1)

    r = C(nombre="Hy-Vee West Point")
    caso("30 nombre fuera de JRS OPS -> NO_REGISTRADO con historial",
         r["resolucion"] == NO_REGISTRADO and len(r["reportes"]) == 2
         and "NOT registered" in r["nota"])
    r = C(nombre="hyvee west point", fecha_desde="2026-09-30")
    caso("31 NO_REGISTRADO respeta la fecha",
         r["resolucion"] == NO_REGISTRADO and len(r["reportes"]) == 1
         and "painting" in r["reportes"][0]["texto"])
    r = C(nombre="Hy-Vee West Point", fecha_desde="2026-09-20")
    caso("32 NO_REGISTRADO sin reporte ese dia -> fechas cercanas",
         not r["reportes"] and "2026-09-29" in r["fechas_disponibles"])
    r = C(codigo="20269999-01")
    caso("33 codigo inexistente NO busca por texto",
         r["resolucion"] == NO_ENCONTRADO and not r["reportes"])
    r = C(nombre="Walgreens Dallas")
    caso("34 nombre sin historial -> NO_ENCONTRADO", r["resolucion"] == NO_ENCONTRADO)

    ok = sum(1 for _, p in pruebas if p)
    for n, p in pruebas:
        print(f"  {'✅' if p else '❌'} {n}")
    print(f"\n{ok}/{len(pruebas)} pruebas pasaron")
    _reset_cache()
    return ok == len(pruebas)


def _cli():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = sys.argv[1:]
    if not args:
        sys.exit(0 if _autotest() else 1)
    def _separar(ref):
        # "20260910-01" -> codigo ; "best buy carmel" -> nombre
        return (ref, None) if re.fullmatch(r"[\w.\-/]*\d[\w.\-/]*", ref.strip()) else (None, ref)

    if args[0] == "--resolver" and len(args) > 1:
        cod, nom = _separar(args[1])
        print(json.dumps(resolver_proyecto(codigo=cod, nombre=nom),
                         ensure_ascii=False, indent=2))
    elif args[0] == "--consultar" and len(args) > 1:
        cod, nom = _separar(args[1])
        desde = args[2] if len(args) > 2 else None
        hasta = args[3] if len(args) > 3 else None
        r = consultar_proyecto(codigo=cod, nombre=nom, fecha_desde=desde, fecha_hasta=hasta)
        for x in r["reportes"]:
            x["texto"] = x["texto"][:300] + ("..." if len(x["texto"]) > 300 else "")
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(__doc__)


if __name__ == "__main__":
    _cli()
