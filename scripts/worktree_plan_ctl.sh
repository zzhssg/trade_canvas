#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/worktree_plan_ctl.sh show
  bash scripts/worktree_plan_ctl.sh bind <plan_path>
  bash scripts/worktree_plan_ctl.sh status <status>

Examples:
  bash scripts/worktree_plan_ctl.sh bind docs/plan/2026-02-09-project-console.md
  bash scripts/worktree_plan_ctl.sh status 开发中
  bash scripts/worktree_plan_ctl.sh status 待验收

Notes:
  - plan_path 必须是相对仓库根目录的路径（例如 docs/plan/...）
  - status 实际由 docs/scripts/doc_set_status.sh 处理（支持 草稿/开发中/待验收/已完成/已上线）
EOF
}

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

command="$1"
shift || true

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${repo_root}" ]]; then
  echo "ERROR: not in git repository" >&2
  exit 2
fi

repo_root="$(cd "${repo_root}" && pwd)"
common_dir_raw="$(git -C "${repo_root}" rev-parse --git-common-dir)"
if [[ "${common_dir_raw}" = /* ]]; then
  common_dir="${common_dir_raw}"
else
  common_dir="${repo_root}/${common_dir_raw}"
fi
common_dir="$(cd "${common_dir}" && pwd)"
main_root="$(cd "${common_dir}/.." && pwd)"

worktree_id="$(
  python3 - "${repo_root}" <<'PY'
import hashlib
import sys
print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:8])
PY
)"

metadata_dir="${main_root}/.worktree-meta"
metadata_file="${metadata_dir}/${worktree_id}.json"

ensure_metadata_file() {
  mkdir -p "${metadata_dir}"
  if [[ ! -f "${metadata_file}" ]]; then
    python3 - "${metadata_file}" <<'PY'
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
import sys

path = sys.argv[1]
payload = {
    "id": os.path.basename(path).replace(".json", ""),
    "description": "",
    "plan_path": None,
    "created_at": datetime.now(timezone.utc).isoformat(),
    "owner": os.environ.get("USER"),
    "ports": {},
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, ensure_ascii=False)
PY
  fi
}

read_plan_path() {
  if [[ ! -f "${metadata_file}" ]]; then
    return 0
  fi
  python3 - "${metadata_file}" <<'PY'
from __future__ import annotations

import json
import sys

path = sys.argv[1]
try:
    data = json.load(open(path, "r", encoding="utf-8"))
except Exception:
    sys.exit(0)
value = (data.get("plan_path") or "").strip()
if value:
    print(value)
PY
}

update_plan_path() {
  local plan_path="$1"
  ensure_metadata_file
  python3 - "${metadata_file}" "${plan_path}" <<'PY'
from __future__ import annotations

import json
import sys

meta_path, plan_path = sys.argv[1], sys.argv[2]
data = json.load(open(meta_path, "r", encoding="utf-8"))
data["plan_path"] = plan_path
with open(meta_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
PY
}

case "${command}" in
  show)
    current_plan="$(read_plan_path || true)"
    echo "worktree: ${repo_root}"
    echo "main_root: ${main_root}"
    echo "worktree_id: ${worktree_id}"
    echo "metadata: ${metadata_file}"
    echo "plan_path: ${current_plan:-<none>}"
    ;;
  bind)
    if [[ $# -ne 1 ]]; then
      usage >&2
      exit 2
    fi
    plan_path="$1"
    if [[ "${plan_path}" = /* ]]; then
      echo "ERROR: plan_path must be repo-relative: ${plan_path}" >&2
      exit 2
    fi
    plan_abs="${repo_root}/${plan_path}"
    if [[ ! -f "${plan_abs}" ]]; then
      echo "ERROR: plan file not found: ${plan_path}" >&2
      exit 2
    fi
    update_plan_path "${plan_path}"
    echo "OK: bound plan_path=${plan_path} for worktree_id=${worktree_id}"
    ;;
  status)
    if [[ $# -ne 1 ]]; then
      usage >&2
      exit 2
    fi
    status="$1"
    plan_path="$(read_plan_path || true)"
    if [[ -z "${plan_path}" ]]; then
      echo "ERROR: no plan_path bound for current worktree. run bind first." >&2
      exit 2
    fi
    plan_abs="${repo_root}/${plan_path}"
    if [[ ! -f "${plan_abs}" ]]; then
      echo "ERROR: bound plan file missing: ${plan_path}" >&2
      exit 2
    fi
    (
      cd "${repo_root}"
      bash "docs/scripts/doc_set_status.sh" "${status}" "${plan_path}"
    )
    echo "OK: updated ${plan_path} -> ${status}"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
