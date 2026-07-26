#!/usr/bin/env bash
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_HOME="${HOME:?HOME is required}"
OPENCLAW_DIR="${USER_HOME}/.openclaw"
OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
EMBEDDING_MODEL="${MEMORA_EMBEDDING_MODEL:-bge-m3}"

CHECK_ONLY=0
START_OLLAMA=0
PULL_MODEL=0
APPLY_CONFIG=0
SYNC_INDEX=0
FORCE_SYNC=0

usage() {
  printf '%s\n' \
    "Usage: scripts/setup.sh [options]" \
    "  --check-only     Check prerequisites without changing state" \
    "  --start-ollama   Start a local Ollama server when unavailable" \
    "  --pull-model     Pull the embedding model when missing" \
    "  --apply-config   Back up and patch OpenClaw configuration" \
    "  --sync           Build or update the Memora index" \
    "  --force-sync     Force a complete Memora index rebuild" \
    "  -h, --help       Show this help"
}

while (($#)); do
  case "$1" in
    --check-only) CHECK_ONLY=1 ;;
    --start-ollama) START_OLLAMA=1 ;;
    --pull-model) PULL_MODEL=1 ;;
    --apply-config) APPLY_CONFIG=1 ;;
    --sync) SYNC_INDEX=1 ;;
    --force-sync)
      SYNC_INDEX=1
      FORCE_SYNC=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

require_bin() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '%s is required\n' "$1" >&2
    exit 1
  }
}

select_python() {
  local candidate
  local resolved
  for candidate in \
    "${MEMORA_PYTHON_BIN:-}" \
    "${PLUGIN_DIR}/.venv/bin/python" \
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

ollama_ready() {
  curl -fsS --max-time 5 "${OLLAMA_BASE_URL%/}/api/tags" >/dev/null
}

model_ready() {
  curl -fsS --max-time 10 "${OLLAMA_BASE_URL%/}/api/tags" |
    "$PYTHON_BOOTSTRAP" -c '
import json
import sys

target = sys.argv[1]
payload = json.load(sys.stdin)
names = [item.get("name", "") for item in payload.get("models", [])]
raise SystemExit(0 if any(name == target or name.startswith(target + ":") for name in names) else 1)
' "$EMBEDDING_MODEL"
}

require_bin git
require_bin openclaw
require_bin curl

PYTHON_BOOTSTRAP="$(select_python)" || {
  printf 'Python 3.10, 3.11, or 3.12 is required\n' >&2
  exit 1
}

if ! ollama_ready; then
  if ((START_OLLAMA == 0)); then
    printf 'Ollama is unavailable at %s\n' "$OLLAMA_BASE_URL" >&2
    exit 1
  fi
  require_bin ollama
  mkdir -p "${OPENCLAW_DIR}/logs"
  nohup ollama serve >"${OPENCLAW_DIR}/logs/memora-ollama.log" 2>&1 &
  for _ in {1..30}; do
    ollama_ready && break
    sleep 1
  done
  ollama_ready || {
    printf 'Ollama did not become ready; see %s\n' \
      "${OPENCLAW_DIR}/logs/memora-ollama.log" >&2
    exit 1
  }
fi

if ! model_ready; then
  if ((PULL_MODEL == 0)); then
    printf 'Ollama model %s is missing\n' "$EMBEDDING_MODEL" >&2
    exit 1
  fi
  require_bin ollama
  ollama pull "$EMBEDDING_MODEL"
  model_ready || {
    printf 'Ollama model %s is still unavailable after pull\n' \
      "$EMBEDDING_MODEL" >&2
    exit 1
  }
fi

printf 'Prerequisites ready: OpenClaw, Python, Git, Ollama %s\n' \
  "$EMBEDDING_MODEL"

if ((CHECK_ONLY == 1)); then
  exit 0
fi

MEMORA_PYTHON_BIN="$PYTHON_BOOTSTRAP" bash "${PLUGIN_DIR}/scripts/install.sh"

if ((APPLY_CONFIG == 1)); then
  mkdir -p "${OPENCLAW_DIR}/backups/memora-openclaw"
  timestamp="$(date +%Y%m%d-%H%M%S)"
  config_path="${OPENCLAW_DIR}/openclaw.json"
  backup_path="${OPENCLAW_DIR}/backups/memora-openclaw/openclaw-${timestamp}.json"
  if [[ -f "$config_path" ]]; then
    cp -p "$config_path" "$backup_path"
    printf 'Configuration backup: %s\n' "$backup_path"
  fi

  patch_file="${PLUGIN_DIR}/config/openclaw.minimal.patch.json5"
  if openclaw plugins inspect active-memory >/dev/null 2>&1; then
    patch_file="${PLUGIN_DIR}/config/openclaw.patch.json5"
  fi

  if ! openclaw config patch --file "$patch_file"; then
    if [[ -f "$backup_path" ]]; then
      cp -p "$backup_path" "$config_path"
    fi
    printf 'Configuration patch failed; previous configuration restored\n' >&2
    exit 1
  fi
  if ! openclaw config validate; then
    if [[ -f "$backup_path" ]]; then
      cp -p "$backup_path" "$config_path"
    fi
    printf 'Configuration validation failed; previous configuration restored\n' >&2
    exit 1
  fi
  openclaw gateway restart
fi

python_bin="${PLUGIN_DIR}/.venv/bin/python"
"$python_bin" "${PLUGIN_DIR}/adapter.py" doctor

if ((SYNC_INDEX == 1)); then
  sync_args=(sync)
  if ((FORCE_SYNC == 1)); then
    sync_args+=(--force)
  fi
  "$python_bin" "${PLUGIN_DIR}/adapter.py" "${sync_args[@]}"
fi

bash "${PLUGIN_DIR}/scripts/verify.sh"
