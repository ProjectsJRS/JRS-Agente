import os, json, base64
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/drive.readonly',
]

def obtener_servicio():
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build('gmail', 'v1', credentials=creds)

def inspeccionar_payload(payload, nivel=0):
    indent = "  " * nivel
    mime = payload.get('mimeType', 'sin_mime')
    tiene_data = bool(payload.get('body', {}).get('data'))
    size = payload.get('body', {}).get('size', 0)
    partes = payload.get('parts', [])
    print(f"{indent}[{nivel}] mimeType: {mime}")
    print(f"{indent}    body.data: {'SI' if tiene_data else 'NO'} | size: {size}")
    print(f"{indent}    parts: {len(partes)}")
    if tiene_data:
        raw = payload['body']['data']
        texto = base64.urlsafe_b64decode(raw).decode('utf-8', errors='ignore')
        print(f"{indent}    CONTENIDO (primeros 200 chars): {repr(texto[:200])}")
    for i, parte in enumerate(partes):
        print(f"{indent}  -- parte {i} --")
        inspeccionar_payload(parte, nivel + 1)

service = obtener_servicio()
id_etiqueta = None
for lbl in service.users().labels().list(userId='me').execute().get('labels', []):
    if lbl['name'] == 'AI-Agent':
        id_etiqueta = lbl['id']
        break

if not id_etiqueta:
    print("ERROR: No se encontró la etiqueta AI-Agent")
    exit()

mensajes = service.users().messages().list(
    userId='me', labelIds=[id_etiqueta], maxResults=3
).execute().get('messages', [])

if not mensajes:
    print("No hay correos con etiqueta AI-Agent ahora mismo.")
    exit()

for i, m in enumerate(mensajes):
    msg = service.users().messages().get(
        userId='me', id=m['id'], format='full'
    ).execute()
    headers = msg['payload']['headers']
    asunto = next((h['value'] for h in headers if h['name']=='Subject'), '?')
    print(f"\n{'='*60}")
    print(f"CORREO {i+1}: {asunto}")
    print(f"snippet: {msg.get('snippet','')[:100]}")
    print(f"{'='*60}")
    inspeccionar_payload(msg['payload'])