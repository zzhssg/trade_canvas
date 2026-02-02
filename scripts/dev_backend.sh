#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/dev_backend.sh [--host <host>] [--port <port>] [--no-reload] [--restart]

Environment (optional):
  TRADE_CANVAS_ENABLE_WHITELIST_INGEST=1
  TRADE_CANVAS_ENABLE_ONDEMAND_INGEST=1
  TRADE_CANVAS_ONDEMAND_IDLE_TTL_S=60
  TRADE_CANVAS_DB_PATH=backend/data/market.db
  TRADE_CANVAS_WHITELIST_PATH=backend/config/market_whitelist.json
EOF
}

host="127.0.0.1"
port="8000"
reload="1"
restart="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) host="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    --no-reload) reload="0"; shift ;;
    --restart) restart="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if [[ ! -f ".env/bin/activate" ]]; then
  echo "ERROR: missing venv at ./.env (expected ./.env/bin/activate)" >&2
  echo "Hint: create it first, then re-run." >&2
  exit 2
fi

# Defaults (allow user overrides).
: "${TRADE_CANVAS_DB_PATH:=backend/data/market.db}"
: "${TRADE_CANVAS_WHITELIST_PATH:=backend/config/market_whitelist.json}"
: "${TRADE_CANVAS_ENABLE_WHITELIST_INGEST:=0}"
: "${TRADE_CANVAS_ENABLE_ONDEMAND_INGEST:=1}"
: "${TRADE_CANVAS_ONDEMAND_IDLE_TTL_S:=60}"

export TRADE_CANVAS_DB_PATH
export TRADE_CANVAS_WHITELIST_PATH
export TRADE_CANVAS_ENABLE_WHITELIST_INGEST
export TRADE_CANVAS_ENABLE_ONDEMAND_INGEST
export TRADE_CANVAS_ONDEMAND_IDLE_TTL_S

# shellcheck disable=SC1091
source ".env/bin/activate"

if command -v lsof >/dev/null 2>&1; then
  existing_pids="$(lsof -t -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
else
  existing_pids=""
fi

if [[ -n "${existing_pids}" ]]; then
  if [[ "${restart}" == "1" ]]; then
    bash scripts/free_port.sh "${port}"
  else
    echo "ERROR: port already in use: ${host}:${port}" >&2
    echo "PID(s): ${existing_pids}" >&2
    echo "Hint: run \`bash scripts/free_port.sh ${port}\` or re-run with \`--restart\`, or pick a different \`--port\`." >&2
    exit 2
  fi
fi

args=(backend.app.main:app --host "$host" --port "$port")
if [[ "$reload" == "1" ]]; then
  args+=(--reload)
fi

exec uvicorn "${args[@]}"
