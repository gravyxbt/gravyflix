#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python_bin="${PYTHON_BIN:-python3}"
if [[ -n "${UV:-}" ]] || command -v uv >/dev/null 2>&1; then
    uv_bin="${UV:-uv}"
    if [[ ! -x .venv/bin/python ]]; then "$uv_bin" venv --python "$python_bin" .venv; fi
    "$uv_bin" pip install --python .venv/bin/python -r backend/requirements-dev.txt
else
    if [[ ! -x .venv/bin/python ]]; then "$python_bin" -m venv .venv; fi
    if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
        echo "Missing pip/ensurepip. Use UV=/path/to/uv ./scripts/setup.sh, or install Ubuntu python3-venv." >&2
        exit 1
    fi
    .venv/bin/python -m pip install -r backend/requirements-dev.txt
fi
