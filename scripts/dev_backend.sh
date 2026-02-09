#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/dev_backend.sh [--host <host>] [--port <port>] [--no-reload] [--restart] [--no-access-log] [--fresh-db]

Environment (optional):
  TRADE_CANVAS_ENABLE_WHITELIST_INGEST=1
  TRADE_CANVAS_ENABLE_ONDEMAND_INGEST=1
  TRADE_CANVAS_ONDEMAND_IDLE_TTL_S=60
  TRADE_CANVAS_ONDEMAND_MAX_JOBS=8
  TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL=0
  TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL=1
  TRADE_CANVAS_MARKET_AUTO_TAIL_BACKFILL_MAX_CANDLES=2000
  TRADE_CANVAS_MARKET_HISTORY_SOURCE=freqtrade
  TRADE_CANVAS_ENABLE_CCXT_BACKFILL=1
  TRADE_CANVAS_UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN_S=3
  TRADE_CANVAS_SQLITE_TIMEOUT_S=5
  TRADE_CANVAS_ENABLE_FAULTHANDLER=1
  TRADE_CANVAS_FAULTHANDLER_PATH=backend/output/faulthandler.log
  TRADE_CANVAS_ENABLE_DEBUG_API=1
  TRADE_CANVAS_DB_PATH=backend/data/market.db
  TRADE_CANVAS_WHITELIST_PATH=backend/config/market_whitelist.json
  TRADE_CANVAS_FREQTRADE_ROOT=.
  TRADE_CANVAS_FREQTRADE_CONFIG=freqtrade_user_data/config.json
  TRADE_CANVAS_FREQTRADE_USERDIR=freqtrade_user_data
  TRADE_CANVAS_FREQTRADE_STRATEGY_PATH=Strategy
  TRADE_CANVAS_FREQTRADE_OFFLINE_MARKETS=1
  TRADE_CANVAS_BACKTEST_REQUIRE_TRADES=1
EOF
}

host="127.0.0.1"
port="8000"
reload="1"
restart="0"
access_log="1"
fresh_db="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) host="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    --no-reload) reload="0"; shift ;;
    --restart) restart="1"; shift ;;
    --no-access-log) access_log="0"; shift ;;
    --fresh-db) fresh_db="1"; shift ;;
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
: "${TRADE_CANVAS_ENABLE_WHITELIST_INGEST:=1}"
: "${TRADE_CANVAS_ENABLE_ONDEMAND_INGEST:=1}"
: "${TRADE_CANVAS_ONDEMAND_IDLE_TTL_S:=60}"
: "${TRADE_CANVAS_ONDEMAND_MAX_JOBS:=8}"
: "${TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL:=0}"
: "${TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL:=1}"
: "${TRADE_CANVAS_MARKET_AUTO_TAIL_BACKFILL_MAX_CANDLES:=2000}"
: "${TRADE_CANVAS_MARKET_HISTORY_SOURCE:=freqtrade}"
: "${TRADE_CANVAS_ENABLE_CCXT_BACKFILL:=1}"
: "${TRADE_CANVAS_UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN_S:=3}"
: "${TRADE_CANVAS_SQLITE_TIMEOUT_S:=5}"
: "${TRADE_CANVAS_ENABLE_FAULTHANDLER:=1}"
: "${TRADE_CANVAS_FAULTHANDLER_PATH:=backend/output/faulthandler.log}"
: "${TRADE_CANVAS_ENABLE_DEBUG_API:=1}"
: "${TRADE_CANVAS_FREQTRADE_ROOT:=$repo_root}"
: "${TRADE_CANVAS_FREQTRADE_CONFIG:=freqtrade_user_data/config.json}"
: "${TRADE_CANVAS_FREQTRADE_USERDIR:=freqtrade_user_data}"
: "${TRADE_CANVAS_FREQTRADE_STRATEGY_PATH:=Strategy}"
: "${TRADE_CANVAS_FREQTRADE_OFFLINE_MARKETS:=1}"
: "${TRADE_CANVAS_BACKTEST_REQUIRE_TRADES:=1}"

export TRADE_CANVAS_DB_PATH
export TRADE_CANVAS_WHITELIST_PATH
export TRADE_CANVAS_ENABLE_WHITELIST_INGEST
export TRADE_CANVAS_ENABLE_ONDEMAND_INGEST
export TRADE_CANVAS_ONDEMAND_IDLE_TTL_S
export TRADE_CANVAS_ONDEMAND_MAX_JOBS
export TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL
export TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL
export TRADE_CANVAS_MARKET_AUTO_TAIL_BACKFILL_MAX_CANDLES
export TRADE_CANVAS_MARKET_HISTORY_SOURCE
export TRADE_CANVAS_ENABLE_CCXT_BACKFILL
export TRADE_CANVAS_UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN_S
export TRADE_CANVAS_SQLITE_TIMEOUT_S
export TRADE_CANVAS_ENABLE_FAULTHANDLER
export TRADE_CANVAS_FAULTHANDLER_PATH
export TRADE_CANVAS_ENABLE_DEBUG_API
export TRADE_CANVAS_FREQTRADE_ROOT
export TRADE_CANVAS_FREQTRADE_CONFIG
export TRADE_CANVAS_FREQTRADE_USERDIR
export TRADE_CANVAS_FREQTRADE_STRATEGY_PATH
export TRADE_CANVAS_FREQTRADE_OFFLINE_MARKETS
export TRADE_CANVAS_BACKTEST_REQUIRE_TRADES

# Optionally reset sqlite db to avoid confusing "1970 candles" due to stale/mocked data.
if [[ "${fresh_db}" == "1" ]]; then
  rm -f "${TRADE_CANVAS_DB_PATH}" "${TRADE_CANVAS_DB_PATH}-wal" "${TRADE_CANVAS_DB_PATH}-shm" 2>/dev/null || true
fi

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
  # Limit reload scanning to backend code to avoid high CPU/IO when the repo has many files (frontend/node_modules, fixtures, sqlite WAL, etc).
  args+=(--reload --reload-dir backend)
fi
args+=(--timeout-graceful-shutdown "${TRADE_CANVAS_UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN_S}")
if [[ "$access_log" == "0" ]]; then
  args+=(--no-access-log)
fi

exec uvicorn "${args[@]}"
