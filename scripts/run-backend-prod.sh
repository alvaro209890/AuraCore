#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/home/acer/Downloads/AuraCore"
BACKEND_DIR="${ROOT_DIR}/backend"

export PYTHONPATH="${BACKEND_DIR}/.vendor${PYTHONPATH:+:${PYTHONPATH}}"

cd "${BACKEND_DIR}"
exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
