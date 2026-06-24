# agent.py
# El agente MCP de JRS — Agent Loop principal
# Version sin claude_agent_sdk — usa Anthropic API directamente

import os
import json
import asyncio
import logging
import zipfile
import shutil
import requests
from datetime import datetime
from dotenv import load_dotenv
import anthropic
import base64
import re
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from whitelist import verify_sender
from tools import (
    obtener_servicio_gmail,
    obtener_id_etiqueta,
    extraer_cuerpo_correo,
    classify_email,
    search_drive,
    generate_report,
    create_gmail_draft,
    alert_if_critical,
    consult_building_code,
    verify_compliance,
    cite_applicable_standard,
)
from client_protocols import get_protocol

load_dotenv()  # En local lee .env. En Railway no hay .env: lee las env vars del panel.

# =====================================================
# CONFIGURACION DESDE EL ENTORNO
# En local sale del .env; en Railway sale del panel de Variables.
# =====================================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
TIMEZONE = os.getenv("TIMEZONE", "America/Chicago")
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_data")

MODELO = os.getenv("AGENT_MODEL", "claude-opus-4-8")
SLEEP_BETWEEN_CYCLES_SECONDS = int(os.getenv("SLEEP_BETWEEN_CYCLES_SECONDS", "300"))
MAX_EMAILS_PER_CYCLE = int(os.getenv("MAX_EMAILS_PER_CYCLE", "10"))
MAX_ITERATIONS_PER_EMAIL = int(os.getenv("MAX_ITERATIONS_PER_EMAIL", "20"))
MAX_CONSECUTIVE_FAILURES = int(os.getenv("MAX_CONSECUTIVE_FAILURES", "5"))

# Bootstrap del ChromaDB (descarga inicial desde GitHub Releases en Railway).
# En local no se usa porque ./chroma_data ya existe.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO", "ProjectsJRS/JRS-Agente")
CHROMADB_ASSET_ID = os.getenv("CHROMADB_ASSET_ID", "456015817")

# Validacion: si falta lo critico, fallar rapido con mensaje claro
# en lugar de morir misteriosamente a los 30 segundos en Railway.
if not ANTHROPIC_API_KEY:
    raise RuntimeError(
        "ANTHROPIC_API_KEY no configurada. Revisa las env vars de Railway."
    )

# =====================================================
# CONFIGURACION DE LOGGING
# Solo stdout: Railway captura la consola y la guarda en su panel de logs.
# NO escribimos archivo local porque el contenedor se borra en cada redeploy.
# =====================================================
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("jrs-agent")

