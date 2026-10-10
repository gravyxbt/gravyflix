#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Darwin ]]; then
    echo "This helper is for Apple Silicon Macs. On Linux, use ./scripts/setup.sh." >&2
    exit 1
fi
python_bin="${PYTHON_BIN:-python3.13}"
if ! command -v "$python_bin" >/dev/null 2>&1; then
    echo "Install native Python and media tools first: brew install python@3.13 ffmpeg" >&2
    exit 1
fi
"$python_bin" - <<'PY'
import platform, sys
if platform.machine() != 'arm64':
    raise SystemExit('Use native ARM Python in a native Terminal session; Rosetta/Intel Python is not supported by this setup.')
if tuple(map(int, platform.mac_ver()[0].split('.')[:1])) < (14,):
    raise SystemExit('Apple Silicon support requires macOS 14 or newer for the pinned OCR runtime.')
if sys.version_info[:2] != (3, 13):
    raise SystemExit('This setup uses Python 3.13. Install it with: brew install python@3.13')
PY
if [[ -x .venv/bin/python ]]; then
    .venv/bin/python - <<'PYTHON'
import platform, sys
if platform.machine() != 'arm64' or sys.version_info[:2] != (3, 13):
    raise SystemExit('The existing .venv is not native ARM Python 3.13. Use a fresh checkout or rename .venv and rerun setup.')
PYTHON
fi
PYTHON_BIN="$python_bin" ./scripts/setup.sh
if [[ ! -f .env ]]; then
    (umask 077; cp .env.example .env)
fi
if ! .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, 'backend')
from app.media_tools import binary
missing = [name for name in ('ffmpeg', 'ffprobe') if not binary(name)]
if missing:
    raise SystemExit('Missing ' + ', '.join(missing) + '. Run: brew install ffmpeg, or ./scripts/setup-media-tools.sh')
PY
then exit 1; fi
printf '%s\n' 'Setup complete. Edit .env if needed, then run ./scripts/start.sh.' 'Open the printed LAN URL to manage your library and download the Roku package.'
