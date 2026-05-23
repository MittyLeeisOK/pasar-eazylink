#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_DIR="/opt/pasar-eazylink"

if [ -d "$REPO_DIR/pasar_eazylink" ]; then
  export PYTHONPATH="$REPO_DIR:${PYTHONPATH:-}"
elif [ -d "$INSTALL_DIR/pasar_eazylink" ]; then
  export PYTHONPATH="$INSTALL_DIR:${PYTHONPATH:-}"
fi

exec python3 -m pasar_eazylink.log_monitor "$@"
