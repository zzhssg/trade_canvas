#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/free_port.sh <port>

Finds processes listening on <port> and terminates them (SIGTERM, then SIGKILL).
Requires: lsof
EOF
}

port="${1:-}"
if [[ -z "${port}" ]] || [[ "${port}" == "-h" ]] || [[ "${port}" == "--help" ]]; then
  usage
  exit 2
fi

if ! [[ "${port}" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
  echo "ERROR: invalid port: ${port}" >&2
  usage
  exit 2
fi

if ! command -v lsof >/dev/null 2>&1; then
  echo "ERROR: lsof is required to free ports on this system." >&2
  exit 2
fi

pids="$(lsof -t -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
if [[ -z "${pids}" ]]; then
  echo "[free-port] Port ${port} is free."
  exit 0
fi

echo "[free-port] Port ${port} is in use by PID(s): ${pids}. Sending SIGTERM..."
kill -TERM ${pids} 2>/dev/null || true
sleep 0.4

still_alive=""
for pid in ${pids}; do
  if kill -0 "${pid}" >/dev/null 2>&1; then
    still_alive="${still_alive} ${pid}"
  fi
done
still_alive="${still_alive# }"

if [[ -z "${still_alive}" ]]; then
  echo "[free-port] Freed port ${port}."
  exit 0
fi

echo "[free-port] PID(s) still alive: ${still_alive}. Sending SIGKILL..."
kill -KILL ${still_alive} 2>/dev/null || true
sleep 0.2

final_alive=""
for pid in ${still_alive}; do
  if kill -0 "${pid}" >/dev/null 2>&1; then
    final_alive="${final_alive} ${pid}"
  fi
done
final_alive="${final_alive# }"

if [[ -z "${final_alive}" ]]; then
  echo "[free-port] Freed port ${port}."
  exit 0
fi

echo "[free-port] Failed to kill PID(s): ${final_alive} (insufficient permissions?)." >&2
exit 1

