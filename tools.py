# tools.py
# Las 9 herramientas (manos) del agente MCP de JRS
# Version sin decoradores @tool — funciones puras de Python

import os
import base64
from typing import List, Dict, Optional, Annotated
from datetime import datetime
from email.mime.text import MIMEText
from dotenv import load_dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from rag_query import buscar_codigo

load_dotenv()

import logging
logger = logging.getLogger("jrs-agent")

# =====================================================
# CONSTANTES
# =====================================================
ETIQUETA_PENDIENTE = "AI-Agent"
ETIQUETA_PROCESADO = "AI-Procesado"
ETIQUETA_REVISION = "AI-Revisar-Manualmente"

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/drive.readonly',
]

RICHARD_CORPORATIVO = "richard@jrsretailservices.com"
RICHARD_PERSONAL = "richardbodington2@gmail.com"

# =====================================================
# CONEXION A GMAIL
# =====================================================
def obtener_servicio_gmail():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds, cache_discovery=False)


def obtener_id_etiqueta(service, nombre_etiqueta):
    resultados = service.users().labels().list(userId='me').execute()
    etiquetas = resultados.get('labels', [])
    for etiqueta in etiquetas:
        if etiqueta['name'] == nombre_etiqueta:
            return etiqueta['id']
    return None


def extraer_cuerpo_correo(payload):
    """
    Extrae el cuerpo en texto plano navegando recursivamente
    la estructura MIME del correo.
    Orden de preferencia: text/plain > text/html > (sin cuerpo)
    """
    # Caso 1: payload tiene data directo (correos simples sin partes)
    data = payload.get('body', {}).get('data')
    if data:
        return base64.urlsafe_b64decode(
            data.encode('UTF-8')).decode('utf-8', errors='ignore')

    # Caso 2: multipart — buscar recursivamente en las partes
    partes = payload.get('parts', [])

    # Primer intento: text/plain en cualquier nivel
    for parte in partes:
        if parte.get('mimeType') == 'text/plain':
            data = parte.get('body', {}).get('data')
            if data:
                return base64.urlsafe_b64decode(
                    data.encode('UTF-8')).decode('utf-8', errors='ignore')
        # Si la parte es multipart anidada, entrar recursivamente
        if parte.get('mimeType', '').startswith('multipart/'):
            resultado = extraer_cuerpo_correo(parte)
            if resultado and resultado != '(sin cuerpo)':
                return resultado

    # Segundo intento: text/html como respaldo
    for parte in partes:
        if parte.get('mimeType') == 'text/html':
            data = parte.get('body', {}).get('data')
            if data:
                import re
                texto_html = base64.urlsafe_b64decode(
                    data.encode('UTF-8')).decode('utf-8', errors='ignore')
                texto = re.sub(r'<br\s*/?>', '\n', texto_html)
                texto = re.sub(r'</div>', '\n', texto)
                texto = re.sub(r'<[^>]+>', '', texto)
                return texto.strip()

    return '(sin cuerpo)'

# =====================================================
# HERRAMIENTA 1: read_tagged_emails
# =====================================================
def read_tagged_emails(max_results: int = 10) -> dict:
    try:
        service = obtener_servicio_gmail()
        id_etiqueta = obtener_id_etiqueta(service, ETIQUETA_PENDIENTE)
        if not id_etiqueta:
            return {"correos": [], "error": f"Etiqueta '{ETIQUETA_PENDIENTE}' no encontrada"}

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

        return {"correos": correos, "total": len(correos)}

    except Exception as e:
        return {"correos": [], "error": str(e)}


