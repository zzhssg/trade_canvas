#!/usr/bin/env bash
set -euo pipefail

host="${PROJECT_CONSOLE_HOST:-127.0.0.1}"
port="${PROJECT_CONSOLE_PORT:-19080}"
repo_root="${PROJECT_CONSOLE_REPO_ROOT:-$(pwd)}"

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ -f ".env/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".env/bin/activate"
fi

export PROJECT_CONSOLE_REPO_ROOT="${repo_root}"
exec uvicorn project_console.backend.main:app --host "${host}" --port "${port}" --reload
