#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/home/acer/Downloads/AuraCore"
RUN_DIR="${ROOT_DIR}/.local-run"
LOCK_FILE="${RUN_DIR}/auto-update.lock"
BRANCH="${AURACORE_UPDATE_BRANCH:-main}"

mkdir -p "${RUN_DIR}"

log() {
  printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$*"
}

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  log "auto-update ja esta em execucao; ignorando ciclo."
  exit 0
fi

cd "${ROOT_DIR}"

current_branch="$(git branch --show-current)"
if [[ "${current_branch}" != "${BRANCH}" ]]; then
  log "branch atual '${current_branch}' nao e '${BRANCH}'; auto-update ignorado."
  exit 0
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  log "repositorio com alteracoes rastreadas locais; auto-update ignorado para nao sobrescrever trabalho."
  exit 0
fi

old_rev="$(git rev-parse HEAD)"

if ! git fetch --quiet origin "${BRANCH}"; then
  log "falha ao buscar atualizacoes de origin/${BRANCH}."
  exit 1
fi

remote_rev="$(git rev-parse FETCH_HEAD)"
if [[ "${old_rev}" == "${remote_rev}" ]]; then
  log "nenhuma atualizacao disponivel."
  exit 0
fi

changed_files="$(git diff --name-only "${old_rev}" "${remote_rev}")"
log "nova revisao encontrada: ${old_rev} -> ${remote_rev}"

git pull --ff-only origin "${BRANCH}"

should_reload_units=false
should_restart_backend=false
should_restart_gateway=false
should_restart_cloudflared=false
should_install_gateway_deps=false

while IFS= read -r path; do
  [[ -z "${path}" ]] && continue

  case "${path}" in
    deploy/systemd-user/*|deploy/cloudflared/*|scripts/install-user-services.sh)
      should_reload_units=true
      should_restart_cloudflared=true
      ;;
  esac

  case "${path}" in
    backend/*|scripts/run-backend-prod.sh)
      should_restart_backend=true
      ;;
  esac

  case "${path}" in
    whatsapp-gateway/*|scripts/run-gateway-prod.sh)
      should_restart_gateway=true
      ;;
  esac

  case "${path}" in
    scripts/*)
      should_restart_backend=true
      should_restart_gateway=true
      ;;
  esac

  case "${path}" in
    whatsapp-gateway/package.json|whatsapp-gateway/package-lock.json)
      should_install_gateway_deps=true
      should_restart_gateway=true
      ;;
  esac
done <<<"${changed_files}"

if [[ ! -d "${ROOT_DIR}/whatsapp-gateway/node_modules" ]]; then
  should_install_gateway_deps=true
  should_restart_gateway=true
fi

if [[ "${should_install_gateway_deps}" == "true" ]]; then
  log "instalando dependencias do gateway."
  (
    cd "${ROOT_DIR}/whatsapp-gateway"
    npm install
  )
fi

if [[ "${should_reload_units}" == "true" ]]; then
  log "reinstalando units do systemd do AuraCore."
  /bin/bash "${ROOT_DIR}/scripts/install-user-services.sh"
fi

restart_targets=()
if [[ "${should_restart_backend}" == "true" ]]; then
  restart_targets+=("auracore-backend.service")
fi
if [[ "${should_restart_gateway}" == "true" ]]; then
  restart_targets+=("auracore-whatsapp-gateway.service")
fi
if [[ "${should_restart_cloudflared}" == "true" ]]; then
  restart_targets+=("auracore-cloudflared.service")
fi

if (( ${#restart_targets[@]} > 0 )); then
  log "reiniciando servicos: ${restart_targets[*]}"
  systemctl --user restart "${restart_targets[@]}"
else
  log "atualizacao concluida sem necessidade de reinicio de servicos."
fi
