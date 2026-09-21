#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1

if [ ! -x .venv/bin/python ]; then
    PY=""
    for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
        command -v "$candidate" >/dev/null 2>&1 && { PY="$candidate"; break; }
    done
    [ -n "$PY" ] || { echo "Python 3.10 or newer is required."; exit 1; }
    "$PY" -m venv .venv || exit 1
    .venv/bin/python -m pip install --upgrade pip --quiet || exit 1
    .venv/bin/python -m pip install -r requirements.txt || exit 1
fi

.venv/bin/python tools/make_icons.py || exit 1
exec .venv/bin/python TubeClipper.py "$@"
