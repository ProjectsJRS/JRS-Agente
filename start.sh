#!/usr/bin/env bash
# start.sh — Arranque combinado para Railway (Opcion 1).
# Un solo servicio corre DOS procesos, porque Railway no comparte volumen
# entre servicios: el dashboard necesita leer /data (heartbeat, alerts.jsonl,
# ChromaDB), que solo esta montado en este servicio.
#
# Diseno:
#   - Streamlit (dashboard) en SEGUNDO plano: expone el puerto de Railway.
#   - Agente en PRIMER plano: es el proceso critico y mantiene vivo el
#     contenedor. Si Streamlit falla, el agente sigue corriendo intacto.
#
# En local (sin $PORT) Streamlit usa 8501 por defecto.

set -u

echo "start.sh -> lanzando dashboard (Streamlit) en segundo plano..."
streamlit run dashboard.py \
  --server.port="${PORT:-8501}" \
  --server.address=0.0.0.0 \
  --server.headless=true &

echo "start.sh -> lanzando agente en primer plano..."
python agent.py
