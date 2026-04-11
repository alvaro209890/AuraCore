#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/home/acer/Downloads/AuraCore"
UNIT_SOURCE_DIR="${ROOT_DIR}/deploy/systemd-user"
UNIT_TARGET_DIR="${HOME}/.config/systemd/user"
CLOUDFLARED_SOURCE_CONFIG="${ROOT_DIR}/deploy/cloudflared/config.yml"
CLOUDFLARED_TARGET_DIR="${HOME}/.cloudflared"
CLOUDFLARED_TARGET_CONFIG="${CLOUDFLARED_TARGET_DIR}/config.yml"
DB_ROOT_DIR="/home/acer/Documentos/Bando_de_dados/Aura_Core"

mkdir -p "${UNIT_TARGET_DIR}"
mkdir -p "${CLOUDFLARED_TARGET_DIR}"
mkdir -p "${DB_ROOT_DIR}/sqlite"
mkdir -p "${DB_ROOT_DIR}/backups"
mkdir -p "${DB_ROOT_DIR}/exports"

install -m 644 "${UNIT_SOURCE_DIR}/auracore-backend.service" "${UNIT_TARGET_DIR}/auracore-backend.service"
install -m 644 "${UNIT_SOURCE_DIR}/auracore-whatsapp-gateway.service" "${UNIT_TARGET_DIR}/auracore-whatsapp-gateway.service"
install -m 644 "${UNIT_SOURCE_DIR}/auracore-cloudflared.service" "${UNIT_TARGET_DIR}/auracore-cloudflared.service"
install -m 644 "${UNIT_SOURCE_DIR}/auracore-auto-update.service" "${UNIT_TARGET_DIR}/auracore-auto-update.service"
install -m 644 "${UNIT_SOURCE_DIR}/auracore-auto-update.timer" "${UNIT_TARGET_DIR}/auracore-auto-update.timer"
install -m 600 "${CLOUDFLARED_SOURCE_CONFIG}" "${CLOUDFLARED_TARGET_CONFIG}"

systemctl --user daemon-reload
systemctl --user enable --now auracore-backend.service
systemctl --user enable --now auracore-whatsapp-gateway.service
systemctl --user enable --now auracore-cloudflared.service
systemctl --user enable --now auracore-auto-update.timer
