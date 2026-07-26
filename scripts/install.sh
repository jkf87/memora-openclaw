#!/usr/bin/env bash
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PLUGIN_DIR}/.venv"
MEMORA_DIR="${PLUGIN_DIR}/vendor/Memora"
MEMORA_COMMIT="dec3f8f2444eace7004fc084abe1be9f3d88270e"

command -v python3 >/dev/null || {
  echo "python3 is required" >&2
  exit 1
}
command -v git >/dev/null || {
  echo "git is required" >&2
  exit 1
}
command -v openclaw >/dev/null || {
  echo "openclaw is required" >&2
  exit 1
}

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip

if [[ ! -d "${MEMORA_DIR}/.git" ]]; then
  mkdir -p "$(dirname "${MEMORA_DIR}")"
  git clone https://github.com/microsoft/Memora.git "${MEMORA_DIR}"
fi

git -C "${MEMORA_DIR}" fetch origin "${MEMORA_COMMIT}"
git -C "${MEMORA_DIR}" checkout --detach "${MEMORA_COMMIT}"

"${VENV_DIR}/bin/pip" install \
  -r "${MEMORA_DIR}/requirements.txt" \
  -r "${PLUGIN_DIR}/requirements-plugin.txt"

openclaw plugins install -l "${PLUGIN_DIR}"

echo
echo "Installed memora-openclaw."
echo "Ensure Ollama is running with the embedding model:"
echo "  ollama pull bge-m3"
echo "  ollama serve"
echo "Next:"
echo "  ${VENV_DIR}/bin/python ${PLUGIN_DIR}/adapter.py doctor"
echo "  ${VENV_DIR}/bin/python ${PLUGIN_DIR}/adapter.py sync"
echo "  openclaw config patch --file ${PLUGIN_DIR}/config/openclaw.patch.json5 --dry-run"
echo "  openclaw config patch --file ${PLUGIN_DIR}/config/openclaw.patch.json5"
