"""
codigos_proyecto.py — Etapa 1: extracción y verificación de códigos de proyecto
================================================================================
Módulo STANDALONE (no toca agent.py ni tools.py todavía).

Fuente de verdad: tabla `projects` de JRS Operations System (Supabase).
Joe NO inventa ni guarda códigos propios: solo los extrae del asunto del correo
y verifica que existan en JRS OPS.

Estados posibles de verificar_asunto():
    VALIDO         -> el código existe en JRS OPS
    HUERFANO       -> hay código en el asunto, pero no existe en JRS OPS (avisar)
    SIN_CODIGO     -> el asunto no trae ningún código entre corchetes (avisar)
    MULTIPLE       -> el asunto trae más de un código (avisar)
    NO_VERIFICADO  -> Supabase no respondió y no hay catálogo en caché
                      (NO es lo mismo que HUERFANO: no se puede afirmar que no exista)

Variables de entorno (Railway):
    SUPABASE_URL               https://<project_ref>.supabase.co
    SUPABASE_SERVICE_KEY       clave service_role (secreto; solo lectura en este módulo)
    CODIGOS_CACHE_TTL          segundos de caché del catálogo (por defecto 300)
    CODIGOS_TAGS_RESERVADOS    etiquetas extra a ignorar, separadas por coma

Uso desde la consola:
    python codigos_proyecto.py                      -> corre los autotests
    python codigos_proyecto.py --probar-conexion    -> consulta real a Supabase
    python codigos_proyecto.py --verificar "[P-1] Daily Report"
"""

import os
import re
import sys
import json
import time
import difflib
import logging
import unicodedata
import urllib.request
import urllib.error

log = logging.getLogger("codigos_proyecto")

# ---------------------------------------------------------------------------
# Estados
# ---------------------------------------------------------------------------
VALIDO = "VALIDO"
HUERFANO = "HUERFANO"
SIN_CODIGO = "SIN_CODIGO"
MULTIPLE = "MULTIPLE"
NO_VERIFICADO = "NO_VERIFICADO"


class CatalogoNoDisponible(Exception):
    """Supabase no respondió (o falta configuración) y no hay caché."""


# ---------------------------------------------------------------------------
# Extracción
# ---------------------------------------------------------------------------
_TAGS_RESERVADOS_BASE = {
    "CREWUPDATE", "CREW-UPDATE", "URGENT", "URGENTE", "FWD", "FW", "RE",
    "EXTERNAL", "EXTERNO", "TEST", "PRUEBA", "CRITICAL", "INFO",
}

_RE_CORCHETES = re.compile(r"\[([^\[\]]{1,40})\]")
# Forma de un código: letras/dígitos con separadores - _ . /  (ej. TJX-01, P-1, P09292026-01)
_RE_FORMA_CODIGO = re.compile(r"^[A-Z0-9][A-Z0-9_.\-/]*$")
_RE_TOKEN_TEXTO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-/–—‑]*")

_GUIONES_UNICODE = {"\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015", "\u2212"}


def normalizar_codigo(texto):
    """Mayúsculas, sin espacios, guiones raros -> '-', sin puntuación final."""
    if not texto:
        return ""
    t = unicodedata.normalize("NFKC", str(texto))
    t = "".join("-" if ch in _GUIONES_UNICODE else ch for ch in t)
    t = re.sub(r"\s+", "", t).upper()
    return t.rstrip(".-/_,;:")


def _tags_reservados():
    extra = os.environ.get("CODIGOS_TAGS_RESERVADOS", "")
    extras = {normalizar_codigo(x) for x in extra.split(",") if x.strip()}
    return _TAGS_RESERVADOS_BASE | extras


def _parece_codigo(norm):
    return (
        bool(norm)
        and bool(_RE_FORMA_CODIGO.match(norm))
        and any(ch.isdigit() for ch in norm)      # descarta [URGENT], [CREW UPDATE]
        and norm not in _tags_reservados()
    )


def extraer_codigos(asunto):
    """Devuelve los códigos candidatos entre corchetes, normalizados y sin duplicados."""
    vistos = []
    for bruto in _RE_CORCHETES.findall(asunto or ""):
        norm = normalizar_codigo(bruto)
        if _parece_codigo(norm) and norm not in vistos:
            vistos.append(norm)
    return vistos


