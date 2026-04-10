#!/usr/bin/env bash

set -euo pipefail

PORT="${PORT:-10000}"
WHATSAPP_GATEWAY_PORT="${WHATSAPP_GATEWAY_PORT:-10001}"

export WHATSAPP_GATEWAY_URL="${WHATSAPP_GATEWAY_URL:-http://127.0.0.1:${WHATSAPP_GATEWAY_PORT}}"
export AURACORE_API_BASE_URL="${AURACORE_API_BASE_URL:-http://127.0.0.1:${PORT}}"

gateway_pid=""
backend_pid=""
keepalive_pid=""

is_truthy() {
  local value
  value="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ "${value}" == "1" || "${value}" == "true" || "${value}" == "yes" || "${value}" == "on" ]]
}

wait_for_backend_health() {
  local health_url="http://127.0.0.1:${PORT}/health"
  local max_attempts="${BACKEND_HEALTH_MAX_ATTEMPTS:-90}"
  local attempt=1

  while (( attempt <= max_attempts )); do
    if [[ -n "${backend_pid}" ]] && ! kill -0 "${backend_pid}" 2>/dev/null; then
      echo "Backend encerrou antes de responder em /health." >&2
      return 1
    fi

    if python3 -c "import sys, urllib.request; urllib.request.urlopen('${health_url}', timeout=2).read(1)" >/dev/null 2>&1; then
      echo "Backend respondeu em /health; iniciando gateway."
      return 0
    fi

    sleep 1
    ((attempt++))
  done

  echo "Backend nao respondeu em /health dentro do tempo esperado." >&2
  return 1
}

start_keepalive() {
  if ! is_truthy "${RENDER_KEEPALIVE_ENABLED:-false}"; then
    return
  fi

  local keepalive_url="${RENDER_KEEPALIVE_URL:-}"
  local interval_seconds="${RENDER_KEEPALIVE_INTERVAL_SECONDS:-600}"

  if [[ -z "${keepalive_url}" ]]; then
    echo "Render keepalive habilitado, mas RENDER_KEEPALIVE_URL nao foi definido."
    return
  fi

  (
    while true; do
      sleep "${interval_seconds}"
      if ! python3 -c "import os, urllib.request; urllib.request.urlopen(os.environ['RENDER_KEEPALIVE_URL'], timeout=15).read(1)" >/dev/null 2>&1; then
        echo "Render keepalive ping falhou para ${keepalive_url}" >&2
      fi
    done
  ) &
  keepalive_pid="$!"
}

cleanup() {
  trap - EXIT SIGINT SIGTERM
  if [[ -n "${backend_pid}" ]] && kill -0 "${backend_pid}" 2>/dev/null; then
    kill "${backend_pid}" 2>/dev/null || true
  fi
  if [[ -n "${gateway_pid}" ]] && kill -0 "${gateway_pid}" 2>/dev/null; then
    kill "${gateway_pid}" 2>/dev/null || true
  fi
  if [[ -n "${keepalive_pid}" ]] && kill -0 "${keepalive_pid}" 2>/dev/null; then
    kill "${keepalive_pid}" 2>/dev/null || true
  fi
  wait || true
}

trap cleanup EXIT SIGINT SIGTERM

# O backend responde ao health check da Render, entao ele precisa ser o
# processo principal do container. O gateway pode falhar sem derrubar o
# /health durante o bootstrap.
cd /app/backend
uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" &
backend_pid="$!"

wait_for_backend_health

cd /app/whatsapp-gateway
PORT="${WHATSAPP_GATEWAY_PORT}" node dist/server.js &
gateway_pid="$!"

start_keepalive

wait "${backend_pid}"