# =====================================================
# HERRAMIENTA 2: classify_email
# =====================================================
def classify_email(subject: str, body: str, sender: str) -> dict:
    texto_completo = f"{subject}\n{body}".lower()
    razones = []
    categoria = "otro"
    cliente_detectado = None
    confianza = 50

    clientes_conocidos = {
        "lenscrafters": ["lenscrafters", "lens crafters", "lc store"],
        "lids": ["lids", "hat store"],
        "target": ["target", "tgt store"],
        "cvs": ["cvs", "cvs pharmacy"],
        "sephora": ["sephora"],
        "h&m": ["h&m", "h and m", "hm store"],
        "best buy": ["best buy", "bestbuy"],
        "walgreens": ["walgreens"],
        "sprouts": ["sprouts"],
        "dollar tree": ["dollar tree"],
    }

    for cliente, keywords in clientes_conocidos.items():
        for kw in keywords:
            if kw in texto_completo:
                cliente_detectado = cliente.title()
                razones.append(f"Mención de cliente: {cliente}")
                break
        if cliente_detectado:
            break

    señales_inspeccion = ["inspector", "city of", "building dept",
                          "code enforcement", "fire marshal", "inspection report"]
    señales_vendor = ["invoice", "po number", "purchase order",
                      "net 30", "quote", "estimate attached"]
    señales_crew = ["crew", "site", "job site", "foreman", "completed tonight",
                    "overnight", "crew leader", "buenas", "jefe", "terminamos"]
    señales_cliente = ["project manager", "facilities manager",
                       "escalation", "punchlist", "per our scope"]

    if any(s in texto_completo for s in señales_inspeccion):
        categoria = "inspeccion"
        confianza = 85
        razones.append("Señales claras de inspección/regulación")
    elif any(s in texto_completo for s in señales_vendor):
        categoria = "vendor"
        confianza = 80
        razones.append("Lenguaje típico de proveedor/facturación")
    elif any(s in texto_completo for s in señales_crew):
        categoria = "crew"
        confianza = 75
        razones.append("Lenguaje de campo/operación nocturna")
    elif any(s in texto_completo for s in señales_cliente) or cliente_detectado:
        categoria = "cliente"
        confianza = 80
        razones.append("Lenguaje corporativo/cliente Fortune 500")
    else:
        razones.append("Sin pistas claras; clasificado como 'otro'")

    return {
        "categoria": categoria,
        "cliente_detectado": cliente_detectado,
        "confianza": confianza,
        "razones": razones,
    }


# =====================================================
# HERRAMIENTA 3: search_drive
# =====================================================
def search_drive(query: str, max_results: int = 5) -> dict:
    try:
        gmail_service = obtener_servicio_gmail()
        creds = gmail_service._http.credentials
        service_drive = build('drive', 'v3', credentials=creds, cache_discovery=False)
        resultados = service_drive.files().list(
            q=f"fullText contains '{query}'",
            pageSize=max_results,
            fields="files(id, name, mimeType, modifiedTime)"
        ).execute()

        archivos = []
        for item in resultados.get('files', []):
            archivos.append({
                'id': item['id'],
                'nombre': item.get('name', ''),
                'tipo': item.get('mimeType', ''),
                'fecha': item.get('modifiedTime', ''),
            })

        return {"archivos": archivos, "total": len(archivos)}

    except Exception as e:
        return {"archivos": [], "error": str(e)}


# =====================================================
# HERRAMIENTA 4: generate_report
# =====================================================
def generate_report(
    project: str,
    location: str,
    client: str,
    shift: str,
    current_status: str,
    work_completed: str,
    work_pending: str,
    issues_detected: str,
    risk_level: str,
    materials_needed: str = "",
    followup_required: str = "",
    photos_needed: str = "",
    compliance_notes: str = "",
    recommended_actions: str = "",
) -> dict:
    risk_level = (risk_level or "MEDIUM").upper()
    icono = {
        "CRITICAL": "CRITICAL",
        "HIGH": "HIGH",
        "MEDIUM": "MEDIUM",
        "LOW": "LOW",
    }.get(risk_level, "MEDIUM")

    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

    reporte = f"""PROJECT INTELLIGENCE REPORT
============================

PROJECT: {project}
LOCATION: {location}
CLIENT: {client}
DATE: {fecha}
SHIFT: {shift}

CURRENT STATUS: {current_status}

WORK COMPLETED: {work_completed}

WORK PENDING: {work_pending}

ISSUES DETECTED: {issues_detected}

RISK LEVEL: {icono}

MATERIALS NEEDED: {materials_needed or 'None reported.'}

FOLLOW-UP REQUIRED: {followup_required or 'None at this time.'}

PHOTOS STILL NEEDED: {photos_needed or 'None at this time.'}

APPLICABLE CODES / COMPLIANCE NOTES: {compliance_notes or 'N/A for this report.'}

RECOMMENDED NEXT ACTIONS: {recommended_actions or 'Awaiting further input.'}

---
Generated by JRS Central Operations Intelligence System
"""
    return {"report": reporte}


