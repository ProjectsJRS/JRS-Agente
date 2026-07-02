#!/usr/bin/env bash
# start.sh — Arranque combinado para Railway (Opcion 1).
# Un solo servicio corre DOS procesos, porque Railway no comparte volumen
# entre servicios: el dashboard necesita leer /data (heartbeat, alerts.jsonl,
# ChromaDB, config.yaml), que solo esta montado en este servicio.
#
# Diseno:
#   - Streamlit (dashboard) en SEGUNDO plano: expone el puerto de Railway.
#   - Agente en PRIMER plano: es el proceso critico y mantiene vivo el
#     contenedor. Si Streamlit falla, el agente sigue corriendo intacto.
#
# En local (sin $PORT) Streamlit usa 8501 por defecto.

set -u

# --- Preparar config.yaml de autenticacion en el volumen ---
# El repo es publico, asi que config.yaml no va por git. En Railway se
# inyecta como variable/secret DASHBOARD_CONFIG_YAML y aqui lo materializamos
# en /data/config.yaml (o donde apunte CHROMA_DB_PATH). En local no se activa
# porque ./config.yaml ya existe y la variable no esta definida.
VOLUME_DIR="$(dirname "${CHROMA_DB_PATH:-./chroma_data}")"
CONFIG_PATH="${VOLUME_DIR}/config.yaml"
if [ -n "${DASHBOARD_CONFIG_YAML:-}" ] && [ ! -f "${CONFIG_PATH}" ]; then
  echo "start.sh -> materializando ${CONFIG_PATH} desde DASHBOARD_CONFIG_YAML..."
  printf '%s' "${DASHBOARD_CONFIG_YAML}" > "${CONFIG_PATH}"
fi

echo "start.sh -> lanzando dashboard (Streamlit) en segundo plano..."
streamlit run dashboard.py \
  --server.port="${PORT:-8501}" \
  --server.address=0.0.0.0 \
  --server.headless=true &

echo "start.sh -> lanzando agente en primer plano..."
python agent.py
