#!/usr/bin/env bash
set -euo pipefail

LABEL="com.zorrobyte.macnotes-mcp"
PLIST_TARGET="${HOME}/Library/LaunchAgents/${LABEL}.plist"

launchctl bootout "gui/${UID}/${LABEL}" >/dev/null 2>&1 || true
rm -f "${PLIST_TARGET}"

echo "Uninstalled ${LABEL}"
