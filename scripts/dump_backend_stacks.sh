#!/usr/bin/env bash
set -euo pipefail

port="${1:-8000}"

if ! command -v lsof >/dev/null 2>&1; then
  echo "ERROR: lsof is required" >&2
  exit 2
fi

pids="$(lsof -t -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null | sort -u || true)"
if [[ -z "${pids}" ]]; then
  echo "No listener found on port ${port}" >&2
  exit 1
fi

echo "Sending SIGUSR1 to PID(s): ${pids}"
for pid in ${pids}; do
  kill -USR1 "${pid}" 2>/dev/null || true
done

echo "If TRADE_CANVAS_FAULTHANDLER_PATH is set, check the log file for stack traces."

