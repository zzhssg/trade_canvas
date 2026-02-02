#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/install_project_skills.sh [--uninstall] [--codex-home <path>]

Installs (symlinks) project-local skills from ./.codex/skills into $CODEX_HOME/skills
so Codex can discover them without changing auth/config.
EOF
}

uninstall=0
codex_home="${CODEX_HOME:-$HOME/.codex}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --uninstall) uninstall=1; shift ;;
    --codex-home) codex_home="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src_dir="${repo_root}/.codex/skills"
dst_dir="${codex_home%/}/skills"

if [[ ! -d "$src_dir" ]]; then
  echo "ERROR: missing project skills dir: $src_dir" >&2
  exit 2
fi

mkdir -p "$dst_dir"

installed_any=0

while IFS= read -r -d '' skill_path; do
  skill_dir="$(basename "$skill_path")"
  link_path="${dst_dir}/${skill_dir}"

  if [[ "$uninstall" -eq 1 ]]; then
    if [[ -L "$link_path" ]]; then
      target="$(readlink "$link_path" || true)"
      if [[ "$target" == "$skill_path" ]]; then
        rm "$link_path"
        echo "Removed: $link_path"
      fi
    fi
    continue
  fi

  if [[ -e "$link_path" && ! -L "$link_path" ]]; then
    echo "SKIP (exists, not symlink): $link_path" >&2
    continue
  fi

  if [[ -L "$link_path" ]]; then
    target="$(readlink "$link_path" || true)"
    if [[ "$target" == "$skill_path" ]]; then
      continue
    fi
    echo "SKIP (symlink exists, different target): $link_path -> $target" >&2
    continue
  fi

  ln -s "$skill_path" "$link_path"
  echo "Linked: $link_path -> $skill_path"
  installed_any=1
done < <(find "$src_dir" -mindepth 1 -maxdepth 1 -type d -print0)

if [[ "$uninstall" -eq 1 ]]; then
  echo "OK: uninstall complete."
  exit 0
fi

if [[ "$installed_any" -eq 0 ]]; then
  echo "OK: already installed (no changes)."
else
  echo "OK: install complete."
fi

