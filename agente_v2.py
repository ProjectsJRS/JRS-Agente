# agente_v2.py
# Agente JRS Central Operations Intelligence System - Fase 3
# Lee correos con etiqueta AI-Agent, los procesa con Claude,
# crea borradores en Gmail con el Project Intelligence Report,
# y cambia las etiquetas a AI-Procesado.
#
# REGLA DE ORO: este agente solo CREA borradores. NUNCA envía correos automáticamente.
 
import os
import base64
from email.mime.text import MIMEText
 
from dotenv import load_dotenv
from anthropic import Anthropic
 
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
 
# ============================================================
# CONFIGURACIÓN
# ============================================================
 
load_dotenv()
 
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
MODELO_CLAUDE = 'claude-opus-4-7'
MAX_TOKENS_CLAUDE = 4096
 
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/drive.readonly',
]
 
ETIQUETA_ENTRADA = 'AI-Agent'
ETIQUETA_SALIDA = 'AI-Procesado'
 
MAX_CORREOS_POR_CORRIDA = 10
 
# Cargar el System Prompt desde archivo
with open('system_prompt.txt', 'r', encoding='utf-8') as f:
    SYSTEM_PROMPT = f.read()
 
# ============================================================
# AUTENTICACIÓN CON GOOGLE
# ============================================================
 
def autenticar_google():
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
    return creds
 
# ============================================================
# GESTIÓN DE ETIQUETAS
# ============================================================
 
def obtener_id_etiqueta(service, nombre_etiqueta):
    resultados = service.users().labels().list(userId='me').execute()
    etiquetas = resultados.get('labels', [])
    for etiqueta in etiquetas:
        if etiqueta['name'] == nombre_etiqueta:
            return etiqueta['id']
    return None
 
def cambiar_etiquetas(service, id_correo, id_quitar, id_agregar):
    """
    Quita una etiqueta y agrega otra al mismo correo.
    """
    service.users().messages().modify(
        userId='me',
        id=id_correo,
        body={
            'removeLabelIds': [id_quitar],
            'addLabelIds': [id_agregar],
        }
    ).execute()
 
# ============================================================
# LECTURA DE CORREOS
# ============================================================
 
def extraer_cuerpo_correo(payload):
    """
    Extrae el cuerpo del correo en texto plano.
    Gmail devuelve los correos en base64, hay que decodificarlos.
    """
    if 'body' in payload and 'data' in payload['body'] and payload['body']['data']:
        data = payload['body']['data']
        texto = base64.urlsafe_b64decode(data.encode('UTF-8')).decode('utf-8', errors='ignore')
        return texto
 
    if 'parts' in payload:
        for parte in payload['parts']:
            if parte.get('mimeType') == 'text/plain':
                data = parte['body'].get('data')
                if data:
                    return base64.urlsafe_b64decode(data.encode('UTF-8')).decode('utf-8', errors='ignore')
        # Si no hay text/plain, intentar con HTML
        for parte in payload['parts']:
            if parte.get('mimeType') == 'text/html':
                data = parte['body'].get('data')
                if data:
                    return base64.urlsafe_b64decode(data.encode('UTF-8')).decode('utf-8', errors='ignore')
 
    return '(sin cuerpo)'
 
def leer_correo_completo(service, id_correo):
    msg = service.users().messages().get(
        userId='me', id=id_correo, format='full'
    ).execute()
    headers = msg['payload']['headers']
    asunto = next((h['value'] for h in headers if h['name'] == 'Subject'), '(sin asunto)')
    remitente = next((h['value'] for h in headers if h['name'] == 'From'), '(sin remitente)')
    fecha = next((h['value'] for h in headers if h['name'] == 'Date'), '')
    cuerpo = extraer_cuerpo_correo(msg['payload'])
    return {
        'id': id_correo,
        'asunto': asunto,
        'remitente': remitente,
        'fecha': fecha,
        'cuerpo': cuerpo,
    }
 
def listar_correos_con_etiqueta(service, id_etiqueta, max_resultados):
    resultados = service.users().messages().list(
        userId='me',
        labelIds=[id_etiqueta],
        maxResults=max_resultados,
    ).execute()
    return resultados.get('messages', [])
 
# ============================================================
# LLAMADA A CLAUDE
# ============================================================
 