# =====================================================
# CARGAR EL SYSTEM PROMPT
# =====================================================
with open("system_prompt.txt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

# =====================================================
# CLIENTE ANTHROPIC
# =====================================================
cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# =====================================================
# DEFINICION DE HERRAMIENTAS PARA LA API
# =====================================================
TOOLS_DEFINITION = [
    {
        "name": "classify_email",
        "description": (
            "Clasifica un correo en una de cuatro categorias: cliente, crew, "
            "vendor o inspeccion. Devuelve categoria, cliente_detectado, "
            "confianza y razones. Usala despues de recibir el correo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Asunto del correo"},
                "body": {"type": "string", "description": "Cuerpo del correo"},
                "sender": {"type": "string", "description": "Remitente del correo"},
            },
            "required": ["subject", "body", "sender"],
        },
    },
    {
        "name": "search_drive",
        "description": (
            "Busca archivos en Google Drive relacionados con un proyecto o cliente. "
            "Usala cuando necesites contexto adicional: scope, planos, specs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Texto a buscar en Drive"},
                "max_results": {"type": "integer", "description": "Maximo de archivos (default 5)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "generate_report",
        "description": (
            "Genera un Project Intelligence Report estructurado en formato JRS. "
            "Usala DESPUES de leer el correo, clasificarlo y buscar contexto."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "location": {"type": "string"},
                "client": {"type": "string"},
                "shift": {"type": "string"},
                "current_status": {"type": "string"},
                "work_completed": {"type": "string"},
                "work_pending": {"type": "string"},
                "issues_detected": {"type": "string"},
                "risk_level": {"type": "string", "description": "CRITICAL, HIGH, MEDIUM o LOW"},
                "materials_needed": {"type": "string"},
                "followup_required": {"type": "string"},
                "photos_needed": {"type": "string"},
                "compliance_notes": {"type": "string"},
                "recommended_actions": {"type": "string"},
            },
            "required": [
                "project", "location", "client", "shift",
                "current_status", "work_completed", "work_pending",
                "issues_detected", "risk_level"
            ],
        },
    },
    {
        "name": "create_gmail_draft",
        "description": (
            "Crea un borrador en Gmail con el reporte generado. NUNCA envia. "
            "Si is_external es True antepone el header obligatorio de aprobacion. "
            "Cambia la etiqueta del correo de AI-Agent a AI-Procesado. "
            "Usala como paso final del procesamiento de cada correo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "original_email_id": {"type": "string", "description": "ID del correo original"},
                "to": {"type": "string", "description": "Destinatario del borrador"},
                "subject": {"type": "string", "description": "Asunto del borrador"},
                "body": {"type": "string", "description": "Cuerpo del borrador"},
                "is_external": {"type": "boolean", "description": "True si el destinatario es externo"},
            },
            "required": ["original_email_id", "to", "subject", "body"],
        },
    },
    {
        "name": "alert_if_critical",
        "description": (
            "Manda alerta inmediata a Richard cuando severity es CRITICAL. "
            "NO espera al reporte diario. "
            "Usala SOLO cuando hayas determinado severidad CRITICAL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "description": "CRITICAL, HIGH, MEDIUM o LOW"},
                "project": {"type": "string", "description": "Nombre del proyecto"},
                "summary": {"type": "string", "description": "Resumen de 1-2 lineas"},
                "detail": {"type": "string", "description": "Detalle completo del incidente"},
            },
            "required": ["severity", "project", "summary", "detail"],
        },
    },
    {
        "name": "consult_building_code",
        "description": (
            "Consulta un codigo de construccion (IBC, NFPA, ADA, OSHA) "
            "y devuelve la seccion aplicable. Usala cuando un correo mencione "
            "un tema tecnico que requiera verificar contra codigo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code_family": {"type": "string", "description": "IBC, NFPA-101, ADA, OSHA-1926"},
                "topic": {"type": "string", "description": "Tema a consultar"},
                "state": {"type": "string", "description": "Estado de 2 letras (opcional)"},
            },
            "required": ["code_family", "topic"],
        },
    },
    {
        "name": "verify_compliance",
        "description": (
            "Verifica si un escenario cumple con un codigo especifico. "
            "Devuelve status compliant/non-compliant/needs-review. "
            "Usala DESPUES de consult_building_code."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "observed_value": {"type": "string", "description": "Valor observado en sitio"},
                "standard_reference": {"type": "string", "description": "Referencia de la norma"},
                "required_value": {"type": "string", "description": "Valor requerido por la norma"},
                "context": {"type": "string", "description": "Contexto adicional"},
            },
            "required": ["observed_value", "standard_reference", "required_value"],
        },
    },
    {
        "name": "cite_applicable_standard",
        "description": (
            "Genera una cita formal de una norma lista para incluir en un reporte. "
            "Usala al cerrar el analisis de compliance."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code_family": {"type": "string"},
                "year": {"type": "string"},
                "section": {"type": "string"},
                "topic": {"type": "string"},
                "state": {"type": "string"},
            },
            "required": ["code_family", "section", "topic"],
        },
    },
]

