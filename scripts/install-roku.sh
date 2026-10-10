#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${ROKU_DEV_TARGET:?Set ROKU_DEV_TARGET to your Roku IP or hostname}"
: "${DEVPASSWORD:?Set DEVPASSWORD to your Roku developer password}"
./scripts/package-roku.sh
exec .venv/bin/python scripts/install_roku.py