# =====================================================
# HERRAMIENTA 5: create_gmail_draft
# =====================================================
def create_gmail_draft(
    original_email_id: str,
    to: str,
    subject: str,
    body: str,
    is_external: bool = True,
) -> dict:
    try:
        service = obtener_servicio_gmail()

        header_obligatorio = (
            "INTERNAL DRAFT - REQUIRES RICHARD'S APPROVAL BEFORE SENDING\n"
            "================================================================\n\n"
        )
        cuerpo_final = (header_obligatorio + body) if is_external else body

        mensaje = MIMEText(cuerpo_final, 'plain', 'utf-8')
        mensaje['to'] = to
        mensaje['subject'] = subject

        raw = base64.urlsafe_b64encode(mensaje.as_bytes()).decode('utf-8')
        borrador = service.users().drafts().create(
            userId='me',
            body={'message': {'raw': raw}}
        ).execute()

        draft_id = borrador.get('id', '')

        label_changed = False
        try:
            id_entrada = obtener_id_etiqueta(service, ETIQUETA_PENDIENTE)
            id_salida = obtener_id_etiqueta(service, ETIQUETA_PROCESADO)
            if id_entrada and id_salida:
                service.users().messages().modify(
                    userId='me',
                    id=original_email_id,
                    body={
                        'removeLabelIds': [id_entrada],
                        'addLabelIds': [id_salida],
                    }
                ).execute()
                label_changed = True
        except Exception as e:
            logger.warning(f"[create_gmail_draft] no se cambió etiqueta: {e}")

        return {
            "draft_id": draft_id,
            "status": "created",
            "label_changed": label_changed,
        }

    except Exception as e:
        return {"draft_id": "", "status": f"error: {e}", "label_changed": False}


