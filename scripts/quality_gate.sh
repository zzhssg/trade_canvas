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
  - file-size gates (py/ts/tsx/hook)
  - python structure gates (function params/dataclass fields)
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
  if [[ "${#all_candidates[@]}" -gt 0 ]]; then
    for path in "${all_candidates[@]}"; do
      if [[ -f "$path" ]] && is_production_file "$path"; then
        echo "$path"
      fi
    done | sort -u
  fi
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

line_count_in_ref() {
  local ref="$1"
  local path="$2"
  if ! git cat-file -e "${ref}:${path}" 2>/dev/null; then
    echo ""
    return 0
  fi
  git show "${ref}:${path}" | wc -l | awk '{print $1}'
}

enforce_line_limit() {
  local path="$1"
  local line_count="$2"
  local limit="$3"
  local label="$4"

  if [[ "$line_count" -le "$limit" ]]; then
    return 0
  fi

  if [[ "$check_all" -eq 0 && -n "$base_ref" ]]; then
    local base_line_count
    base_line_count="$(line_count_in_ref "$base_ref" "$path")"
    if [[ -n "$base_line_count" && "$base_line_count" -gt "$limit" ]]; then
      if [[ "$line_count" -le "$base_line_count" ]]; then
        if [[ "$line_count" -lt "$base_line_count" ]]; then
          echo "[quality-gate] NOTE: ${label} still over limit but reduced: ${path} (${base_line_count} -> ${line_count}, limit ${limit})"
        fi
        return 0
      fi
      mark_failure "${label} still over limit and grew: ${path} (${base_line_count} -> ${line_count}, limit ${limit})"
      return 0
    fi
  fi

  mark_failure "${label} exceeds ${limit} lines: ${path} (${line_count})"
}

check_line_limits() {
  local path="$1"
  local line_count
  line_count="$(wc -l <"$path" | awk '{print $1}')"
  local base_name
  base_name="$(basename "$path")"

  if [[ "$path" == *.py ]]; then
    enforce_line_limit "$path" "$line_count" 300 "Python file"
  fi

  if [[ "$path" == *.tsx ]]; then
    enforce_line_limit "$path" "$line_count" 400 "TSX component"
  fi

  if [[ "$path" == *.ts && "$path" != *.d.ts && "$base_name" != use* ]]; then
    case "$path" in
      frontend/src/contracts/openapi.ts) ;;
      *)
        enforce_line_limit "$path" "$line_count" 300 "TS module"
        ;;
    esac
  fi

  if [[ "$base_name" == use*.ts || "$base_name" == use*.tsx ]]; then
    enforce_line_limit "$path" "$line_count" 150 "Hook file"
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

collect_python_structure_issues() {
  local display_path="$1"
  local source_path="$2"
  python3 - "$display_path" "$source_path" <<'PY'
from __future__ import annotations

import ast
import sys
from pathlib import Path

MAX_PARAMS = 8
MAX_FIELDS = 15

display_path = Path(sys.argv[1])
source_path = Path(sys.argv[2])
source = source_path.read_text(encoding="utf-8")
problems: list[str] = []

try:
    tree = ast.parse(source)
except SyntaxError as exc:
    print(f"{display_path}:{exc.lineno}: syntax parse failed during quality gate: {exc.msg}")
    raise SystemExit(0)

for parent in ast.walk(tree):
    for child in ast.iter_child_nodes(parent):
        child._parent = parent  # type: ignore[attr-defined]


def _is_dataclass_decorator(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "dataclass"
    if isinstance(node, ast.Attribute):
        return node.attr == "dataclass"
    if isinstance(node, ast.Call):
        return _is_dataclass_decorator(node.func)
    return False


def _is_classvar(node: ast.AST | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return node.id == "ClassVar"
    if isinstance(node, ast.Attribute):
        return node.attr == "ClassVar"
    if isinstance(node, ast.Subscript):
        return _is_classvar(node.value)
    return False


def _parameter_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    args = node.args
    count = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
    if args.vararg is not None:
        count += 1
    if args.kwarg is not None:
        count += 1

    parent = getattr(node, "_parent", None)
    if isinstance(parent, ast.ClassDef) and args.args:
        first_name = args.args[0].arg
        if first_name in {"self", "cls"}:
            count -= 1
    return count


for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        count = _parameter_count(node)
        if count > MAX_PARAMS:
            problems.append(
                f"{display_path}:{node.lineno}: function `{node.name}` has {count} params (max {MAX_PARAMS})"
            )
        continue

    if isinstance(node, ast.ClassDef):
        if not any(_is_dataclass_decorator(deco) for deco in node.decorator_list):
            continue
        field_count = 0
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                if _is_classvar(stmt.annotation):
                    continue
                field_count += 1
        if field_count > MAX_FIELDS:
            problems.append(
                f"{display_path}:{node.lineno}: dataclass `{node.name}` has {field_count} fields (max {MAX_FIELDS})"
            )

if problems:
    print("\n".join(problems))
PY
}

normalize_python_structure_issues() {
  sed -E 's/^[^:]+:[0-9]+:[[:space:]]*//' | awk 'NF' | sort -u
}

check_python_structure_limits() {
  local path="$1"
  if [[ "$path" != *.py ]]; then
    return 0
  fi

  local issues
  issues="$(collect_python_structure_issues "$path" "$path")"
  if [[ -z "$issues" ]]; then
    return 0
  fi

  if [[ "$check_all" -eq 0 && -n "$base_ref" ]] && git cat-file -e "${base_ref}:${path}" 2>/dev/null; then
    local base_tmp
    base_tmp="$(mktemp)"
    git show "${base_ref}:${path}" >"$base_tmp"
    local base_issues
    base_issues="$(collect_python_structure_issues "$path" "$base_tmp")"
    rm -f "$base_tmp"

    local current_norm
    current_norm="$(printf '%s\n' "$issues" | normalize_python_structure_issues)"
    local base_norm
    base_norm="$(printf '%s\n' "$base_issues" | normalize_python_structure_issues)"
    local new_norm
    if [[ -n "$base_norm" ]]; then
      new_norm="$(comm -23 <(printf '%s\n' "$current_norm") <(printf '%s\n' "$base_norm"))"
    else
      new_norm="$current_norm"
    fi
    if [[ -z "$new_norm" ]]; then
      return 0
    fi
    while IFS= read -r issue; do
      if [[ -n "$issue" ]]; then
        echo "${path}: ${issue}" >&2
      fi
    done <<<"$new_norm"
    mark_failure "Python structure limit introduced/regressed in ${path}"
    return 0
  fi

  echo "$issues" >&2
  mark_failure "Python structure limit exceeded in ${path}"
}

if [[ "${#prod_files[@]}" -gt 0 ]]; then
  for path in "${prod_files[@]}"; do
    check_line_limits "$path"
    check_banned_markers "$path"
    check_python_structure_limits "$path"
  done
fi

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
  if [[ "${#all_candidates[@]}" -gt 0 ]]; then
    for path in "${all_candidates[@]}"; do
      if [[ -f "$path" && "$path" == *.py ]]; then
        echo "$path"
      fi
    done | sort -u
  fi
)

frontend_changes=()
while IFS= read -r line; do
  frontend_changes+=("$line")
done < <(
  if [[ "${#all_candidates[@]}" -gt 0 ]]; then
    for path in "${all_candidates[@]}"; do
      if [[ -f "$path" && ("$path" == frontend/src/* || "$path" == frontend/package.json || "$path" == frontend/tsconfig*.json) ]]; then
        echo "$path"
      fi
    done | sort -u
  fi
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
