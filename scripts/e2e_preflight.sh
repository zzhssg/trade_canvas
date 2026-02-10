#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/e2e_preflight.sh --backend-base <url> [--timeout-s <sec>] [--skip-demo-strategy]

Checks deterministic E2E assumptions against a running backend service:
  1) ingest/candle_closed is writable
  2) market/candles is readable and returns the probe series
  3) (default) backtest/strategies contains DemoStrategy

Options:
  --backend-base <url>    Backend base URL (e.g. http://127.0.0.1:8000)
  --timeout-s <sec>       Per-request timeout seconds (default: 8)
  --skip-demo-strategy    Skip the DemoStrategy check
USAGE
}

backend_base=""
timeout_s=8
require_demo_strategy=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-base)
      backend_base="$2"
      shift 2
      ;;
    --timeout-s)
      timeout_s="$2"
      shift 2
      ;;
    --skip-demo-strategy)
      require_demo_strategy=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$backend_base" ]]; then
  echo "ERROR: missing --backend-base" >&2
  usage
  exit 2
fi

if ! [[ "$timeout_s" =~ ^[0-9]+$ ]] || [[ "$timeout_s" -le 0 ]]; then
  echo "ERROR: --timeout-s must be a positive integer, got: $timeout_s" >&2
  exit 2
fi

tmp_ingest="$(mktemp)"
tmp_candles="$(mktemp)"
tmp_strategies="$(mktemp)"
cleanup() {
  rm -f "$tmp_ingest" "$tmp_candles" "$tmp_strategies" 2>/dev/null || true
}
trap cleanup EXIT

probe_symbol="E2EPROBE${RANDOM}${RANDOM}"
probe_series="binance:futures:${probe_symbol}/USDT:1m"
probe_time="$(date +%s)"
probe_time="$((probe_time - probe_time % 60))"

ingest_code="$(
  curl -sS --max-time "$timeout_s" -o "$tmp_ingest" -w '%{http_code}' \
    -H 'content-type: application/json' \
    -X POST "${backend_base}/api/market/ingest/candle_closed" \
    -d "{\"series_id\":\"${probe_series}\",\"candle\":{\"candle_time\":${probe_time},\"open\":1,\"high\":2,\"low\":0.5,\"close\":1.5,\"volume\":10}}"
)"
if [[ "$ingest_code" != "200" ]]; then
  echo "ERROR: e2e_preflight ingest probe failed (HTTP ${ingest_code})." >&2
  cat "$tmp_ingest" >&2 || true
  exit 2
fi

candles_code="$(
  curl -sS --max-time "$timeout_s" -o "$tmp_candles" -w '%{http_code}' \
    "${backend_base}/api/market/candles?series_id=${probe_series}&limit=1"
)"
if [[ "$candles_code" != "200" ]]; then
  echo "ERROR: e2e_preflight candles probe failed (HTTP ${candles_code})." >&2
  cat "$tmp_candles" >&2 || true
  echo "Hint: backend may be blocked by non-deterministic backfill config." >&2
  exit 2
fi

python3 - "$tmp_candles" "$probe_series" <<'PY'
from __future__ import annotations

import json
import sys

path, expected_series = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    payload = json.load(f)
if str(payload.get("series_id") or "") != expected_series:
    raise SystemExit("e2e_preflight failed: series_id mismatch in candles response")
candles = payload.get("candles") or []
if len(candles) < 1:
    raise SystemExit("e2e_preflight failed: candles response is empty")
PY

if [[ "$require_demo_strategy" == "1" ]]; then
  strategies_code="$(
    curl -sS --max-time "$timeout_s" -o "$tmp_strategies" -w '%{http_code}' \
      "${backend_base}/api/backtest/strategies"
  )"
  if [[ "$strategies_code" != "200" ]]; then
    echo "ERROR: e2e_preflight strategies probe failed (HTTP ${strategies_code})." >&2
    cat "$tmp_strategies" >&2 || true
    exit 2
  fi

  python3 - "$tmp_strategies" <<'PY'
from __future__ import annotations

import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    payload = json.load(f)
strategies = payload.get("strategies") or []
if "DemoStrategy" not in strategies:
    raise SystemExit(
        "e2e_preflight failed: DemoStrategy missing. "
        "Enable TRADE_CANVAS_FREQTRADE_MOCK=1 or avoid --reuse-servers."
    )
PY
fi

echo "[e2e_preflight] OK: backend readiness checks passed (${backend_base})."
