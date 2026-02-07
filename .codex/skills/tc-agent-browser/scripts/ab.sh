#!/usr/bin/env bash
set -euo pipefail

if command -v agent-browser >/dev/null 2>&1; then
  exec agent-browser "$@"
fi

exec npx -y agent-browser "$@"

