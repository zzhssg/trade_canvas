#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/quality_gate.sh [--base <ref>] [--all] [--delete-list <path>] [--fast]

Purpose:
  Enforce clean-code gates for trade_canvas:
  - no compatibility/legacy markers in changed production files
  - no TODO/FIXME/HACK debt markers in changed production files
  - file-size gates (py/tsx/hook)
  - optional delete-list check for legacy removal
  - run pytest/frontend build based on touched area

Options:
  --base <ref>          Include diff against git ref (e.g. main)
  --all                 Check all tracked files instead of changed files
  --delete-list <path>  Newline file with legacy paths that must be deleted
  --fast                Skip pytest and frontend build (structure checks only)
  -h, --help            Show help
USAGE
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

base_ref=""
check_all=0
delete_list=""
run_pytest=1
run_frontend_build=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base)
      base_ref="$2"
      shift 2
      ;;
    --all)
      check_all=1
      shift
      ;;
    --delete-list)
      delete_list="$2"
      shift 2
      ;;
    --fast)
      run_pytest=0
      run_frontend_build=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown arg: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -n "$base_ref" ]]; then
  if ! git rev-parse --verify --quiet "$base_ref" >/dev/null; then
    echo "ERROR: --base ref not found: $base_ref" >&2
    exit 2
  fi
fi

if [[ -n "$delete_list" && ! -f "$delete_list" ]]; then
  echo "ERROR: --delete-list file not found: $delete_list" >&2
  exit 2
fi

all_candidates=()
while IFS= read -r line; do
  all_candidates+=("$line")
done < <(
  {
    if [[ "$check_all" -eq 1 ]]; then
      git ls-files
    else
      if [[ -n "$base_ref" ]]; then
        git diff --name-only --diff-filter=ACMR "$base_ref...HEAD"
      fi
      git diff --name-only --diff-filter=ACMR
      git diff --cached --name-only --diff-filter=ACMR
      git ls-files --others --exclude-standard
    fi
  } | awk 'NF' | sort -u
)

is_production_file() {
  local path="$1"

  case "$path" in
    backend/*|trade_canvas/*|frontend/src/*|freqtrade_user_data/*) ;;
    *) return 1 ;;
  esac

  case "$path" in
    tests/*|*/tests/*|*.test.*|*.spec.*|test_*.py) return 1 ;;
  esac

  case "$path" in
    *.py|*.ts|*.tsx|*.js|*.jsx) return 0 ;;
  esac
  return 1
}

prod_files=()
while IFS= read -r line; do
  prod_files+=("$line")
done < <(
  for path in "${all_candidates[@]}"; do
    if [[ -f "$path" ]] && is_production_file "$path"; then
      echo "$path"
    fi
  done | sort -u
)

if [[ "${#prod_files[@]}" -eq 0 ]]; then
  echo "[quality-gate] No changed production files detected. Skip structure checks."
fi

failures=0

mark_failure() {
  local message="$1"
  echo "FAIL: $message" >&2
  failures=1
}

check_line_limits() {
  local path="$1"
  local line_count
  line_count="$(wc -l <"$path" | awk '{print $1}')"
  local base_name
  base_name="$(basename "$path")"

  if [[ "$path" == *.py && "$line_count" -gt 300 ]]; then
    mark_failure "Python file exceeds 300 lines: ${path} (${line_count})"
  fi

  if [[ "$path" == *.tsx && "$line_count" -gt 400 ]]; then
    mark_failure "TSX component exceeds 400 lines: ${path} (${line_count})"
  fi

  if [[ ("$base_name" == use*.ts || "$base_name" == use*.tsx) && "$line_count" -gt 150 ]]; then
    mark_failure "Hook file exceeds 150 lines: ${path} (${line_count})"
  fi
}

check_banned_markers() {
  local path="$1"
  local compat_pattern
  compat_pattern='\b(legacy|compat(?:ibility)?|deprecated|backward[_-]?compat|dual[_-]?write|legacy_path|compat_mode)\b|遗留|兼容'
  local debt_pattern
  debt_pattern='\b(TODO|FIXME|HACK)\b'

  local compat_hits
  compat_hits="$(
    rg -n -i --color never "$compat_pattern" "$path" 2>/dev/null \
      | rg -v "quality: allow-compat-token" || true
  )"
  if [[ -n "$compat_hits" ]]; then
    echo "$compat_hits" >&2
    mark_failure "Compatibility/legacy marker found in ${path}"
  fi

  local debt_hits
  debt_hits="$(
    rg -n --color never "$debt_pattern" "$path" 2>/dev/null \
      | rg -v "quality: allow-temporary" || true
  )"
  if [[ -n "$debt_hits" ]]; then
    echo "$debt_hits" >&2
    mark_failure "Debt marker (TODO/FIXME/HACK) found in ${path}"
  fi
}

for path in "${prod_files[@]}"; do
  check_line_limits "$path"
  check_banned_markers "$path"
done

if [[ -n "$delete_list" ]]; then
  while IFS= read -r raw_line; do
    line="$(echo "$raw_line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    if [[ -z "$line" || "$line" == \#* ]]; then
      continue
    fi
    if [[ -e "$line" ]]; then
      mark_failure "Delete-list path still exists: $line"
    fi
  done <"$delete_list"
fi

if [[ -x "scripts/no_sqlite_guard.sh" ]]; then
  echo "[quality-gate] Running no-sqlite guard ..."
  if ! bash scripts/no_sqlite_guard.sh; then
    mark_failure "scripts/no_sqlite_guard.sh failed"
  fi
fi

py_changes=()
while IFS= read -r line; do
  py_changes+=("$line")
done < <(
  for path in "${all_candidates[@]}"; do
    if [[ -f "$path" && "$path" == *.py ]]; then
      echo "$path"
    fi
  done | sort -u
)

frontend_changes=()
while IFS= read -r line; do
  frontend_changes+=("$line")
done < <(
  for path in "${all_candidates[@]}"; do
    if [[ -f "$path" && ("$path" == frontend/src/* || "$path" == frontend/package.json || "$path" == frontend/tsconfig*.json) ]]; then
      echo "$path"
    fi
  done | sort -u
)

if [[ "$run_pytest" -eq 1 && "${#py_changes[@]}" -gt 0 ]]; then
  echo "[quality-gate] Running pytest -q ..."
  if ! pytest -q; then
    mark_failure "pytest -q failed"
  fi
fi

if [[ "$run_frontend_build" -eq 1 && "${#frontend_changes[@]}" -gt 0 ]]; then
  echo "[quality-gate] Running frontend build ..."
  if ! (cd frontend && npm run build); then
    mark_failure "cd frontend && npm run build failed"
  fi
fi

if [[ "$failures" -ne 0 ]]; then
  echo "[quality-gate] FAILED" >&2
  exit 1
fi

echo "[quality-gate] OK"
