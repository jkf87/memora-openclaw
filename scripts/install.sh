#!/usr/bin/env bash
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PLUGIN_DIR}/.venv"
MEMORA_DIR="${PLUGIN_DIR}/vendor/Memora"
MEMORA_COMMIT="dec3f8f2444eace7004fc084abe1be9f3d88270e"

select_python() {
  local candidate
  local resolved
  for candidate in \
    "${MEMORA_PYTHON_BIN:-}" \
    "${VENV_DIR}/bin/python" \
    python3.12 \
    python3.11 \
    python3.10 \
    python3; do
    [[ -n "$candidate" ]] || continue
    if [[ "$candidate" == */* ]]; then
      [[ -x "$candidate" ]] || continue
      resolved="$candidate"
    else
      resolved="$(command -v "$candidate" 2>/dev/null || true)"
      [[ -n "$resolved" ]] || continue
    fi
    if "$resolved" -c \
      'import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 13) else 1)'; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done
  return 1
}

PYTHON_BOOTSTRAP="$(select_python)" || {
  echo "Python 3.10, 3.11, or 3.12 is required" >&2
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

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  "$PYTHON_BOOTSTRAP" -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/python" -m pip install --upgrade pip

if [[ ! -d "${MEMORA_DIR}/.git" ]]; then
  mkdir -p "$(dirname "${MEMORA_DIR}")"
  git clone https://github.com/microsoft/Memora.git "${MEMORA_DIR}"
fi

git -C "${MEMORA_DIR}" fetch origin "${MEMORA_COMMIT}"
git -C "${MEMORA_DIR}" checkout --detach "${MEMORA_COMMIT}"

"${VENV_DIR}/bin/pip" install \
  -r "${PLUGIN_DIR}/requirements-plugin.txt"

if openclaw plugins inspect memora-openclaw >/dev/null 2>&1; then
  echo "memora-openclaw is already registered; keeping the existing plugin link."
  openclaw plugins enable memora-openclaw >/dev/null
else
  openclaw plugins install -l "${PLUGIN_DIR}"
fi

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
