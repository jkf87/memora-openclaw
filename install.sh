#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_URL="${MEMORA_OPENCLAW_REPOSITORY_URL:-https://github.com/jkf87/memora-openclaw.git}"
SKILL_NAME="memora-openclaw"
AGENT_ID=""
FULL_SETUP=0
ASSUME_YES=0
FORCE_INSTALL=0
DRY_RUN=0

usage() {
  printf '%s\n' \
    "Memora for OpenClaw easy installer" \
    "" \
    "Usage: install.sh [options]" \
    "  --full          Install, configure, and build the initial index" \
    "  --yes           Acknowledge config changes, downloads, and GLM usage" \
    "  --agent <id>    Install into one OpenClaw agent instead of globally" \
    "  --force         Replace an existing managed skill installation" \
    "  --dry-run       Print the planned commands without changing anything" \
    "  -h, --help      Show this help"
}

while (($#)); do
  case "$1" in
    --full) FULL_SETUP=1 ;;
    --yes) ASSUME_YES=1 ;;
    --force) FORCE_INSTALL=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --agent)
      shift
      [[ $# -gt 0 ]] || {
        printf '%s\n' "--agent requires an id" >&2
        exit 2
      }
      AGENT_ID="$1"
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

if ((FULL_SETUP == 1 && ASSUME_YES == 0)); then
  printf '%s\n' \
    "Full setup changes OpenClaw configuration, may download BGE-M3, and" \
    "invokes the configured GLM route while building the initial index." \
    "Re-run with --full --yes after reviewing README.md." >&2
  exit 2
fi

install_args=(skills install "git:${REPOSITORY_URL}" --as "$SKILL_NAME")
if [[ -n "$AGENT_ID" ]]; then
  install_args+=(--agent "$AGENT_ID")
else
  install_args+=(--global)
fi
if ((FORCE_INSTALL == 1)); then
  install_args+=(--force)
fi

if ((DRY_RUN == 1)); then
  printf 'openclaw'
  printf ' %q' "${install_args[@]}"
  printf '\n'
  if ((FULL_SETUP == 1)); then
    printf '%s\n' \
      '<installed-skill>/scripts/setup.sh --start-ollama --pull-model --apply-config --sync'
  fi
  exit 0
fi

command -v openclaw >/dev/null 2>&1 || {
  printf '%s\n' \
    "OpenClaw is required. Install it first, then rerun this command." >&2
  exit 1
}

info_args=(skills info "$SKILL_NAME" --json)
if [[ -n "$AGENT_ID" ]]; then
  info_args+=(--agent "$AGENT_ID")
fi

if openclaw "${info_args[@]}" >/dev/null 2>&1; then
  if ((FORCE_INSTALL == 0)); then
    printf '%s\n' \
      "The $SKILL_NAME skill is already installed." \
      "Use --force to replace it, or invoke it directly in OpenClaw."
  else
    openclaw "${install_args[@]}"
  fi
else
  openclaw "${install_args[@]}"
fi

skill_info="$(openclaw "${info_args[@]}")"
skill_dir="$(
  printf '%s' "$skill_info" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["baseDir"])'
)"

if ((FULL_SETUP == 1)); then
  bash "${skill_dir}/scripts/setup.sh" \
    --start-ollama \
    --pull-model \
    --apply-config \
    --sync
else
  printf '\n%s\n' \
    "Installed $SKILL_NAME." \
    "Next, invoke this in OpenClaw:" \
    '$memora-openclaw Install Memora, enable it, and build my initial index.'
fi
