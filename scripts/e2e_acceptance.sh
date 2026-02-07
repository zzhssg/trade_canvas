#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/e2e_acceptance.sh [--reuse-servers] [--smoke] [--skip-playwright-install] [--skip-doc-audit] [-- <playwright args...>]

Runs the FE/BE integration E2E gate (Playwright):
  mock feed (HTTP ingest) → store → API → frontend (HTTP catchup + WS follow)

Environment overrides (optional):
  E2E_BACKEND_HOST=127.0.0.1
  E2E_BACKEND_PORT=8000
  E2E_FRONTEND_HOST=127.0.0.1
  E2E_FRONTEND_PORT=5173
  E2E_SMOKE=1
    - Run only tests tagged with `@smoke` (fast local loop; do not use for final delivery).
  E2E_SKIP_PLAYWRIGHT_INSTALL=1
    - Skip `npx playwright install chromium` (fast local loop if browsers are already cached).
  E2E_SKIP_DOC_AUDIT=1
    - Skip `bash docs/scripts/doc_audit.sh` (fast local loop; do not use for final delivery).

  Optional doc/plan gate (recommended when claiming "done"):
  E2E_PLAN_DOC=docs/plan/....md
    - Requires the plan doc front matter status to be done/已完成/online/已上线
    - Requires updated: to be today's date
EOF
}

reuse_servers=0
smoke=0
skip_playwright_install=0
skip_doc_audit=0
pw_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reuse-servers) reuse_servers=1; shift ;;
    --smoke) smoke=1; shift ;;
    --skip-playwright-install) skip_playwright_install=1; shift ;;
    --skip-doc-audit) skip_doc_audit=1; shift ;;
    --) shift; pw_args+=("$@"); break ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

backend_host="${E2E_BACKEND_HOST:-127.0.0.1}"
backend_port="${E2E_BACKEND_PORT:-8000}"
frontend_host="${E2E_FRONTEND_HOST:-127.0.0.1}"
frontend_port="${E2E_FRONTEND_PORT:-5173}"
smoke="${E2E_SMOKE:-$smoke}"
skip_playwright_install="${E2E_SKIP_PLAYWRIGHT_INSTALL:-$skip_playwright_install}"
skip_doc_audit="${E2E_SKIP_DOC_AUDIT:-$skip_doc_audit}"

backend_base="http://${backend_host}:${backend_port}"
frontend_base="http://${frontend_host}:${frontend_port}"

ensure_no_proxy() {
  local extra="$1"
  local cur="${NO_PROXY:-${no_proxy:-}}"
  if [[ -z "${cur}" ]]; then
    cur="$extra"
  else
    # Append entries not already present (comma separated).
    IFS=',' read -r -a extras <<<"${extra}"
    local e
    for e in "${extras[@]}"; do
      e="$(echo "$e" | xargs || true)"
      [[ -z "$e" ]] && continue
      if [[ ",${cur}," != *",${e},"* ]]; then
        cur="${cur},${e}"
      fi
    done
  fi
  export NO_PROXY="${cur}"
  export no_proxy="${cur}"
}

# Avoid hanging local curl healthchecks under environments with http_proxy/https_proxy set.
ensure_no_proxy "localhost,127.0.0.1,::1,${backend_host},${frontend_host}"

is_listening() {
  local host="$1"
  local port="$2"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  if command -v nc >/dev/null 2>&1; then
    nc -z "$host" "$port" >/dev/null 2>&1
    return $?
  fi
  return 1
}

wait_http_ok() {
  local url="$1"
  local name="$2"
  local i
  for i in {1..80}; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  echo "ERROR: timeout waiting for ${name} at ${url}" >&2
  return 1
}

backend_pid=""
frontend_pid=""
e2e_db_path=""

kill_listeners() {
  local port="$1"
  local pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  fi
  if [[ -n "$pids" ]]; then
    kill $pids >/dev/null 2>&1 || true
  fi
}

