#!/usr/bin/env bash
set -euo pipefail

NAME="${1:-macnotes-mcp}"
URL="${2:-http://127.0.0.1:8765/mcp}"

if ! command -v mcporter >/dev/null 2>&1; then
  echo "mcporter not found on PATH. Install it first, then rerun." >&2
  exit 1
fi

if mcporter config get "${NAME}" --json >/dev/null 2>&1; then
  mcporter config remove "${NAME}" >/dev/null
fi

mcporter config add "${NAME}" --url "${URL}" --transport http --scope home >/dev/null
echo "Configured mcporter server '${NAME}' -> ${URL}"

if command -v openclaw >/dev/null 2>&1; then
  openclaw config set skills.entries.apple-notes.enabled false >/dev/null || true
  echo "Disabled OpenClaw bundled skill: apple-notes"
fi
