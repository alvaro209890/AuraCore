#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/home/acer/Downloads/AuraCore"
GATEWAY_DIR="${ROOT_DIR}/whatsapp-gateway"

cd "${GATEWAY_DIR}"
npm run build
exec npm run start