# =====================================================
# EJECUTOR DE HERRAMIENTAS
# =====================================================
def ejecutar_herramienta(nombre: str, parametros: dict) -> str:
    """
    Dispatcher: llama a la función correspondiente en tools.py
    y devuelve el resultado como string JSON.
    """
    try:
        if nombre == "classify_email":
            resultado = classify_email(
                subject=parametros.get("subject", ""),
                body=parametros.get("body", ""),
                sender=parametros.get("sender", ""),
            )

        elif nombre == "search_drive":
            resultado = search_drive(
                query=parametros.get("query", ""),
                max_results=parametros.get("max_results", 5),
            )

        elif nombre == "generate_report":
            resultado = generate_report(
                project=parametros.get("project", ""),
                location=parametros.get("location", ""),
                client=parametros.get("client", ""),
                shift=parametros.get("shift", ""),
                current_status=parametros.get("current_status", ""),
                work_completed=parametros.get("work_completed", ""),
                work_pending=parametros.get("work_pending", ""),
                issues_detected=parametros.get("issues_detected", ""),
                risk_level=parametros.get("risk_level", "MEDIUM"),
                materials_needed=parametros.get("materials_needed", ""),
                followup_required=parametros.get("followup_required", ""),
                photos_needed=parametros.get("photos_needed", ""),
                compliance_notes=parametros.get("compliance_notes", ""),
                recommended_actions=parametros.get("recommended_actions", ""),
            )

        elif nombre == "create_gmail_draft":
            resultado = create_gmail_draft(
                original_email_id=parametros.get("original_email_id", ""),
                to=parametros.get("to", ""),
                subject=parametros.get("subject", ""),
                body=parametros.get("body", ""),
                is_external=parametros.get("is_external", True),
            )

        elif nombre == "alert_if_critical":
            resultado = alert_if_critical(
                severity=parametros.get("severity", ""),
                project=parametros.get("project", ""),
                summary=parametros.get("summary", ""),
                detail=parametros.get("detail", ""),
            )

        elif nombre == "consult_building_code":
            resultado = consult_building_code(
                code_family=parametros.get("code_family", ""),
                topic=parametros.get("topic", ""),
                state=parametros.get("state", ""),
            )

        elif nombre == "verify_compliance":
            resultado = verify_compliance(
                observed_value=parametros.get("observed_value", ""),
                standard_reference=parametros.get("standard_reference", ""),
                required_value=parametros.get("required_value", ""),
                context=parametros.get("context", ""),
            )

        elif nombre == "cite_applicable_standard":
            resultado = cite_applicable_standard(
                code_family=parametros.get("code_family", ""),
                year=parametros.get("year", ""),
                section=parametros.get("section", ""),
                topic=parametros.get("topic", ""),
                state=parametros.get("state", ""),
            )

        else:
            return json.dumps({"error": f"Herramienta desconocida: {nombre}"})

        return json.dumps(resultado)

    except Exception as e:
        logger.error(f"Error ejecutando herramienta '{nombre}': {e}")
        return json.dumps({"error": str(e)})


# =====================================================
# LECTURA DIRECTA DE CORREOS
# =====================================================
def leer_correos_pendientes(max_results: int = 10) -> list:
    try:
        service = obtener_servicio_gmail()
        id_etiqueta = obtener_id_etiqueta(service, "AI-Agent")
        if not id_etiqueta:
            logger.warning("Etiqueta AI-Agent no encontrada en Gmail.")
            return []

        resultados = service.users().messages().list(
            userId='me',
            labelIds=[id_etiqueta],
            maxResults=max_results
        ).execute()

        mensajes = resultados.get('messages', [])
        correos = []

        for mensaje in mensajes:
            msg = service.users().messages().get(
                userId='me', id=mensaje['id'], format='full'
            ).execute()

            headers = msg['payload']['headers']
            asunto = next((h['value'] for h in headers if h['name'] == 'Subject'), '(sin asunto)')
            remitente = next((h['value'] for h in headers if h['name'] == 'From'), '(sin remitente)')
            fecha = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            cuerpo = extraer_cuerpo_correo(msg['payload'])

            correos.append({
                'id': mensaje['id'],
                'from': remitente,
                'subject': asunto,
                'body': cuerpo,
                'date': fecha,
            })

        return correos

    except Exception as e:
        logger.error(f"Error leyendo correos: {e}")
        return []


