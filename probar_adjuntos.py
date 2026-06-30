# probar_adjuntos.py
# -------------------------------------------------------------------
# Script de AISLAMIENTO: prueba SOLO la lectura de adjuntos de los
# correos etiquetados con AI-Agent.
#
# Reutiliza las funciones reales de tools.py (no duplica logica).
# NO llama a Claude, NO crea borradores y NO cambia etiquetas:
# unicamente lee e imprime. Es seguro correrlo las veces que quieras.
#
# Uso:   python probar_adjuntos.py
# -------------------------------------------------------------------

from tools import (
    obtener_servicio_gmail,
    obtener_id_etiqueta,
    listar_adjuntos,
    extraer_texto_de_adjuntos,
    ETIQUETA_PENDIENTE,
)

# Cuantos correos revisar y cuanto texto de cada adjunto mostrar en pantalla.
MAX_CORREOS = 5
LIMITE_CHARS_PREVIEW = 1500


def main():
    print("=" * 60)
    print("PRUEBA DE LECTURA DE ADJUNTOS — JRS")
    print("=" * 60)

    # 1) Conectar a Gmail (usa tu token.json local)
    print("\n[1] Conectando a Gmail...")
    service = obtener_servicio_gmail()
    print("    Conectado.")

    # 2) Buscar correos con la etiqueta AI-Agent
    print(f"\n[2] Buscando correos con etiqueta '{ETIQUETA_PENDIENTE}'...")
    id_etiqueta = obtener_id_etiqueta(service, ETIQUETA_PENDIENTE)
    if not id_etiqueta:
        print(f"    ERROR: no existe la etiqueta '{ETIQUETA_PENDIENTE}' en Gmail.")
        return

    resultados = service.users().messages().list(
        userId="me", labelIds=[id_etiqueta], maxResults=MAX_CORREOS
    ).execute()
    mensajes = resultados.get("messages", [])

    if not mensajes:
        print("    No hay correos con esa etiqueta ahora mismo.")
        print("    Tip: ponle la etiqueta AI-Agent al correo del SOW de Richard")
        print("         y vuelve a correr este script.")
        return
    print(f"    {len(mensajes)} correo(s) encontrado(s).")

    # 3) Por cada correo: mostrar adjuntos detectados y el texto extraido
    for i, m in enumerate(mensajes, start=1):
        msg = service.users().messages().get(
            userId="me", id=m["id"], format="full"
        ).execute()

        headers = msg["payload"]["headers"]
        asunto = next((h["value"] for h in headers if h["name"] == "Subject"), "(sin asunto)")
        remitente = next((h["value"] for h in headers if h["name"] == "From"), "(sin remitente)")

        print("\n" + "=" * 60)
        print(f"CORREO {i}: {asunto}")
        print(f"De: {remitente}")
        print("=" * 60)

        # 3a) Que adjuntos trae (nombre + tipo)
        adjuntos = listar_adjuntos(msg["payload"])
        if not adjuntos:
            print("  Sin adjuntos. (Este correo no tiene archivos pegados.)")
            continue
        print(f"  Adjuntos detectados: {len(adjuntos)}")
        for a in adjuntos:
            print(f"    - {a['filename']}  ({a['mimeType']})")

        # 3b) El texto que el agente le pasaria a Claude
        print("\n  --- TEXTO EXTRAIDO DE LOS ADJUNTOS ---")
        texto = extraer_texto_de_adjuntos(service, m["id"], msg["payload"])
        if not texto.strip():
            print("  (No se extrajo texto. Revisa las notas de arriba: puede ser")
            print("   un escaneo/imagen o un tipo de archivo no soportado.)")
        else:
            print(texto[:LIMITE_CHARS_PREVIEW])
            sobrantes = len(texto) - LIMITE_CHARS_PREVIEW
            if sobrantes > 0:
                print(f"\n  [... {sobrantes} caracteres mas omitidos en esta vista ...]")

    print("\n" + "=" * 60)
    print("FIN DE LA PRUEBA")
    print("Si arriba ves los specs del SOW (LVT, pintura Pashima, plafones")
    print("Armstrong, etc.), el agente ya esta leyendo los adjuntos bien.")
    print("=" * 60)


if __name__ == "__main__":
    main()