# =====================================================
# HERRAMIENTA 6: alert_if_critical
# =====================================================
def alert_if_critical(
    severity: str,
    project: str,
    summary: str,
    detail: str,
) -> dict:
    severity_upper = (severity or "").upper()
    if severity_upper != "CRITICAL":
        return {
            "alert_sent": False,
            "recipients": [],
            "reason": f"Severity {severity_upper} no amerita alerta inmediata",
        }

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    asunto = f"CRITICAL ALERT - {project}"
    cuerpo = f"""CRITICAL ALERT - JRS Central Operations Intelligence System
==================================================================

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
        for destinatario in [RICHARD_CORPORATIVO, RICHARD_PERSONAL]:
            try:
                mensaje = MIMEText(cuerpo, 'plain', 'utf-8')
                mensaje['to'] = destinatario
                mensaje['subject'] = asunto
                raw = base64.urlsafe_b64encode(mensaje.as_bytes()).decode('utf-8')
                service.users().messages().send(
                    userId='me',
                    body={'raw': raw}
                ).execute()
                enviados.append(destinatario)
            except Exception as e:
                logger.error(f"[alert_if_critical] envío a {destinatario}: {e}")
    except Exception as e:
        logger.error(f"[alert_if_critical] conexión Gmail: {e}")

    return {
        "alert_sent": len(enviados) > 0,
        "recipients": enviados,
        "timestamp": timestamp,
    }


# =====================================================
# HERRAMIENTA 7: consult_building_code
# =====================================================
def consult_building_code(
    code_family: str,
    topic: str,
    state: str = "",
) -> dict:
    """
    Consulta el conocimiento técnico de JRS (RAG con ChromaDB).
    """
    resultado = buscar_codigo(
        code_family=code_family,
        topic=topic,
        state=state if state else None,
        n_results=3,
    )

    if not resultado["found"]:
        return {
            "section": "",
            "title": "",
            "text": "No relevant chunks found in the knowledge base for this query.",
            "reference": "",
            "confidence": "low",
            "jurisdiction_note": resultado["jurisdiction_note"],
        }

    # El mejor chunk (primer resultado)
    top = resultado["results"][0]
    meta = top["metadata"]

    family = meta.get("family", code_family).strip()
    year = meta.get("year", "").strip()
    section = resultado["best_section"] or meta.get("section_hint", "").strip()
    title = meta.get("title", "").strip()

    # Construir referencia formal.
    # Evitar duplicar el año cuando la familia ya lo contiene
    # (ej: family="OSHA 1926" + year="1926" -> "OSHA 1926", no "OSHA 1926 1926").
    if year and year in family:
        familia_ref = family          # el año ya está en el nombre de la familia
    elif year:
        familia_ref = f"{family} {year}"
    else:
        familia_ref = family

    if section:
        reference = f"Per {familia_ref}, Section {section}"
    else:
        reference = f"Per {familia_ref}"

    # Combinar los top 3 chunks como texto evidencial (Claude verá esto)
    texto_evidencial = "\n\n---\n\n".join([
        item["text"][:600] for item in resultado["results"][:3]
    ])

    return {
        "section": section,
        "title": title,
        "text": texto_evidencial,
        "reference": reference,
        "confidence": resultado["confidence"],
        "jurisdiction_note": resultado["jurisdiction_note"],
    }


# =====================================================
# HERRAMIENTA 8: verify_compliance
# =====================================================
def verify_compliance(
    observed_value: str,
    standard_reference: str,
    required_value: str,
    context: str = "",
) -> dict:
    import re

    def _extraer_numero(texto):
        m = re.search(r'(\d+(?:\.\d+)?)', texto or "")
        return float(m.group(1)) if m else None

    obs_num = _extraer_numero(observed_value)
    req_num = _extraer_numero(required_value)
    es_minimo = "min" in (required_value or "").lower()
    es_maximo = "max" in (required_value or "").lower()

    status = "needs-review"
    gap = ""
    recomendacion = ""
    explicacion = ""

    if obs_num is not None and req_num is not None:
        if es_minimo:
            if obs_num >= req_num:
                status = "compliant"
                explicacion = f"Observed {observed_value} meets minimum {required_value} per {standard_reference}."
            else:
                status = "non-compliant"
                gap = f"{req_num - obs_num} units below minimum"
                recomendacion = f"Increase to at least {required_value} per {standard_reference}."
                explicacion = f"Observed {observed_value} is below required {required_value}."
        elif es_maximo:
            if obs_num <= req_num:
                status = "compliant"
                explicacion = f"Observed {observed_value} is within maximum {required_value}."
            else:
                status = "non-compliant"
                gap = f"{obs_num - req_num} units above maximum"
                recomendacion = f"Reduce to at most {required_value} per {standard_reference}."
                explicacion = f"Observed {observed_value} exceeds maximum {required_value}."
        else:
            if abs(obs_num - req_num) < 0.01:
                status = "compliant"
                explicacion = "Observed value matches required value."
            else:
                status = "non-compliant"
                gap = f"differs by {abs(obs_num - req_num)} units"
                explicacion = f"Observed {observed_value} does not match {required_value}."
    else:
        explicacion = "Unable to extract numeric values. Manual review recommended."
        recomendacion = "Escalate to Richard for manual verification."

    return {
        "status": status,
        "gap": gap,
        "recommendation": recomendacion,
        "explanation": explicacion,
    }


# =====================================================
# HERRAMIENTA 9: cite_applicable_standard
# =====================================================
def cite_applicable_standard(
    code_family: str,
    year: str,
    section: str,
    topic: str,
    state: str = "",
) -> dict:
    code_family = (code_family or "").strip()
    year = (year or "").strip()
    section = (section or "").strip()

    if not code_family or not section:
        return {
            "citation": (
                "[Citation incomplete — code_family and section are required. "
                "Verify against current local code adoption.]"
            )
        }

    principal = f"Per {code_family} {year}, Section {section}" if year else f"Per {code_family}, Section {section}"
    if topic:
        principal += f" ({topic})"
    principal += "."

    nota = f" Note: verify local adoption in {state}." if state else " Note: verify local adoption in the applicable jurisdiction."

    return {"citation": principal + nota}
