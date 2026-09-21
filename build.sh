#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1

fail() { printf '\n [X] %s\n' "$*"; exit 1; }
[ "$(uname)" = "Darwin" ] || fail "Run this build on macOS."

PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    command -v "$candidate" >/dev/null 2>&1 && { PY="$candidate"; break; }
done
[ -n "$PY" ] || fail "Python 3.10 or newer is required."

[ -x .venv-build/bin/python ] || "$PY" -m venv .venv-build || fail "Could not create the build environment."
VPY=.venv-build/bin/python
"$VPY" -m pip install --upgrade pip --quiet || fail "Could not update pip."
"$VPY" -m pip install -r requirements.txt --quiet || fail "Could not install dependencies."
"$VPY" tools/make_icons.py || fail "Could not generate icons."
"$VPY" -m tests.test_engine || fail "Engine tests failed."
QT_QPA_PLATFORM=offscreen "$VPY" -m tests.test_app || fail "UI tests failed."

VERSION="$("$VPY" tools/version.py)"
rm -rf build dist
TUBECLIPPER_VERSION="$VERSION" "$VPY" -m PyInstaller --clean --noconfirm \
    TubeClipper-mac.spec || fail "PyInstaller failed."
[ -d dist/TubeClipper.app ] || fail "The app bundle is missing."
printf '%s' "$VERSION" > dist/TubeClipper.app/Contents/MacOS/VERSION.txt
codesign --force --deep --sign - dist/TubeClipper.app 2>/dev/null || true

printf '\nDone: dist/TubeClipper.app\n'
printf 'Install ffmpeg with Homebrew before first use: brew install ffmpeg\n'
