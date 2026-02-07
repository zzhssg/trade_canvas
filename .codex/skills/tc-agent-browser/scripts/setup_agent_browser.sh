#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash .codex/skills/tc-agent-browser/scripts/setup_agent_browser.sh [--with-deps]

Installs `agent-browser` globally and downloads Chromium via `agent-browser install`.

Notes:
- If `npm install -g` fails due to permissions, prefer using:
  bash .codex/skills/tc-agent-browser/scripts/ab.sh <command...>
  which falls back to `npx -y agent-browser`.
EOF
}

with_deps=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-deps) with_deps=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: missing Node.js/npm. Install Node.js first." >&2
  exit 2
fi

if ! command -v agent-browser >/dev/null 2>&1; then
  npm install -g agent-browser
fi

if [[ "$with_deps" -eq 1 ]]; then
  agent-browser install --with-deps
else
  agent-browser install
fi