# =====================================================
# AGENT LOOP — un correo
# =====================================================
def procesar_un_correo(correo: dict) -> dict:
    email_id = correo.get("id", "unknown")
    sender_raw = correo.get("from", "")
    asunto = correo.get("subject", "(sin asunto)")

    logger.info(f"Procesando correo {email_id} - {asunto}")

    # Verificacion anti-spoofing
    sender_check = verify_sender(sender_raw)
    if sender_check["spoofing_risk"] == "high":
        logger.warning(f"Spoofing detectado en {email_id}: {sender_check['reason']}")
        return {"result": "blocked_spoofing", "iterations": 0, "draft_id": None}

    # Obtener protocolo del cliente si aplica
    contexto_remitente = (
        f"REMITENTE: {sender_check['name'] or sender_check['email']}\n"
        f"ROL: {sender_check['role']}\n"
        f"INTERNO: {sender_check['is_internal']}\n"
        f"PUEDE APROBAR EXTERNOS: {sender_check['can_approve_external']}\n"
        f"ASUNTO: {asunto}\n"
        f"FECHA: {correo.get('date', '')}\n"
        f"CUERPO:\n{correo.get('body', '')}"
    )

    instruccion = (
        "IMPORTANT: All reports, drafts and communications must be written in English only. "
        "Process the following email following the system prompt protocol. "
        "If the sender is external, prepare only a draft with the approval header. "
        "If you detect CRITICAL severity, send an immediate alert before continuing. "
        "Use the available tools to classify, search context, generate the report, "
        "and create the Gmail draft.\n\n"
        f"EMAIL_ID to use when modifying labels: {email_id}\n\n"
        f"{contexto_remitente}"
    )

    # Agent Loop con Anthropic API
    messages = [{"role": "user", "content": instruccion}]
    iteraciones = 0
    draft_id = None

    try:
        while iteraciones < MAX_ITERATIONS_PER_EMAIL:
            iteraciones += 1
            logger.info(f"  Iteracion {iteraciones}...")

            respuesta = cliente.messages.create(
                model=MODELO,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                tools=TOOLS_DEFINITION,
                messages=messages,
            )

            # Agregar respuesta del asistente al historial
            messages.append({"role": "assistant", "content": respuesta.content})

            # Si Claude termino sin usar herramientas
            if respuesta.stop_reason == "end_turn":
                logger.info(f"Correo {email_id} completado en {iteraciones} iteraciones.")
                break

            # Si Claude quiere usar herramientas
            if respuesta.stop_reason == "tool_use":
                tool_results = []

                for bloque in respuesta.content:
                    if bloque.type == "tool_use":
                        nombre_tool = bloque.name
                        params_tool = bloque.input
                        tool_use_id = bloque.id

                        logger.info(f"  Herramienta: {nombre_tool}")
                        resultado = ejecutar_herramienta(nombre_tool, params_tool)

                        # Capturar draft_id si se creo un borrador
                        try:
                            resultado_dict = json.loads(resultado)
                            if nombre_tool == "create_gmail_draft" and resultado_dict.get("draft_id"):
                                draft_id = resultado_dict["draft_id"]
                        except Exception:
                            pass

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": resultado,
                        })

                # Agregar resultados de herramientas al historial
                messages.append({"role": "user", "content": tool_results})

            else:
                # stop_reason inesperado
                logger.warning(f"Stop reason inesperado: {respuesta.stop_reason}")
                break

    except Exception as e:
        logger.error(f"Error en Agent Loop para {email_id}: {e}")
        return {"result": f"error: {e}", "iterations": iteraciones, "draft_id": None}

    return {
        "result": "processed",
        "iterations": iteraciones,
        "draft_id": draft_id,
    }


