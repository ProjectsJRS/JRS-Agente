# agent.py
# El agente MCP de JRS — Agent Loop principal
# Version sin claude_agent_sdk — usa Anthropic API directamente

import os
import json
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv
import anthropic

from whitelist import verify_sender
from tools import (
    obtener_servicio_gmail,
    obtener_id_etiqueta,
    extraer_cuerpo_correo,
)
from client_protocols import get_protocol

load_dotenv()

# =====================================================
# CONFIGURACION DE LOGGING
# =====================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('agent.log', encoding='utf-8'),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger("jrs-agent")

# =====================================================
# CONSTANTES
# =====================================================
MAX_ITERATIONS_PER_EMAIL = 20
SLEEP_BETWEEN_CYCLES_SECONDS = 300
MAX_EMAILS_PER_CYCLE = 10
MODELO = "claude-opus-4-8"

# =====================================================
# CARGAR EL SYSTEM PROMPT
# =====================================================
with open("system_prompt.txt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

# =====================================================
# CLIENTE ANTHROPIC
# =====================================================
cliente = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

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
    Recibe el nombre de una herramienta y sus parametros,
    ejecuta la logica correspondiente, y devuelve el resultado como string JSON.
    """
    import base64
    import re
    from email.mime.text import MIMEText
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    SCOPES = [
        'https://www.googleapis.com/auth/gmail.modify',
        'https://www.googleapis.com/auth/gmail.compose',
        'https://www.googleapis.com/auth/drive.readonly',
    ]

    if nombre == "classify_email":
        subject = parametros.get("subject", "")
        body = parametros.get("body", "")
        sender = parametros.get("sender", "")
        texto = f"{subject}\n{body}".lower()

        clientes_conocidos = {
            "lenscrafters": ["lenscrafters", "lens crafters"],
            "lids": ["lids", "hat store"],
            "target": ["target", "tgt store"],
            "cvs": ["cvs pharmacy", "cvs"],
            "sephora": ["sephora"],
            "h&m": ["h&m", "h and m"],
            "best buy": ["best buy", "bestbuy"],
            "walgreens": ["walgreens"],
            "sprouts": ["sprouts"],
            "dollar tree": ["dollar tree"],
        }

        cliente_detectado = None
        for cliente, keywords in clientes_conocidos.items():
            for kw in keywords:
                if kw in texto:
                    cliente_detectado = cliente.title()
                    break
            if cliente_detectado:
                break

        categoria = "otro"
        if any(s in texto for s in ["inspector", "city of", "building dept", "fire marshal"]):
            categoria = "inspeccion"
        elif any(s in texto for s in ["invoice", "po number", "purchase order", "net 30"]):
            categoria = "vendor"
        elif any(s in texto for s in ["crew", "job site", "foreman", "overnight", "buenas", "jefe", "terminamos"]):
            categoria = "crew"
        elif any(s in texto for s in ["project manager", "facilities", "punchlist"]) or cliente_detectado:
            categoria = "cliente"

        return json.dumps({
            "categoria": categoria,
            "cliente_detectado": cliente_detectado,
            "confianza": 80,
        })

    elif nombre == "search_drive":
        query = parametros.get("query", "")
        max_results = parametros.get("max_results", 5)
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            service_drive = build('drive', 'v3', credentials=creds)
            resultados = service_drive.files().list(
                q=f"fullText contains '{query}'",
                pageSize=max_results,
                fields="files(id, name, mimeType, modifiedTime)"
            ).execute()
            archivos = [
                {"nombre": f.get("name"), "tipo": f.get("mimeType")}
                for f in resultados.get("files", [])
            ]
            return json.dumps({"archivos": archivos, "total": len(archivos)})
        except Exception as e:
            return json.dumps({"archivos": [], "error": str(e)})

    elif nombre == "generate_report":
        risk_level = (parametros.get("risk_level") or "MEDIUM").upper()
        iconos = {"CRITICAL": "CRITICAL", "HIGH": "HIGH", "MEDIUM": "MEDIUM", "LOW": "LOW"}
        nivel = iconos.get(risk_level, "MEDIUM")
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        reporte = f"""PROJECT INTELLIGENCE REPORT
============================

PROJECT: {parametros.get('project', '')}
LOCATION: {parametros.get('location', '')}
CLIENT: {parametros.get('client', '')}
DATE: {fecha}
SHIFT: {parametros.get('shift', '')}

CURRENT STATUS: {parametros.get('current_status', '')}

WORK COMPLETED: {parametros.get('work_completed', '')}

WORK PENDING: {parametros.get('work_pending', '')}

ISSUES DETECTED: {parametros.get('issues_detected', '')}

RISK LEVEL: {nivel}

MATERIALS NEEDED: {parametros.get('materials_needed') or 'None reported.'}

FOLLOW-UP REQUIRED: {parametros.get('followup_required') or 'None at this time.'}

PHOTOS STILL NEEDED: {parametros.get('photos_needed') or 'None at this time.'}

APPLICABLE CODES / COMPLIANCE NOTES: {parametros.get('compliance_notes') or 'N/A for this report.'}

RECOMMENDED NEXT ACTIONS: {parametros.get('recommended_actions') or 'Awaiting further input.'}

---
Generated by JRS Central Operations Intelligence System
"""
        return json.dumps({"report": reporte})

    elif nombre == "create_gmail_draft":
        original_email_id = parametros.get("original_email_id", "")
        to = parametros.get("to", "")
        subject = parametros.get("subject", "")
        body = parametros.get("body", "")
        is_external = parametros.get("is_external", True)

        try:
            service = obtener_servicio_gmail()
            header = (
                "INTERNAL DRAFT - REQUIRES RICHARD'S APPROVAL BEFORE SENDING\n"
                "================================================================\n\n"
            )
            cuerpo_final = (header + body) if is_external else body

            mensaje = MIMEText(cuerpo_final, 'plain', 'utf-8')
            mensaje['to'] = to
            mensaje['subject'] = subject
            raw = base64.urlsafe_b64encode(mensaje.as_bytes()).decode('utf-8')

            borrador = service.users().drafts().create(
                userId='me',
                body={'message': {'raw': raw}}
            ).execute()
            draft_id = borrador.get('id', '')

            # Cambiar etiquetas
            id_entrada = obtener_id_etiqueta(service, "AI-Agent")
            id_salida = obtener_id_etiqueta(service, "AI-Procesado")
            if id_entrada and id_salida and original_email_id:
                service.users().messages().modify(
                    userId='me',
                    id=original_email_id,
                    body={
                        'removeLabelIds': [id_entrada],
                        'addLabelIds': [id_salida],
                    }
                ).execute()

            logger.info(f"Borrador creado: {draft_id}")
            return json.dumps({"draft_id": draft_id, "status": "created"})

        except Exception as e:
            logger.error(f"Error creando borrador: {e}")
            return json.dumps({"draft_id": "", "status": f"error: {e}"})

    elif nombre == "alert_if_critical":
        severity = (parametros.get("severity") or "").upper()
        if severity != "CRITICAL":
            return json.dumps({"alert_sent": False, "reason": f"Severity {severity} no es CRITICAL"})

        project = parametros.get("project", "")
        summary = parametros.get("summary", "")
        detail = parametros.get("detail", "")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        asunto = f"CRITICAL ALERT - {project}"
        cuerpo = f"""CRITICAL ALERT - JRS Central Operations Intelligence System

Time: {timestamp}
Project: {project}

SUMMARY: {summary}

DETAIL: {detail}

This is an automated CRITICAL severity alert.
Action required from operations leadership.
"""
        enviados = []
        try:
            service = obtener_servicio_gmail()
            for destinatario in ["richard@jrsretailservices.com", "richardbodington2@gmail.com"]:
                try:
                    mensaje = MIMEText(cuerpo, 'plain', 'utf-8')
                    mensaje['to'] = destinatario
                    mensaje['subject'] = asunto
                    raw = base64.urlsafe_b64encode(mensaje.as_bytes()).decode('utf-8')
                    service.users().messages().send(
                        userId='me', body={'raw': raw}
                    ).execute()
                    enviados.append(destinatario)
                except Exception as e:
                    logger.error(f"Error enviando alerta a {destinatario}: {e}")
        except Exception as e:
            logger.error(f"Error conectando Gmail para alerta: {e}")

        return json.dumps({"alert_sent": len(enviados) > 0, "recipients": enviados})

    elif nombre == "consult_building_code":
        code_family = (parametros.get("code_family") or "").upper()
        topic = (parametros.get("topic") or "").upper()
        state = (parametros.get("state") or "").upper()

        base = {
            "IBC:GROUP M": {"section": "303.4", "reference": "Per IBC 2024, Section 303.4", "text": "Group M: mercantile occupancy, retail stores."},
            "IBC:CEILING HEIGHT": {"section": "1003.2", "reference": "Per IBC 2024, Section 1003.2", "text": "Minimum ceiling height 7 ft 6 in for occupied spaces."},
            "ADA:DOOR OPENING": {"section": "404.2.3", "reference": "Per 2010 ADA Standards, Section 404.2.3", "text": "Clear width 32 in minimum."},
            "NFPA-101:EXIT SIGNS": {"section": "7.10", "reference": "Per NFPA 101 (2024), Section 7.10", "text": "Exits shall be marked by approved signs."},
            "OSHA-1926:FALL PROTECTION": {"section": "1926.501", "reference": "Per OSHA 29 CFR 1926.501", "text": "Fall protection required at 6 feet above lower level."},
        }

        for clave, datos in base.items():
            familia, tema = clave.split(":", 1)
            if code_family == familia and tema in topic:
                return json.dumps({**datos, "confidence": "medium",
                                   "jurisdiction_note": f"Verify local adoption in {state}." if state else "Verify local adoption."})

        return json.dumps({"section": "", "text": f"No reference found for {code_family} on '{topic}'. Verify manually.", "confidence": "low"})

    elif nombre == "verify_compliance":
        observed = parametros.get("observed_value", "")
        required = parametros.get("required_value", "")
        reference = parametros.get("standard_reference", "")

        def extraer(texto):
            m = re.search(r'(\d+(?:\.\d+)?)', texto or "")
            return float(m.group(1)) if m else None

        obs = extraer(observed)
        req = extraer(required)
        es_min = "min" in required.lower()

        if obs is not None and req is not None:
            if es_min:
                status = "compliant" if obs >= req else "non-compliant"
            else:
                status = "compliant" if obs <= req else "non-compliant"
        else:
            status = "needs-review"

        return json.dumps({"status": status, "observed": observed, "required": required, "reference": reference})

    elif nombre == "cite_applicable_standard":
        code_family = parametros.get("code_family", "")
        year = parametros.get("year", "")
        section = parametros.get("section", "")
        topic = parametros.get("topic", "")
        state = parametros.get("state", "")

        cita = f"Per {code_family} {year}, Section {section} ({topic})."
        nota = f" Note: verify local adoption in {state}." if state else " Note: verify local adoption in the applicable jurisdiction."
        return json.dumps({"citation": cita + nota})

    else:
        return json.dumps({"error": f"Herramienta desconocida: {nombre}"})


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
                max_tokens=4096,
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
# FUNCION PRINCIPAL
# =====================================================
async def main():
    logger.info("JRS Central Operations Intelligence System - INICIADO")

    while True:
        try:
            logger.info("Buscando correos pendientes...")
            correos = leer_correos_pendientes(max_results=MAX_EMAILS_PER_CYCLE)

            if not correos:
                logger.info("No hay correos pendientes en este ciclo.")
            else:
                logger.info(f"{len(correos)} correo(s) por procesar.")
                for correo in correos:
                    resultado = procesar_un_correo(correo)
                    logger.info(f"Resultado: {resultado}")

        except KeyboardInterrupt:
            logger.info("Interrupcion manual - cerrando agente.")
            break
        except Exception as e:
            logger.error(f"Error inesperado en el bucle principal: {e}")

        logger.info(f"Esperando {SLEEP_BETWEEN_CYCLES_SECONDS} segundos...")
        await asyncio.sleep(SLEEP_BETWEEN_CYCLES_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())