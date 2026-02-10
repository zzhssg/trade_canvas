#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/probe_market_backfill.sh [-- <extra args passed to probe_market_auto_backfill.py>]

默认会执行 live 轮测（全 series）并输出 JSON 报告。

可通过环境变量覆盖：
  MARKET_BACKFILL_PROBE_TRANSPORT=live|app      (默认 live)
  MARKET_BACKFILL_PROBE_ROUNDS=2                (默认 2)
  MARKET_BACKFILL_PROBE_LIMIT=500               (默认 500)
  MARKET_BACKFILL_PROBE_DB_PATH=backend/data/market.db
  MARKET_BACKFILL_PROBE_BASE_URL=http://127.0.0.1:8000
  MARKET_BACKFILL_PROBE_TIMEOUT=25
  MARKET_BACKFILL_PROBE_REPORT_PATH=output/market_backfill_rounds_report_<transport>.json
  MARKET_BACKFILL_PROBE_ENABLE_CCXT_ON_READ=0|1 (仅 app 模式生效)

示例：
  bash scripts/probe_market_backfill.sh
  MARKET_BACKFILL_PROBE_TRANSPORT=app bash scripts/probe_market_backfill.sh
  bash scripts/probe_market_backfill.sh -- --series-id binance:spot:BTC/USDT:1m
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

transport="${MARKET_BACKFILL_PROBE_TRANSPORT:-live}"
rounds="${MARKET_BACKFILL_PROBE_ROUNDS:-2}"
limit="${MARKET_BACKFILL_PROBE_LIMIT:-500}"
db_path="${MARKET_BACKFILL_PROBE_DB_PATH:-backend/data/market.db}"
base_url="${MARKET_BACKFILL_PROBE_BASE_URL:-http://127.0.0.1:8000}"
timeout_s="${MARKET_BACKFILL_PROBE_TIMEOUT:-25}"
report_path="${MARKET_BACKFILL_PROBE_REPORT_PATH:-output/market_backfill_rounds_report_${transport}.json}"
enable_ccxt_on_read="${MARKET_BACKFILL_PROBE_ENABLE_CCXT_ON_READ:-0}"

extra_args=()
if [[ "${1:-}" == "--" ]]; then
  shift
  extra_args=("$@")
elif [[ $# -gt 0 ]]; then
  extra_args=("$@")
fi

cmd=(
  python3 scripts/probe_market_auto_backfill.py
  --transport "$transport"
  --rounds "$rounds"
  --limit "$limit"
  --db-path "$db_path"
  --base-url "$base_url"
  --request-timeout "$timeout_s"
  --report-path "$report_path"
)

if [[ "$enable_ccxt_on_read" == "1" ]]; then
  cmd+=(--enable-ccxt-on-read)
fi

if [[ ${#extra_args[@]} -gt 0 ]]; then
  cmd+=("${extra_args[@]}")
fi

echo "[probe_market_backfill] transport=${transport} rounds=${rounds} limit=${limit}"
echo "[probe_market_backfill] report=${report_path}"
"${cmd[@]}"
