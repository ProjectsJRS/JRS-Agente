#!/usr/bin/env python3
# generar_config.py
# Genera config.yaml para la autenticacion del dashboard (Streamlit-Authenticator 0.4.2).
#
# - Pide la contrasena de cada usuario de forma OCULTA (getpass) — nunca se
#   escribe ni se guarda en texto plano.
# - Hashea con bcrypt (compatible al 100% con streamlit-authenticator, que usa
#   bcrypt.hashpw/checkpw por dentro). No requiere streamlit para correr.
# - Genera una cookie key aleatoria.
#
# USO:  python generar_config.py
# Resultado: crea config.yaml en la carpeta actual.
# IMPORTANTE: config.yaml NO debe subir a git (repo publico). Va al .gitignore.

import os
import sys
import secrets
import getpass

import bcrypt
import yaml

# --- Edita aqui los 4 usuarios (username, nombre, apellido, email) ---
# El login se hace por USERNAME. Ajusta emails si hace falta.
USUARIOS = [
    {"username": "richard",  "first_name": "Richard",  "last_name": "Bodington", "email": "richard@jrsretailservices.com"},
    {"username": "ralph",    "first_name": "Ralph",    "last_name": "Kirk",      "email": "ralph@jrsretailservices.com"},
    {"username": "macayla",  "first_name": "Macayla",  "last_name": "",          "email": "macayla@jrsretailservices.com"},
    {"username": "emmanuel", "first_name": "Emmanuel", "last_name": "Mendoza",   "email": "emmanuel@jrsretailservices.com"},
]

COOKIE_NAME = "jrs_dashboard_auth"
COOKIE_EXPIRY_DAYS = 7   # dias que dura la sesion sin re-login (dato sensible: no lo pongas muy alto)
OUTPUT = "config.yaml"


def hashear(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def main():
    if os.path.exists(OUTPUT):
        resp = input(f"{OUTPUT} ya existe. ¿Sobrescribir? (si/no): ").strip().lower()
        if resp != "si":
            print("Cancelado.")
            sys.exit(0)

    usernames = {}
    print("\nDefine una contrasena FUERTE para cada usuario (no se mostrara al escribir):\n")
    for u in USUARIOS:
        while True:
            pw1 = getpass.getpass(f"  Contrasena para '{u['username']}': ")
            if len(pw1) < 8:
                print("  -> Muy corta (minimo 8). Intenta de nuevo.")
                continue
            pw2 = getpass.getpass(f"  Repite la contrasena de '{u['username']}': ")
            if pw1 != pw2:
                print("  -> No coinciden. Intenta de nuevo.")
                continue
            break
        usernames[u["username"]] = {
            "email": u["email"],
            "first_name": u["first_name"],
            "last_name": u["last_name"],
            "password": hashear(pw1),
            "failed_login_attempts": 0,
            "logged_in": False,
        }
        print(f"  -> '{u['username']}' listo.\n")

    config = {
        "cookie": {
            "name": COOKIE_NAME,
            "key": secrets.token_hex(16),   # clave aleatoria para firmar la cookie
            "expiry_days": COOKIE_EXPIRY_DAYS,
        },
        "credentials": {"usernames": usernames},
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)

    print(f"Listo. Se creo {OUTPUT} con {len(usernames)} usuarios.")
    print("RECORDATORIO: config.yaml NO debe subir a git. Confirma que este en .gitignore.")


if __name__ == "__main__":
    main()
