#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash docs/scripts/doc_set_status.sh <status> <file> [file...]

Status accepts (equivalent aliases):
  draft | 草稿
  in_progress | 开发中
  pending_acceptance | 待验收
  done | 已完成
  online | 已上线
  deprecated | 已废弃

Behavior:
  - Updates YAML front matter field: status:
  - Updates YAML front matter field: updated: to today's YYYY-MM-DD
  - Requires the file to already have a YAML front matter block (--- ... ---)
EOF
}

if [[ $# -lt 2 ]]; then
  usage >&2
  exit 2
fi

status="$1"
shift

python3 - "$status" "$@" <<'PY'
from __future__ import annotations

import sys
from datetime import date

ALIAS = {
    "draft": "draft",
    "草稿": "draft",
    "in_progress": "in_progress",
    "开发中": "in_progress",
    "pending_acceptance": "pending_acceptance",
    "待验收": "pending_acceptance",
    "done": "done",
    "已完成": "done",
    "online": "online",
    "已上线": "online",
    "deprecated": "deprecated",
    "已废弃": "deprecated",
}

CANONICAL = {
    "draft": "draft",
    "in_progress": "in_progress",
    "pending_acceptance": "pending_acceptance",
    "done": "done",
    "online": "online",
    "deprecated": "deprecated",
}


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


raw_status = sys.argv[1].strip()
status_key = ALIAS.get(raw_status)
if status_key is None:
    die(f"invalid status '{raw_status}'")

new_status = CANONICAL[status_key]
new_status_written = raw_status if raw_status in {"草稿", "开发中", "待验收", "已完成", "已上线", "已废弃"} else new_status
today = date.today().isoformat()

paths = sys.argv[2:]
for path in paths:
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        die(f"missing file: {path}")

    if not lines or lines[0].strip() != "---":
        die(f"missing YAML front matter (first line must be ---): {path}")

    # Find closing front matter delimiter.
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        die(f"unterminated YAML front matter (missing closing ---): {path}")

    found_status = False
    found_updated = False
    for i in range(1, end):
        s = lines[i]
        if s.lstrip().startswith("status:"):
            lines[i] = f"status: {new_status_written}\n"
            found_status = True
        elif s.lstrip().startswith("updated:"):
            lines[i] = f"updated: {today}\n"
            found_updated = True

    if not found_status:
        # Insert status after title if present, else at top.
        insert_at = 1
        for i in range(1, end):
            if lines[i].lstrip().startswith("title:"):
                insert_at = i + 1
                break
        lines.insert(insert_at, f"status: {new_status_written}\n")
        end += 1
    if not found_updated:
        # Insert updated near created if present, else append before end.
        insert_at = end
        for i in range(1, end):
            if lines[i].lstrip().startswith("created:"):
                insert_at = i + 1
                break
        lines.insert(insert_at, f"updated: {today}\n")
        end += 1

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)

print(f"OK: updated status={new_status_written}, updated={today} for {len(paths)} file(s)")
PY
