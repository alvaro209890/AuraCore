#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_DIR="${ROOT_DIR}/whatsapp-gateway"
NPM_BIN="${NPM_BIN:-}"

if [[ -z "${NPM_BIN}" ]]; then
  if NPM_PATH="$(command -v npm 2>/dev/null)"; then
    NPM_BIN="${NPM_PATH}"
  else
    NVM_NODE_GLOB="${HOME}/.nvm/versions/node"/*/bin/npm
    for candidate in ${NVM_NODE_GLOB}; do
      if [[ -x "${candidate}" ]]; then
        NPM_BIN="${candidate}"
      fi
    done
  fi
fi

if [[ -z "${NPM_BIN}" || ! -x "${NPM_BIN}" ]]; then
  echo "npm nao encontrado para subir o whatsapp-gateway" >&2
  exit 127
fi

export PATH="$(dirname "${NPM_BIN}")${PATH:+:${PATH}}"

cd "${GATEWAY_DIR}"
"${NPM_BIN}" run build
exec "${NPM_BIN}" run start
