#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

hits="$({
  rg -n "(sqlite3?\\b|TRADE_CANVAS_ENABLE_SQLITE_STORE)" \
    backend/app trade_canvas scripts conftest.py backend/tests tests \
    --glob '!scripts/no_sqlite_guard.sh' \
    --glob '!scripts/quality_gate.sh'
} || true)"

if [[ -n "$hits" ]]; then
  echo "FAIL: SQLite residue detected in active code paths:" >&2
  echo "$hits" >&2
  exit 1
fi

echo "[no-sqlite-guard] OK"
