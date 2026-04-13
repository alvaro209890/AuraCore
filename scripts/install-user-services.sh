#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SOURCE_DIR="${ROOT_DIR}/deploy/systemd-user"
UNIT_TARGET_DIR="${HOME}/.config/systemd/user"
CLOUDFLARED_SOURCE_CONFIG="${ROOT_DIR}/deploy/cloudflared/auracore-config.yml"
CLOUDFLARED_TARGET_DIR="${HOME}/.cloudflared"
CLOUDFLARED_TARGET_CONFIG="${CLOUDFLARED_TARGET_DIR}/auracore-config.yml"
DB_ROOT_DIR="$(grep -E '^AURACORE_DB_ROOT=' "${ROOT_DIR}/backend/.env" | head -n1 | cut -d= -f2-)"

mkdir -p "${UNIT_TARGET_DIR}"
mkdir -p "${CLOUDFLARED_TARGET_DIR}"
mkdir -p "${DB_ROOT_DIR}/.system"
mkdir -p "${DB_ROOT_DIR}/agent-session"

sed "s#__AURACORE_ROOT__#${ROOT_DIR}#g" "${UNIT_SOURCE_DIR}/auracore-backend.service" > "${UNIT_TARGET_DIR}/auracore-backend.service"
sed "s#__AURACORE_ROOT__#${ROOT_DIR}#g" "${UNIT_SOURCE_DIR}/auracore-whatsapp-gateway.service" > "${UNIT_TARGET_DIR}/auracore-whatsapp-gateway.service"
sed "s#__AURACORE_ROOT__#${ROOT_DIR}#g" "${UNIT_SOURCE_DIR}/auracore-cloudflared.service" > "${UNIT_TARGET_DIR}/auracore-cloudflared.service"
sed "s#__AURACORE_ROOT__#${ROOT_DIR}#g" "${UNIT_SOURCE_DIR}/auracore-auto-update.service" > "${UNIT_TARGET_DIR}/auracore-auto-update.service"
install -m 644 "${UNIT_SOURCE_DIR}/auracore-auto-update.timer" "${UNIT_TARGET_DIR}/auracore-auto-update.timer"
chmod 644 "${UNIT_TARGET_DIR}/auracore-backend.service" "${UNIT_TARGET_DIR}/auracore-whatsapp-gateway.service" "${UNIT_TARGET_DIR}/auracore-cloudflared.service" "${UNIT_TARGET_DIR}/auracore-auto-update.service"
install -m 600 "${CLOUDFLARED_SOURCE_CONFIG}" "${CLOUDFLARED_TARGET_CONFIG}"

systemctl --user daemon-reload
systemctl --user enable --now auracore-backend.service
systemctl --user enable --now auracore-whatsapp-gateway.service
systemctl --user enable --now auracore-cloudflared.service
systemctl --user enable --now auracore-auto-update.timer