cleanup() {
  set +e
  # We start servers in the background; kill their whole process groups to avoid leaving orphaned children
  # (e.g. `npm run dev` -> node) after the script exits.
  if [[ -n "${frontend_pid}" ]]; then
    kill -- -"${frontend_pid}" >/dev/null 2>&1 || kill "${frontend_pid}" >/dev/null 2>&1 || true
    kill_listeners "$frontend_port"
  fi
  if [[ -n "${backend_pid}" ]]; then
    kill -- -"${backend_pid}" >/dev/null 2>&1 || kill "${backend_pid}" >/dev/null 2>&1 || true
    kill_listeners "$backend_port"
  fi
  if [[ -n "${e2e_db_path}" ]]; then
    rm -f "${e2e_db_path}" "${e2e_db_path}-wal" "${e2e_db_path}-shm" 2>/dev/null || true
  fi
}
trap cleanup EXIT

mkdir -p output/playwright

if is_listening "$backend_host" "$backend_port"; then
  if [[ "$reuse_servers" -ne 1 ]]; then
    echo "ERROR: backend port already in use: ${backend_port} (use --reuse-servers to reuse)" >&2
    echo "Hint: free it with \`bash scripts/free_port.sh ${backend_port}\`." >&2
    exit 2
  fi
else
  if [[ ! -f ".env/bin/activate" ]]; then
    echo "ERROR: missing venv at ./.env (needed by scripts/dev_backend.sh)" >&2
    exit 2
  fi
  # Unique sqlite db per run to avoid cross-run interference when rerunning the E2E gate locally.
  ts="$(date +%s)"
  e2e_db_path="backend/data/market_e2e_${backend_port}_${ts}_$$.db"
  rm -f "${e2e_db_path}" "${e2e_db_path}-wal" "${e2e_db_path}-shm" 2>/dev/null || true
  (
    export TRADE_CANVAS_DB_PATH="${e2e_db_path}"
    export TRADE_CANVAS_ENABLE_WHITELIST_INGEST="0"
    export TRADE_CANVAS_ENABLE_ONDEMAND_INGEST="0"
    export TRADE_CANVAS_ENABLE_DEBUG_API="1"
    export TRADE_CANVAS_FREQTRADE_MOCK="1"
    # Pin ingest flags for deterministic E2E (avoid inheriting dev shell env).
    export TRADE_CANVAS_ENABLE_FACTOR_INGEST="1"
    export TRADE_CANVAS_ENABLE_OVERLAY_INGEST="1"
    export TRADE_CANVAS_ENABLE_REPLAY_V1="${TRADE_CANVAS_ENABLE_REPLAY_V1:-1}"
    export TRADE_CANVAS_ENABLE_REPLAY_ENSURE_COVERAGE="${TRADE_CANVAS_ENABLE_REPLAY_ENSURE_COVERAGE:-1}"
    export TRADE_CANVAS_PIVOT_WINDOW_MAJOR="${TRADE_CANVAS_PIVOT_WINDOW_MAJOR:-50}"
    export TRADE_CANVAS_PIVOT_WINDOW_MINOR="${TRADE_CANVAS_PIVOT_WINDOW_MINOR:-5}"
    export TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES="${TRADE_CANVAS_FACTOR_LOOKBACK_CANDLES:-20000}"
    export TRADE_CANVAS_OVERLAY_WINDOW_CANDLES="${TRADE_CANVAS_OVERLAY_WINDOW_CANDLES:-2000}"
    # When overriding frontend ports for parallel runs, ensure backend CORS allows that origin.
    export TRADE_CANVAS_CORS_ORIGINS="${TRADE_CANVAS_CORS_ORIGINS:-http://localhost:${frontend_port},http://127.0.0.1:${frontend_port},http://localhost:5173,http://127.0.0.1:5173}"
    bash scripts/dev_backend.sh --no-reload --host "$backend_host" --port "$backend_port"
  ) &
  backend_pid="$!"
