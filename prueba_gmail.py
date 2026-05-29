# prueba_gmail.py
# Primer script que se conecta a Gmail corporativo de JRS y lee correos con etiqueta AI-Agent.
# Este script es solo de VERIFICACIÓN. No procesa los correos con Claude ni crea borradores.
# JRS Central Operations Intelligence System - Fase 3 - Mayo 2026
 
import os.path
import base64
 
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
 
# ============================================================
# CONFIGURACIÓN
# ============================================================
 
# Los 3 permisos que la app va a solicitar a Google.
# DEBEN ser EXACTAMENTE los mismos que configuraste en el OAuth Consent Screen.
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/drive.readonly',
]
 
# Nombre exacto de la etiqueta que el agente va a procesar.
ETIQUETA_AGENTE = 'AI-Agent'
 
# ============================================================
# FUNCIÓN: AUTENTICAR CON GOOGLE
# ============================================================
 
def autenticar():
    """
    Se autentica con Google usando OAuth.
    La primera vez abre el navegador para que autorices.
    Después guarda un token.json que reutiliza en siguientes corridas.
    """
    creds = None
 
    # Si ya existe un token guardado, lo cargamos.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
 
    # Si no hay credenciales válidas, hay que autenticar de nuevo.
    if not creds or not creds.valid:
        # Si están expiradas pero hay refresh_token, las renovamos.
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Primera vez: abre el navegador para autorizar.
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
 
        # Guarda las credenciales para la próxima ejecución.
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
 
    return creds
 
# ============================================================
# FUNCIÓN: BUSCAR EL ID DE LA ETIQUETA AI-AGENT
# ============================================================
 
def obtener_id_etiqueta(service, nombre_etiqueta):
    """
    Gmail no usa los nombres de las etiquetas en las búsquedas, usa IDs internos.
    Esta función traduce el nombre 'AI-Agent' a su ID interno.
    """
    resultados = service.users().labels().list(userId='me').execute()
    etiquetas = resultados.get('labels', [])
 
    for etiqueta in etiquetas:
        if etiqueta['name'] == nombre_etiqueta:
            return etiqueta['id']
 
    return None  # La etiqueta no existe
 
# ============================================================
# FUNCIÓN: LEER CORREOS CON ETIQUETA AI-AGENT
# ============================================================
 
def leer_correos_etiquetados(service, id_etiqueta, max_resultados=5):
    """
    Lee los correos que tienen la etiqueta dada.
    Devuelve una lista con asunto, remitente, y primer fragmento del cuerpo.
    """
    resultados = service.users().messages().list(
        userId='me',
        labelIds=[id_etiqueta],
        maxResults=max_resultados
    ).execute()
 
    mensajes = resultados.get('messages', [])
    correos_procesados = []
 
    for mensaje in mensajes:
        msg = service.users().messages().get(
            userId='me',
            id=mensaje['id'],
            format='full'
        ).execute()
 
        # Extraer asunto y remitente de los headers
        headers = msg['payload']['headers']
        asunto = next((h['value'] for h in headers if h['name'] == 'Subject'), '(sin asunto)')
        remitente = next((h['value'] for h in headers if h['name'] == 'From'), '(sin remitente)')
 
        # Extraer fragmento corto del cuerpo (snippet)
        fragmento = msg.get('snippet', '(sin contenido)')
 
        correos_procesados.append({
            'id': mensaje['id'],
            'asunto': asunto,
            'remitente': remitente,
            'fragmento': fragmento,
        })
 
    return correos_procesados
 
# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================
 
def main():
    print('=' * 60)
    print('JRS Agente MCP - Prueba de conexión a Gmail')
    print('=' * 60)
 
    try:
        # Paso 1: autenticar
        print('\n[1/4] Autenticando con Google...')
        creds = autenticar()
        print('       Autenticación exitosa.')
 
        # Paso 2: construir el servicio de Gmail
        print('\n[2/4] Conectando a Gmail API...')
        service = build('gmail', 'v1', credentials=creds)
        print('       Conexión a Gmail establecida.')
 
        # Paso 3: buscar el ID de la etiqueta AI-Agent
        print(f'\n[3/4] Buscando etiqueta "{ETIQUETA_AGENTE}"...')
        id_etiqueta = obtener_id_etiqueta(service, ETIQUETA_AGENTE)
 
        if id_etiqueta is None:
            print(f'       ERROR: la etiqueta "{ETIQUETA_AGENTE}" no existe en Gmail.')
            print('       Crea la etiqueta en Gmail antes de correr este script.')
            return
 
        print(f'       Etiqueta encontrada. ID interno: {id_etiqueta}')
 
        # Paso 4: leer los correos con esa etiqueta
        print(f'\n[4/4] Leyendo correos con etiqueta "{ETIQUETA_AGENTE}"...')
        correos = leer_correos_etiquetados(service, id_etiqueta, max_resultados=5)
 
        if not correos:
            print('       No hay correos con esa etiqueta.')
            print('       Mándate correos de prueba y aplícales la etiqueta AI-Agent.')
            return
 
        print(f'       Se encontraron {len(correos)} correo(s).')
        print('\n' + '=' * 60)
        print('CORREOS ENCONTRADOS:')
        print('=' * 60)
 
        for i, correo in enumerate(correos, start=1):
            print(f'\n--- Correo #{i} ---')
            print(f'ID: {correo["id"]}')
            print(f'De: {correo["remitente"]}')
            print(f'Asunto: {correo["asunto"]}')
            print(f'Fragmento: {correo["fragmento"][:200]}...')
 
        print('\n' + '=' * 60)
        print('PRUEBA COMPLETADA EXITOSAMENTE')
        print('=' * 60)
 
    except HttpError as error:
        print(f'Error de Gmail API: {error}')
    except Exception as e:
        print(f'Error inesperado: {e}')
 
if __name__ == '__main__':
    main()