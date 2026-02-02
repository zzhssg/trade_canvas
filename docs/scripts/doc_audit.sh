#!/usr/bin/env bash
set -euo pipefail

repo_root="${1:-.}"
cd "$repo_root"

if [[ ! -d "docs" ]]; then
  echo "ERROR: missing ./docs directory" >&2
  exit 2
fi

fail=0

while IFS= read -r -d '' file; do
	# Root README.md is allowed as a short entry index only.
	if [[ "$file" == "./README.md" ]]; then
	  continue
	fi
	# Root AGENTS.md is allowed (agent instructions, not project docs).
	if [[ "$file" == "./AGENTS.md" ]]; then
	  continue
	fi
  # Ignore vendored/node stuff if present.
  if [[ "$file" == "./frontend/node_modules/"* ]] || [[ "$file" == "./node_modules/"* ]]; then
    continue
  fi
  # Ignore project-local Codex config/skills (tooling, not project docs).
  if [[ "$file" == "./.codex/"* ]]; then
    continue
  fi
  # Ignore build/test artifacts.
  if [[ "$file" == "./output/"* ]]; then
    continue
  fi
  # Ignore tool caches.
  if [[ "$file" == "./.pytest_cache/"* ]] || [[ "$file" == "./.ruff_cache/"* ]] || [[ "$file" == "./.mypy_cache/"* ]]; then
    continue
  fi
  # Ignore local virtualenvs.
  if [[ "$file" == "./.env/"* ]] || [[ "$file" == "./.venv/"* ]] || [[ "$file" == "./venv/"* ]]; then
    continue
  fi
  echo "DOCS VIOLATION: Markdown file outside docs/: ${file#./}"
  fail=1
done < <(find . -type f -name "*.md" -not -path "./docs/*" -print0)

if [[ "$fail" -ne 0 ]]; then
  echo
  echo "Fix: move documentation into docs/ (core docs into docs/core/, plans into docs/plan/)."
  exit 1
fi

echo "OK: no Markdown files outside docs/ (except README.md)."

if [[ -x "docs/scripts/doc_frontmatter_audit.sh" ]]; then
  bash "docs/scripts/doc_frontmatter_audit.sh"
fi