# ---------------------------------------------------------------------------
# Catálogo de proyectos (Supabase) con caché
# ---------------------------------------------------------------------------
_cache = {"ts": 0.0, "catalogo": None}


def _reset_cache():
    _cache["ts"] = 0.0
    _cache["catalogo"] = None


def _ttl():
    try:
        return int(os.environ.get("CODIGOS_CACHE_TTL", "300"))
    except ValueError:
        return 300


def _consultar_supabase():
    """GET de solo lectura a la tabla projects. Devuelve lista de dicts."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise CatalogoNoDisponible("Faltan SUPABASE_URL o SUPABASE_SERVICE_KEY")

    endpoint = f"{url}/rest/v1/projects?select=id,code,name,status&order=code.asc"
    req = urllib.request.Request(endpoint, method="GET", headers={
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
        raise CatalogoNoDisponible(f"Supabase no respondió: {e}") from e


def obtener_catalogo(forzar=False, _fetch=None):
    """
    Devuelve {codigo_normalizado: proyecto}.
    Si Supabase falla pero hay caché previa, usa la caché (aunque esté vencida).
    Si falla y no hay caché, lanza CatalogoNoDisponible.
    """
    vigente = (time.time() - _cache["ts"]) < _ttl()
    if _cache["catalogo"] is not None and vigente and not forzar:
        return _cache["catalogo"]

    fetch = _fetch or _consultar_supabase
    try:
        filas = fetch()
    except Exception as e:
        if _cache["catalogo"] is not None:
            log.warning("Catálogo de proyectos: usando caché vencida (%s)", e)
            return _cache["catalogo"]
        raise CatalogoNoDisponible(str(e)) from e

    catalogo = {}
    for p in filas or []:
        norm = normalizar_codigo(p.get("code"))
        if norm:
            catalogo[norm] = {
                "id": p.get("id"),
                "code": p.get("code"),
                "name": p.get("name"),
                "status": p.get("status"),
            }
    _cache["catalogo"] = catalogo
    _cache["ts"] = time.time()
    return catalogo


# ---------------------------------------------------------------------------
# Verificación
# ---------------------------------------------------------------------------
def _sugerencias(codigo, catalogo, n=3):
    return [catalogo[c]["code"] for c in
            difflib.get_close_matches(codigo, list(catalogo.keys()), n=n, cutoff=0.75)]


def verificar_asunto(asunto, _fetch=None):
    """
    Decisión determinística sobre el código del asunto.
    Devuelve dict: estado, codigo, codigos, proyecto, sugerencias, detalle.
    """
    codigos = extraer_codigos(asunto)
    base = {"estado": None, "codigo": None, "codigos": codigos,
            "proyecto": None, "sugerencias": [], "detalle": ""}

    if not codigos:
        base.update(estado=SIN_CODIGO, detalle="El asunto no trae código entre corchetes.")
        return base

    if len(codigos) > 1:
        base.update(estado=MULTIPLE, detalle=f"El asunto trae {len(codigos)} códigos: {', '.join(codigos)}.")
        return base

    codigo = codigos[0]
    base["codigo"] = codigo

    try:
        catalogo = obtener_catalogo(_fetch=_fetch)
    except CatalogoNoDisponible as e:
        base.update(estado=NO_VERIFICADO, detalle=f"No se pudo consultar JRS OPS: {e}")
        return base

    if codigo in catalogo:
        base.update(estado=VALIDO, proyecto=catalogo[codigo],
                    detalle=f"Código encontrado: {catalogo[codigo]['name']}.")
    else:
        base.update(estado=HUERFANO, sugerencias=_sugerencias(codigo, catalogo),
                    detalle="El código no existe en JRS OPS.")
    return base


def codigos_mencionados(texto, _fetch=None):
    """
    Para consultas en lenguaje libre (chat / correo):
    'resumen del 29 de sept de Chilis (código P09292026-01)' -> ['P09292026-01'].
    Solo devuelve códigos que EXISTEN en el catálogo.
    """
    try:
        catalogo = obtener_catalogo(_fetch=_fetch)
    except CatalogoNoDisponible:
        return []
    encontrados = []
    for tok in _RE_TOKEN_TEXTO.findall(texto or ""):
        norm = normalizar_codigo(tok)
        if norm in catalogo and catalogo[norm]["code"] not in encontrados:
            encontrados.append(catalogo[norm]["code"])
    return encontrados


def mensaje_aviso(resultado, idioma="es"):
    """Texto de aviso para el remitente. None si no hay nada que avisar."""
    estado = resultado.get("estado")
    codigo = resultado.get("codigo")
    sug = resultado.get("sugerencias") or []

    if idioma == "en":
        textos = {
            HUERFANO: (f"I have loaded the project into the database, but I could not find a previously "
                       f"created code matching {codigo}. Please review."),
            SIN_CODIGO: ("I have loaded this report into the database, but the subject line has no project "
                         "code in brackets. Please review."),
            MULTIPLE: (f"I have loaded this report, but the subject line contains more than one project code "
                       f"({', '.join(resultado.get('codigos', []))}). Please review."),
            NO_VERIFICADO: (f"I have loaded the report with code {codigo}, but I could not verify it against "
                            f"JRS Operations System right now. I will flag it for review."),
        }
        extra = f" Did you mean: {', '.join(sug)}?" if sug else ""
    else:
        textos = {
            HUERFANO: (f"He cargado el proyecto en la base de datos, pero no he conseguido un código "
                       f"previamente creado que coincida con {codigo}, favor revisar."),
            SIN_CODIGO: ("He cargado el reporte en la base de datos, pero el asunto no trae un código de "
                         "proyecto entre corchetes, favor revisar."),
            MULTIPLE: (f"He cargado el reporte, pero el asunto trae más de un código de proyecto "
                       f"({', '.join(resultado.get('codigos', []))}), favor revisar."),
            NO_VERIFICADO: (f"He cargado el reporte con el código {codigo}, pero no pude verificarlo contra "
                            f"JRS Operations System en este momento. Queda marcado para revisión."),
        }
        extra = f" ¿Quizás quisiste decir: {', '.join(sug)}?" if sug else ""

    if estado not in textos:
        return None
    return textos[estado] + (extra if estado == HUERFANO else "")


# ---------------------------------------------------------------------------
# Autotests
# ---------------------------------------------------------------------------
def _autotest():
    catalogo_falso = [
        {"id": "u1", "code": "P09292026-01", "name": "Chili's #123", "status": "active"},
        {"id": "u2", "code": "P09012026-01", "name": "Target T-2419", "status": "active"},
        {"id": "u3", "code": "TJX-01", "name": "TJ Maxx Katy", "status": "completed"},
        {"id": "u4", "code": "P-1", "name": "Proyecto legado", "status": "active"},
    ]
    fetch_ok = lambda: catalogo_falso

    def fetch_falla():
        raise CatalogoNoDisponible("simulado: Supabase caído")

    pruebas = []

    def caso(nombre, cond):
        pruebas.append((nombre, bool(cond)))

    # Extracción
    caso("01 extrae código simple", extraer_codigos("[P09292026-01] Daily Report") == ["P09292026-01"])
    caso("02 normaliza minúsculas", extraer_codigos("[p09292026-01] daily") == ["P09292026-01"])
    caso("03 normaliza guion largo (–)", extraer_codigos("[P09292026–01] x") == ["P09292026-01"])
    caso("04 ignora [CREW UPDATE]", extraer_codigos("[CREW UPDATE] [P-1] Day 3") == ["P-1"])
    caso("05 ignora etiquetas sin dígitos", extraer_codigos("[URGENT] Water leak") == [])
    caso("06 sin corchetes -> vacío", extraer_codigos("Daily report P09292026-01") == [])
    caso("07 detecta dos códigos", extraer_codigos("[P-1] y [TJX-01]") == ["P-1", "TJX-01"])
    caso("08 deduplica mismo código", extraer_codigos("[P-1] ... [p-1]") == ["P-1"])
    caso("09 tolera espacios internos", extraer_codigos("[ TJX-01 ] report") == ["TJX-01"])
    caso("10 funciona con Fwd/RE", extraer_codigos("Fwd: RE: [P09292026-01] Day 2") == ["P09292026-01"])

    # Verificación
    _reset_cache()
    r = verificar_asunto("[P09292026-01] Daily Report", _fetch=fetch_ok)
    caso("11 VALIDO con proyecto", r["estado"] == VALIDO and r["proyecto"]["name"] == "Chili's #123")

    _reset_cache()
    r = verificar_asunto("[P09022026-01] Daily Report", _fetch=fetch_ok)
    caso("12 HUERFANO + sugiere P09012026-01",
         r["estado"] == HUERFANO and "P09012026-01" in r["sugerencias"])

    _reset_cache()
    caso("13 SIN_CODIGO", verificar_asunto("Daily Report", _fetch=fetch_ok)["estado"] == SIN_CODIGO)
    caso("14 MULTIPLE", verificar_asunto("[P-1] [TJX-01]", _fetch=fetch_ok)["estado"] == MULTIPLE)

    _reset_cache()
    caso("15 NO_VERIFICADO si Supabase cae sin caché",
         verificar_asunto("[P-1] x", _fetch=fetch_falla)["estado"] == NO_VERIFICADO)

    _reset_cache()
    obtener_catalogo(_fetch=fetch_ok)
    _cache["ts"] = 0.0  # fuerza caché vencida
    caso("16 usa caché vencida si Supabase cae",
         verificar_asunto("[TJX-01] x", _fetch=fetch_falla)["estado"] == VALIDO)

    _reset_cache()
    caso("17 códigos legados (TJX-01, P-1) válidos",
         verificar_asunto("[tjx-01] x", _fetch=fetch_ok)["estado"] == VALIDO
         and verificar_asunto("[P-1] x", _fetch=fetch_ok)["estado"] == VALIDO)

    # Faltan variables de entorno -> NO_VERIFICADO (nunca HUERFANO falso)
    _reset_cache()
    respaldo = {k: os.environ.pop(k, None) for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY")}
    caso("18 sin env vars -> NO_VERIFICADO", verificar_asunto("[P-1] x")["estado"] == NO_VERIFICADO)
    for k, v in respaldo.items():
        if v is not None:
            os.environ[k] = v

    # Mensajes
    _reset_cache()
    r = verificar_asunto("[P09022026-01] x", _fetch=fetch_ok)
    m = mensaje_aviso(r)
    caso("19 aviso HUERFANO con texto y sugerencia",
         m and "no he conseguido un código" in m and "P09012026-01" in m)
    caso("20 sin aviso si VALIDO",
         mensaje_aviso(verificar_asunto("[P-1] x", _fetch=fetch_ok)) is None)
    caso("21 aviso en inglés", "Please review" in (mensaje_aviso(r, idioma="en") or ""))

    # Lenguaje libre
    caso("22 código en texto libre",
         codigos_mencionados("Joe, dame un resumen del 29 de septiembre de Chilis (código P09292026-01).",
                             _fetch=fetch_ok) == ["P09292026-01"])
    caso("23 texto libre ignora códigos inexistentes",
         codigos_mencionados("revisa P09992026-01 por favor", _fetch=fetch_ok) == [])

    ok = sum(1 for _, p in pruebas if p)
    for nombre, p in pruebas:
        print(f"  {'✅' if p else '❌'} {nombre}")
    print(f"\n{ok}/{len(pruebas)} pruebas pasaron")
    _reset_cache()
    return ok == len(pruebas)


def _cli():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = sys.argv[1:]
    if not args:
        sys.exit(0 if _autotest() else 1)
    if args[0] == "--probar-conexion":
        try:
            cat = obtener_catalogo(forzar=True)
            print(f"✅ Conexión OK — {len(cat)} proyectos en JRS OPS")
            for p in list(cat.values())[:10]:
                print(f"   {p['code']:<16} {p['status'] or '':<10} {p['name']}")
        except CatalogoNoDisponible as e:
            print(f"❌ {e}")
            sys.exit(1)
    elif args[0] == "--verificar" and len(args) > 1:
        r = verificar_asunto(args[1])
        print(json.dumps(r, ensure_ascii=False, indent=2))
        aviso = mensaje_aviso(r)
        if aviso:
            print(f"\nAviso: {aviso}")
    else:
        print(__doc__)


if __name__ == "__main__":
    _cli()
