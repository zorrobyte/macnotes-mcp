#!/usr/bin/env bash
set -euo pipefail

LABEL="com.zorrobyte.macnotes-mcp"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLIST_TEMPLATE="${REPO_DIR}/deploy/launchd/${LABEL}.plist"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_TARGET="${LAUNCH_AGENTS_DIR}/${LABEL}.plist"
LOG_DIR="${HOME}/Library/Logs/macnotes-mcp"
PYTHON_BIN="${REPO_DIR}/.venv/bin/python"

mkdir -p "${LAUNCH_AGENTS_DIR}" "${LOG_DIR}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Python venv not found at ${PYTHON_BIN}; running uv sync..."
  (cd "${REPO_DIR}" && uv sync)
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Unable to find Python at ${PYTHON_BIN}" >&2
  exit 1
fi

sed \
  -e "s#__PYTHON_BIN__#${PYTHON_BIN}#g" \
  -e "s#__REPO_DIR__#${REPO_DIR}#g" \
  -e "s#__LOG_DIR__#${LOG_DIR}#g" \
  "${PLIST_TEMPLATE}" > "${PLIST_TARGET}"

launchctl bootout "gui/${UID}/${LABEL}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${UID}" "${PLIST_TARGET}"
launchctl enable "gui/${UID}/${LABEL}"
launchctl kickstart -k "gui/${UID}/${LABEL}"

echo "Installed and started ${LABEL}"
echo "Plist: ${PLIST_TARGET}"
echo "Logs: ${LOG_DIR}"
