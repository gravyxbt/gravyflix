#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -n "${UV:-}" ]] || command -v uv >/dev/null 2>&1; then
    "${UV:-uv}" pip install --python .venv/bin/python static-ffmpeg==3.0
else
    .venv/bin/python -m pip install static-ffmpeg==3.0
fi
exec .venv/bin/python -c 'from static_ffmpeg import run; print(run.get_or_fetch_platform_executables_else_raise())'
