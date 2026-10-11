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
ARCH="$(uname -m)"
APP=dist/TubeClipper.app
STAGE=build/dmg
DMG="dist/TubeClipper-$VERSION-macOS-$ARCH.dmg"
[ -d "$APP" ] || fail "$APP is missing."

rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cat > "$STAGE/Read me first.txt" <<'NOTE'
TubeClipper
===========

Drag TubeClipper into Applications.

ffmpeg and ffprobe are included. No Homebrew installation is needed.

macOS will say it "could not verify" the app. That is because it is not
notarized by Apple, not because anything was found in it.

On macOS 15 and later, Control-clicking and choosing Open no longer works
for this. Instead:

  1. Click Done on the warning.
  2. Open System Settings, go to Privacy & Security, and scroll down to
     the Security section.
  3. Next to "TubeClipper.app was blocked", click Open Anyway, then
     authenticate and confirm.

Only needed once. After that it opens like any other app.
NOTE

# hdiutil intermittently fails with "Resource busy" on CI runners while
# something (XProtect, Spotlight) still has the staged files open. Retrying
# after a pause is the standard remedy and costs nothing when it succeeds.
made=0
for attempt in 1 2 3 4 5; do
    if hdiutil create -volname "TubeClipper $VERSION" -srcfolder "$STAGE" \
        -ov -format UDZO "$DMG" >/dev/null; then
        made=1
        break
    fi
    printf 'hdiutil attempt %s failed; retrying...\n' "$attempt"
    sleep $((attempt * 5))
done
[ "$made" = 1 ] || fail "hdiutil failed."
printf '\nDone: %s\n' "$DMG"
