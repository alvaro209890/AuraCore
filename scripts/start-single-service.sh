#!/usr/bin/env bash

set -euo pipefail

PORT="${PORT:-10000}"
WHATSAPP_GATEWAY_PORT="${WHATSAPP_GATEWAY_PORT:-10001}"

export WHATSAPP_GATEWAY_URL="${WHATSAPP_GATEWAY_URL:-http://127.0.0.1:${WHATSAPP_GATEWAY_PORT}}"
export AURACORE_API_BASE_URL="${AURACORE_API_BASE_URL:-http://127.0.0.1:${PORT}}"

gateway_pid=""
backend_pid=""

cleanup() {
  trap - EXIT SIGINT SIGTERM
  if [[ -n "${backend_pid}" ]] && kill -0 "${backend_pid}" 2>/dev/null; then
    kill "${backend_pid}" 2>/dev/null || true
  fi
  if [[ -n "${gateway_pid}" ]] && kill -0 "${gateway_pid}" 2>/dev/null; then
    kill "${gateway_pid}" 2>/dev/null || true
  fi
  wait || true
}

trap cleanup EXIT SIGINT SIGTERM

cd /app/whatsapp-gateway
PORT="${WHATSAPP_GATEWAY_PORT}" node dist/server.js &
gateway_pid="$!"

cd /app/backend
uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" &
backend_pid="$!"

wait -n "${gateway_pid}" "${backend_pid}"
