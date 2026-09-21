"""Print, write, or verify TubeClipper's source version."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def version():
    import tubeclipper
    return tubeclipper.__version__


def main(argv):
    if not argv:
        print(version())
        return 0
    if argv[0] in ("-h", "--help"):
        print("version.py [--write PATH | --check PATH]")
        return 0
    if len(argv) < 2:
        print(f"version.py: {argv[0]} needs a path", file=sys.stderr)
        return 2
    command, path = argv[0], argv[1]
    if command == "--write":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="ascii", newline="") as handle:
            handle.write(version())
        print(version())
        return 0
    if command == "--check":
        try:
            with open(path, encoding="ascii") as handle:
                built = handle.read().strip()
        except OSError as exc:
            print(f"version.py: cannot read {path}: {exc}", file=sys.stderr)
            return 2
        if built != version():
            print(f"version.py: built={built!r} source={version()!r}",
                  file=sys.stderr)
            return 1
        print(built)
        return 0
    print(f"version.py: unknown option {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
