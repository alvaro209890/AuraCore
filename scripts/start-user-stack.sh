#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${ROOT_DIR}/.local-run"
CLOUDFLARED_TOKEN_FILE="${HOME}/.cloudflared/auracore-local-api.token"

mkdir -p "${RUN_DIR}"

start_process() {
  local name="$1"
  local command="$2"
  local log_file="${RUN_DIR}/${name}.log"
  local pid_file="${RUN_DIR}/${name}.pid"

  if [[ -f "${pid_file}" ]]; then
    local existing_pid
    existing_pid="$(cat "${pid_file}")"
    if [[ -n "${existing_pid}" ]] && kill -0 "${existing_pid}" 2>/dev/null; then
      return 0
    fi
  fi

  nohup /bin/bash -lc "${command}" >>"${log_file}" 2>&1 &
  local pid="$!"
  echo "${pid}" >"${pid_file}"
  sleep 2

  if ! kill -0 "${pid}" 2>/dev/null; then
    rm -f "${pid_file}"
    echo "${name} encerrou logo apos iniciar. Verifique ${log_file}" >&2
    return 1
  fi
}

wait_for_health() {
  local url="$1"
  local label="$2"
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "${label} nao respondeu em ${url}" >&2
  return 1
}

start_process "backend" "cd '${ROOT_DIR}' && exec /bin/bash '${ROOT_DIR}/scripts/run-backend-prod.sh'"
wait_for_health "http://127.0.0.1:8000/health" "backend"

start_process "gateway" "cd '${ROOT_DIR}' && exec /bin/bash '${ROOT_DIR}/scripts/run-gateway-prod.sh'"
wait_for_health "http://127.0.0.1:10001/health" "gateway"

if [[ ! -f "${CLOUDFLARED_TOKEN_FILE}" ]]; then
  echo "arquivo de token do cloudflared ausente: ${CLOUDFLARED_TOKEN_FILE}" >&2
  exit 1
fi

start_process "cloudflared" "exec /usr/bin/cloudflared --config '${HOME}/.cloudflared/auracore-config.yml' tunnel run --token-file '${CLOUDFLARED_TOKEN_FILE}'"