def generar_intelligence_report(correo):
    """
    Manda el correo a Claude y devuelve el Project Intelligence Report.
    """
    cliente = Anthropic(api_key=ANTHROPIC_API_KEY)
 
    mensaje_usuario = (
        f'Se recibió el siguiente correo en projects@jrsretailservices.com '
        f'con la etiqueta AI-Agent. Genera el Project Intelligence Report '
        f'siguiendo el formato estándar.\n\n'
        f'De: {correo["remitente"]}\n'
        f'Fecha: {correo["fecha"]}\n'
        f'Asunto: {correo["asunto"]}\n\n'
        f'Cuerpo del correo:\n{correo["cuerpo"]}\n'
    )
 
    respuesta = cliente.messages.create(
        model=MODELO_CLAUDE,
        max_tokens=MAX_TOKENS_CLAUDE,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': mensaje_usuario}],
    )
 
    return respuesta.content[0].text
 
# ============================================================
# CREACIÓN DEL BORRADOR EN GMAIL
# ============================================================
 
def crear_borrador(service, correo_original, reporte):
    """
    Crea un borrador en Gmail con el Project Intelligence Report.
    El borrador NO se envía. Queda en la carpeta de Borradores.
    """
    cuerpo_borrador = (
        f'INTERNAL DRAFT — REQUIRES RICHARD\'S APPROVAL BEFORE SENDING\n'
        f'(Borrador generado automáticamente por el agente. NO enviar sin revisar.)\n'
        f'\n'
        f'=== Project Intelligence Report ===\n'
        f'\n'
        f'{reporte}\n'
        f'\n'
        f'=== Correo original ===\n'
        f'De: {correo_original["remitente"]}\n'
        f'Asunto: {correo_original["asunto"]}\n'
        f'Fecha: {correo_original["fecha"]}\n'
    )
 
    # Construir el mensaje MIME
    mensaje = MIMEText(cuerpo_borrador, 'plain', 'utf-8')
    mensaje['to'] = 'richard@jrsretailservices.com'
    mensaje['subject'] = f'[AGENTE] Intelligence Report - {correo_original["asunto"]}'
 
    # Codificar el mensaje en base64 (Gmail lo requiere)
    raw = base64.urlsafe_b64encode(mensaje.as_bytes()).decode('utf-8')
 
    borrador = service.users().drafts().create(
        userId='me',
        body={'message': {'raw': raw}}
    ).execute()
 
    return borrador['id']
 
# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================
 
def main():
    print('=' * 60)
    print('JRS Agente MCP v2.0 - Procesamiento de correos')
    print('=' * 60)
 
    # 1. Autenticación
    print('\n[1] Autenticando con Google...')
    creds = autenticar_google()
    service = build('gmail', 'v1', credentials=creds)
    print('    Conectado a Gmail.')
 
    # 2. Obtener IDs de etiquetas
    print('\n[2] Obteniendo IDs de etiquetas...')
    id_entrada = obtener_id_etiqueta(service, ETIQUETA_ENTRADA)
    id_salida = obtener_id_etiqueta(service, ETIQUETA_SALIDA)
 
    if not id_entrada or not id_salida:
        print(f'    ERROR: faltan etiquetas. Crea AI-Agent y AI-Procesado en Gmail.')
        return
    print(f'    AI-Agent: {id_entrada}')
    print(f'    AI-Procesado: {id_salida}')
 
    # 3. Listar correos por procesar
    print(f'\n[3] Buscando correos con etiqueta {ETIQUETA_ENTRADA}...')
    correos_pendientes = listar_correos_con_etiqueta(service, id_entrada, MAX_CORREOS_POR_CORRIDA)
 
    if not correos_pendientes:
        print('    No hay correos por procesar. Salida.')
        return
    print(f'    {len(correos_pendientes)} correo(s) por procesar.')
 
    # 4. Procesar cada correo
    procesados = 0
    errores = 0
 
    for i, mensaje in enumerate(correos_pendientes, start=1):
        print(f'\n[{i}/{len(correos_pendientes)}] Procesando correo {mensaje["id"]}...')
 
        try:
            # 4a. Leer contenido completo
            correo = leer_correo_completo(service, mensaje['id'])
            print(f'        Asunto: {correo["asunto"][:80]}')
 
            # 4b. Generar reporte con Claude
            print('        Generando Intelligence Report con Claude...')
            reporte = generar_intelligence_report(correo)
 
            # 4c. Crear borrador
            print('        Creando borrador en Gmail...')
            id_borrador = crear_borrador(service, correo, reporte)
            print(f'        Borrador creado: {id_borrador}')
 
            # 4d. Cambiar etiquetas
            print('        Cambiando etiquetas...')
            cambiar_etiquetas(service, correo['id'], id_entrada, id_salida)
 
            procesados += 1
            print('        OK.')
 
        except Exception as e:
            errores += 1
            print(f'        ERROR al procesar: {e}')
 
    # 5. Reporte final
    print('\n' + '=' * 60)
    print(f'Procesados exitosamente: {procesados}')
    print(f'Errores: {errores}')
    print('=' * 60)
 
if __name__ == '__main__':
    main()
