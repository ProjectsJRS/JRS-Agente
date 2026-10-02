#!/usr/bin/env bash
# start.sh — Arranque para Railway.
#
# CAMBIO (2026-10-01, Etapa 4): Streamlit retirado. La interfaz ahora es
# JRS Operations System (Netlify), que habla con Joe por la API (api.py).
# La API corre DENTRO del proceso del agente, en un hilo, y escucha en $PORT:
# un solo proceso = un solo cliente de ChromaDB (sin riesgo de dañar el indice).
#
# Si la API falla, el agente de correo sigue corriendo intacto.

set -u

echo "start.sh -> lanzando agente (incluye la API en \$PORT=${PORT:-8000})..."
exec python agent.py
