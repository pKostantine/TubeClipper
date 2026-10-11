"""Give the app's icon a filename that changes when the artwork does.

macOS caches rendered app icons, and the cache key includes the icon's
filename inside the bundle but not its contents.  Ship a new .icns under
the same name at the same bundle path and the Dock will happily keep
drawing the old picture, through rebuilds, reinstalls, `killall Dock`,
`lsregister -f`, and clearing the user-level icon cache.  That is not a
theory: it cost a long debugging session where every rebuilt file was
correct on disk and every screenshot showed the previous artwork.

Naming the icon after a hash of its own contents sidesteps the cache
instead of fighting it.  Same artwork, same name, no churn; new artwork,
new name, and the system has nothing cached to serve.

Run on a built .app:  python tools/stamp_icon.py dist/TubeClipper.app
"""

from __future__ import annotations

import hashlib
import os
import plistlib
import subprocess
import sys


def main(argv):
    if len(argv) != 2:
        raise SystemExit("usage: stamp_icon.py <path to .app>")

    app = argv[1]
    resources = os.path.join(app, "Contents", "Resources")
    plist_path = os.path.join(app, "Contents", "Info.plist")
    if not os.path.isdir(resources) or not os.path.exists(plist_path):
        raise SystemExit(f"stamp_icon: {app} does not look like an app bundle")

    with open(plist_path, "rb") as handle:
        plist = plistlib.load(handle)

    current = plist.get("CFBundleIconFile") or ""
    if not current.endswith(".icns"):
        current += ".icns"
    icon = os.path.join(resources, current)
    if not os.path.exists(icon):
        raise SystemExit(f"stamp_icon: {icon} is missing")

    with open(icon, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()[:10]

    # Strip any previous stamp before adding this one, so the name does not
    # grow a chain of hashes across rebuilds.
    stem = current[:-len(".icns")].split("-")[0]
    stamped = f"{stem}-{digest}.icns"

    if stamped != current:
        os.rename(icon, os.path.join(resources, stamped))
        for name in os.listdir(resources):
            if name.endswith(".icns") and name != stamped:
                os.remove(os.path.join(resources, name))
        plist["CFBundleIconFile"] = stamped
        with open(plist_path, "wb") as handle:
            plistlib.dump(plist, handle)

    # Touching Resources invalidates the signature, so re-sign ad hoc.
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app],
                   check=True, capture_output=True)
    print(f"stamp_icon: icon is now {stamped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
