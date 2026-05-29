# agente_v1.py
# Primera version del agente - JRS Central Operations
 
import os
from dotenv import load_dotenv
from anthropic import Anthropic
 
# Cargar la API Key desde el .env
load_dotenv()
api_key = os.getenv("ANTHROPIC_API_KEY")
cliente = Anthropic(api_key=api_key)
 
# Leer el System Prompt desde el archivo de texto
with open("system_prompt.txt", "r", encoding="utf-8") as archivo:
    system_prompt = archivo.read()
 
# El correo de campo a analizar (por ahora, escrito aqui)
correo_de_campo = """

05/06 - Client: Perfumania (Day 5)
Adress: Mc Allen, TX
Store: 4100

-

Daily Work Summary:
• Flooring: Transition metal profiles were sourced from Floor & Decor and installed along the floating floor edge, delivering a clean, code-compliant finish.
• Low-Voltage Coordination: The cable installation team was received and guided on the layout and quantity of pre-installed electrical boxes.
• Fire Sprinkler System: A certified technician performed the required system modifications.
• Site Conditioning:Old baseboards were removed and a full general cleaning was completed, leaving the jobsite organized for upcoming work.

The project continues to advance on track.

Best regards

–•JRS Attend check:
1- Mauricio Siso
2- Doreyvins Varela
3- Gilberto Buitrago
4- German Calatraba


"""
 
# Enviar al agente: System Prompt + el correo
respuesta = cliente.messages.create(
    model="claude-opus-4-7",
    max_tokens=1500,
    system=system_prompt,
    messages=[
        {"role": "user", "content": correo_de_campo}
    ]
)
 
# Mostrar el Project Intelligence Report
print(respuesta.content[0].text)
