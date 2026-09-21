#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1

[ -x .venv/bin/python ] || { echo "Run ./run_dev.sh once first."; exit 1; }
.venv/bin/python -m tests.test_engine || exit 1
QT_QPA_PLATFORM=offscreen .venv/bin/python -m tests.test_app
