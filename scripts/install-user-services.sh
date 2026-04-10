#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/home/acer/Downloads/AuraCore"
UNIT_SOURCE_DIR="${ROOT_DIR}/deploy/systemd-user"
UNIT_TARGET_DIR="${HOME}/.config/systemd/user"

mkdir -p "${UNIT_TARGET_DIR}"

install -m 644 "${UNIT_SOURCE_DIR}/auracore-backend.service" "${UNIT_TARGET_DIR}/auracore-backend.service"
install -m 644 "${UNIT_SOURCE_DIR}/auracore-whatsapp-gateway.service" "${UNIT_TARGET_DIR}/auracore-whatsapp-gateway.service"
install -m 644 "${UNIT_SOURCE_DIR}/auracore-cloudflared.service" "${UNIT_TARGET_DIR}/auracore-cloudflared.service"

systemctl --user daemon-reload
systemctl --user enable auracore-backend.service
systemctl --user enable auracore-whatsapp-gateway.service
systemctl --user enable auracore-cloudflared.service
