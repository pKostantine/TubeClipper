#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1

fail() { printf '\n [X] %s\n' "$*"; exit 1; }
[ "$(uname)" = "Darwin" ] || fail "A DMG must be built on macOS."
./build.sh || fail "The app build failed."

VPY=.venv-build/bin/python
VERSION="$("$VPY" tools/version.py)"
APP=dist/TubeClipper.app
STAGE=build/dmg
DMG="dist/TubeClipper-$VERSION.dmg"
[ -d "$APP" ] || fail "$APP is missing."

rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cat > "$STAGE/Read me first.txt" <<'NOTE'
TubeClipper
===========

Drag TubeClipper into Applications.

TubeClipper also needs ffmpeg. If it is not already installed, open Terminal
and run:

    brew install ffmpeg

If macOS blocks the app because it is not notarized, Control-click the app,
choose Open, then choose Open once more. This is only needed on first launch.
NOTE

hdiutil create -volname "TubeClipper $VERSION" -srcfolder "$STAGE" \
    -ov -format UDZO "$DMG" >/dev/null || fail "hdiutil failed."
printf '\nDone: %s\n' "$DMG"