# =====================================================
# BOOTSTRAP DEL CHROMADB
# La primera vez que el agente arranca en Railway, el volumen /data esta vacio.
# Esta funcion descarga la base de Fase 5 desde GitHub Releases y la instala.
# En arranques posteriores detecta que ya existe y no hace nada.
# En local no se activa porque ./chroma_data ya tiene la base.
# =====================================================
def asegurar_chromadb():
    marcador = os.path.join(CHROMA_DB_PATH, "chroma.sqlite3")

    # Validamos que el ChromaDB este COMPLETO, no solo que exista el archivo.
    # ChromaDB crea un chroma.sqlite3 vacio (~150 KB) automaticamente al arrancar
    # sin datos. Una base real pesa decenas de MB y tiene subcarpetas de colecciones.
    # Por eso exigimos: sqlite >= 10 MB Y al menos una subcarpeta de coleccion.
    TAMANO_MINIMO_SQLITE = 10 * 1024 * 1024  # 10 MB

    if os.path.exists(marcador):
        tamano = os.path.getsize(marcador)
        subcarpetas = [
            d for d in os.listdir(CHROMA_DB_PATH)
            if os.path.isdir(os.path.join(CHROMA_DB_PATH, d))
        ]
        if tamano >= TAMANO_MINIMO_SQLITE and subcarpetas:
            logger.info(
                f"ChromaDB completo presente en {CHROMA_DB_PATH} "
                f"({tamano / 1_000_000:.0f} MB, {len(subcarpetas)} colecciones). No se descarga."
            )
            return
        # Existe pero esta incompleto/vacio: lo borramos para descargar el real.
        logger.warning(
            f"ChromaDB en {CHROMA_DB_PATH} esta incompleto "
            f"(sqlite {tamano / 1024:.0f} KB, {len(subcarpetas)} colecciones). "
            "Se eliminara y se descargara la base completa."
        )
        shutil.rmtree(CHROMA_DB_PATH)

    if not GITHUB_TOKEN:
        logger.warning(
            "ChromaDB no encontrado y GITHUB_TOKEN no configurado. "
            "Las consultas de codigos de construccion no funcionaran "
            "hasta que se cargue la base de conocimiento."
        )
        return

    logger.info("ChromaDB no encontrado. Descargando desde GitHub Releases...")

    # Trabajamos dentro del volumen para que el movimiento final sea instantaneo.
    volume_dir = os.path.dirname(CHROMA_DB_PATH) or "."
    os.makedirs(volume_dir, exist_ok=True)
    tmp_zip = os.path.join(volume_dir, "_chromadb_download.zip")
    tmp_extract = os.path.join(volume_dir, "_chromadb_extract")

    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/assets/{CHROMADB_ASSET_ID}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/octet-stream",
    }

    try:
        # 1) Descargar el ZIP por streaming (sin cargar 123 MB en memoria de golpe).
        with requests.get(url, headers=headers, stream=True, timeout=600) as resp:
            resp.raise_for_status()
            total = 0
            with open(tmp_zip, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
                    total += len(chunk)
        logger.info(f"Descarga completa: {total / 1_000_000:.1f} MB")

        # 2) Descomprimir manejando rutas estilo Windows.
        #    El ZIP se creo en Windows, asi que sus rutas internas usan '\'
        #    como separador. Linux NO lo interpreta como separador de carpetas,
        #    asi que hay que traducir '\' a '/' a mano y crear las carpetas reales.
        #    Tambien quitamos el prefijo de la carpeta interna 'chroma_data'.
        if os.path.exists(CHROMA_DB_PATH):
            shutil.rmtree(CHROMA_DB_PATH)
        os.makedirs(CHROMA_DB_PATH, exist_ok=True)

        with zipfile.ZipFile(tmp_zip, "r") as z:
            for info in z.infolist():
                nombre = info.filename.replace("\\", "/")  # normalizar separador
                # Quitar el prefijo 'chroma_data/' para que el contenido quede
                # directo en CHROMA_DB_PATH (ej: /data/chroma_db/chroma.sqlite3).
                if nombre.startswith("chroma_data/"):
                    nombre = nombre[len("chroma_data/"):]
                if not nombre or nombre.endswith("/"):
                    continue  # saltar entradas de carpeta o vacias
                destino = os.path.join(CHROMA_DB_PATH, nombre)
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                with z.open(info) as origen, open(destino, "wb") as salida:
                    shutil.copyfileobj(origen, salida)

        logger.info(f"ChromaDB instalado correctamente en {CHROMA_DB_PATH}.")

    except Exception as e:
        logger.error(f"Error instalando ChromaDB: {e}", exc_info=True)
        raise
    finally:
        # Limpieza de temporales (no critica si falla).
        try:
            if os.path.exists(tmp_zip):
                os.remove(tmp_zip)
        except OSError:
            pass


# =====================================================
# FUNCION PRINCIPAL
# =====================================================
async def main():
    logger.info("JRS Central Operations Intelligence System - INICIADO en produccion")
    logger.info(f"   Timezone:       {TIMEZONE}")
    logger.info(f"   ChromaDB path:  {CHROMA_DB_PATH}")
    logger.info(f"   Modelo:         {MODELO}")
    logger.info(f"   Ciclo cada:     {SLEEP_BETWEEN_CYCLES_SECONDS}s")

    # Asegurar que el ChromaDB este disponible antes de empezar a procesar.
    asegurar_chromadb()

    consecutive_failures = 0

    while True:
        try:
            logger.info("Buscando correos pendientes...")
            correos = leer_correos_pendientes(max_results=MAX_EMAILS_PER_CYCLE)

            if not correos:
                logger.info("No hay correos pendientes en este ciclo.")
            else:
                if len(correos) == MAX_EMAILS_PER_CYCLE:
                    logger.info(f"{len(correos)} correo(s) procesados...")
                for correo in correos:
                    resultado = procesar_un_correo(correo)
                    logger.info(f"Resultado: {resultado}")

            consecutive_failures = 0  # reset al completar el ciclo con exito

        except KeyboardInterrupt:
            logger.info("Interrupcion manual - cerrando agente.")
            break
        except Exception as e:
            consecutive_failures += 1
            logger.error(
                f"Error en el ciclo ({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}): {e}",
                exc_info=True,
            )
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.critical(
                    f"{MAX_CONSECUTIVE_FAILURES} errores seguidos. Levantando excepcion "
                    "para que Railway reinicie el proceso limpio."
                )
                raise

        logger.info(f"Esperando {SLEEP_BETWEEN_CYCLES_SECONDS} segundos...")
        await asyncio.sleep(SLEEP_BETWEEN_CYCLES_SECONDS)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Al presionar Ctrl+C durante el sleep, asyncio cancela la tarea y
        # la interrupcion llega aqui. La capturamos para salir sin traceback.
        logger.info("Interrupcion manual - cerrando agente.")