fi

if is_listening "$frontend_host" "$frontend_port"; then
  if [[ "$reuse_servers" -ne 1 ]]; then
    echo "ERROR: frontend port already in use: ${frontend_port} (use --reuse-servers to reuse)" >&2
    echo "Hint: free it with \`node frontend/scripts/free-port.mjs ${frontend_port}\`." >&2
    exit 2
  fi
else
  (
    cd frontend
    export VITE_API_BASE="$backend_base"
    export VITE_API_BASE_URL="$backend_base"
    export VITE_ENABLE_REPLAY_V1="${VITE_ENABLE_REPLAY_V1:-1}"
    export VITE_ENABLE_REPLAY_PACKAGE_V1="${VITE_ENABLE_REPLAY_PACKAGE_V1:-0}"
    npm run dev -- --host "$frontend_host" --port "$frontend_port"
  ) &
  frontend_pid="$!"
fi

wait_http_ok "${backend_base}/api/market/whitelist" "backend"
wait_http_ok "${frontend_base}/" "frontend"

(
  cd frontend
  export E2E_BASE_URL="$frontend_base"
  export E2E_API_BASE_URL="$backend_base"

  if [[ "${smoke}" == "1" ]]; then
    has_grep=0
    for a in "${pw_args[@]+"${pw_args[@]}"}"; do
      if [[ "$a" == "--grep" || "$a" == "-g" ]]; then
        has_grep=1
        break
      fi
    done
    if [[ "$has_grep" -ne 1 ]]; then
      pw_args+=("--grep" "@smoke")
    fi
  fi

  if [[ "${skip_playwright_install}" != "1" ]]; then
    npx playwright install chromium
  fi
  if [[ "${#pw_args[@]}" -gt 0 ]]; then
    npx playwright test "${pw_args[@]}"
  else
    npx playwright test
  fi
)

echo
echo "[e2e_acceptance] OK: Playwright E2E passed."

if [[ "${skip_doc_audit}" != "1" && -x "docs/scripts/doc_audit.sh" ]]; then
  echo "[e2e_acceptance] Running docs audit..."
  bash "docs/scripts/doc_audit.sh"
elif [[ "${skip_doc_audit}" == "1" ]]; then
  echo "[e2e_acceptance] NOTE: skipping docs audit (E2E_SKIP_DOC_AUDIT=1 / --skip-doc-audit)."
fi

if [[ -n "${E2E_PLAN_DOC:-}" ]]; then
  python3 - "$E2E_PLAN_DOC" <<'PY'
from __future__ import annotations

import sys
from datetime import date


def read_frontmatter(path: str) -> dict[str, str]:
    with open(path, "r", encoding="utf-8") as f:
        if f.readline().strip() != "---":
            raise ValueError("missing YAML front matter (first line must be ---)")
        out: dict[str, str] = {}
        for line in f:
            s = line.rstrip("\n")
            if s.strip() == "---":
                return out
            if ":" not in s:
                continue
            k, v = s.split(":", 1)
            k = k.strip()
            v = v.strip()
            if k:
                out[k] = v
    raise ValueError("unterminated YAML front matter (missing closing ---)")


path = sys.argv[1]
meta = read_frontmatter(path)
status = (meta.get("status") or "").strip()
updated = (meta.get("updated") or "").strip()

allowed = {"done", "已完成", "online", "已上线"}
if status not in allowed:
    raise SystemExit(
        f"[e2e_acceptance] FAIL: {path} status must be done/已完成/online/已上线, got {status!r}"
    )

today = date.today().isoformat()
if updated != today:
    raise SystemExit(f"[e2e_acceptance] FAIL: {path} updated must be {today}, got {updated!r}")

print(f"[e2e_acceptance] OK: plan status gate passed ({path})")
PY
else
  echo "[e2e_acceptance] NOTE: set E2E_PLAN_DOC=docs/plan/<...>.md to enforce plan status update."
fi
