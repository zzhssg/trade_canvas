#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$repo_root"

python3 -m pytest backend/tests/test_market_candles.py -q
python3 -m pytest backend/tests/test_market_ws.py -q
python3 -m pytest backend/tests/test_ingest_ccxt_loop_mapping.py -q
python3 -m pytest backend/tests/test_history_bootstrapper.py -q
python3 -m pytest backend/tests/test_e2e_user_story_market_sync.py -q

echo "OK: backend fastpath v2 checks passed."
