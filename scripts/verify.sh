#!/usr/bin/env bash
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PLUGIN_DIR}/.venv/bin/python"

[[ -x "$PYTHON_BIN" ]] || {
  printf 'Plugin virtual environment is missing: %s\n' "$PYTHON_BIN" >&2
  exit 1
}
[[ -d "${PLUGIN_DIR}/vendor/Memora/src" ]] || {
  printf 'Pinned Memora checkout is missing: %s\n' \
    "${PLUGIN_DIR}/vendor/Memora" >&2
  exit 1
}

openclaw config validate
openclaw plugins inspect memora-openclaw
openclaw plugins doctor
openclaw gateway health
"$PYTHON_BIN" "${PLUGIN_DIR}/adapter.py" doctor
"$PYTHON_BIN" "${PLUGIN_DIR}/adapter.py" status

