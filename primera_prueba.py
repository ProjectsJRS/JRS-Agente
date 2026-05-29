# primera_prueba.py
# Primer contacto con Claude - JRS Central Operations
 
import os
from dotenv import load_dotenv
from anthropic import Anthropic
 
# Cargar las variables del archivo .env
load_dotenv()
 
# Leer la API Key desde el entorno
api_key = os.getenv("ANTHROPIC_API_KEY")
 
# Crear el cliente de Anthropic (el 'mesero')
cliente = Anthropic(api_key=api_key)
 
# Enviar un mensaje a Claude
respuesta = cliente.messages.create(
    model="claude-opus-4-7",
    max_tokens=500,
    messages=[
        {"role": "user", "content": "Hola Claude. Responde en espanol: en una frase, que es JRS Retail Services?"}
    ]
)
 
# Mostrar la respuesta en pantalla
print(respuesta.content[0].text)
