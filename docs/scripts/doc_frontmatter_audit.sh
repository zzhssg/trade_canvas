#!/usr/bin/env bash
set -euo pipefail

repo_root="${1:-.}"
cd "$repo_root"

if [[ ! -d "docs" ]]; then
  echo "ERROR: missing ./docs directory" >&2
  exit 2
fi

python3 - <<'PY'
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from datetime import date

ALLOWED_STATUS = {
    "draft": "draft/草稿",
    "草稿": "draft/草稿",
    "in_progress": "in_progress/开发中",
    "开发中": "in_progress/开发中",
    "done": "done/已完成",
    "已完成": "done/已完成",
    "deprecated": "deprecated/已废弃",
    "已废弃": "deprecated/已废弃",
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_PLACEHOLDERS = {"YYYY-MM-DD"}


def read_frontmatter(path: str) -> dict[str, str] | None:
    with open(path, "r", encoding="utf-8") as f:
        first = f.readline()
        if first.strip() != "---":
            return None
        meta: dict[str, str] = {}
        for line in f:
            s = line.rstrip("\n")
            if s.strip() == "---":
                return meta
            if not s.strip() or s.lstrip().startswith("#"):
                continue
            # Minimal "key: value" parsing; ignore nested YAML.
            if ":" not in s:
                continue
            key, value = s.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            meta[key] = value
        return None


def cmp_dates(created: str, updated: str) -> bool:
    return updated >= created


violations: list[str] = []
by_status: dict[str, list[str]] = defaultdict(list)
files_with_frontmatter = 0

for root, dirs, files in os.walk("docs"):
    # Skip typical junk if present.
    dirs[:] = [d for d in dirs if d not in ("node_modules", ".git")]
    for name in files:
        if not name.endswith(".md"):
            continue
        path = os.path.join(root, name)
        meta = read_frontmatter(path)
        if meta is None:
            continue
        files_with_frontmatter += 1
        status = meta.get("status", "").strip()
        created = meta.get("created", "").strip()
        updated = meta.get("updated", "").strip()

        if not status:
            violations.append(f"Missing status: {path}")
            continue

        if status not in ALLOWED_STATUS:
            violations.append(
                f"Invalid status '{status}' (allowed: {', '.join(sorted(set(ALLOWED_STATUS.values())))}): {path}"
            )
        by_status[ALLOWED_STATUS.get(status, status)].append(path)

        if created and created not in DATE_PLACEHOLDERS and not DATE_RE.match(created):
            violations.append(f"Invalid created '{created}' (YYYY-MM-DD): {path}")
        if updated and updated not in DATE_PLACEHOLDERS and not DATE_RE.match(updated):
            violations.append(f"Invalid updated '{updated}' (YYYY-MM-DD): {path}")
        if (
            created
            and updated
            and created not in DATE_PLACEHOLDERS
            and updated not in DATE_PLACEHOLDERS
            and DATE_RE.match(created)
            and DATE_RE.match(updated)
            and not cmp_dates(created, updated)
        ):
            violations.append(f"updated < created ({updated} < {created}): {path}")

print(f"Front matter files: {files_with_frontmatter}")
for key in ("draft/草稿", "in_progress/开发中", "done/已完成", "deprecated/已废弃"):
    items = sorted(by_status.get(key, []))
    if not items:
        continue
    print(f"- {key}: {len(items)}")
    for p in items:
        print(f"  - {p}")

if violations:
    print("\nVIOLATIONS:")
    for v in violations:
        print(f"- {v}")
    sys.exit(1)

print("\nOK: doc front matter status looks consistent.")
PY
