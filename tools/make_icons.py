"""Generate Windows, macOS, and UI assets from the supplied logo.png."""

import os
import shutil
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")


def main():
    source = os.path.join(ROOT, "logo.png")
    if not os.path.exists(source):
        print(f"make_icons: {source} is missing", file=sys.stderr)
        return 1
    os.makedirs(ASSETS, exist_ok=True)

    image = Image.open(source).convert("RGBA")
    side = max(image.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.alpha_composite(image, ((side - image.width) // 2,
                                   (side - image.height) // 2))

    asset_logo = os.path.join(ASSETS, "logo.png")
    shutil.copyfile(source, asset_logo)
    square.resize((256, 256), Image.Resampling.LANCZOS).save(
        os.path.join(ASSETS, "logo_256.png"))
    square.save(os.path.join(ASSETS, "TubeClipper.ico"), format="ICO",
                sizes=[(s, s) for s in (256, 128, 64, 48, 32, 24, 16)])
    layers = [square.resize((s, s), Image.Resampling.LANCZOS)
              for s in (16, 32, 64, 128, 256, 512, 1024)]
    layers[-1].save(os.path.join(ASSETS, "TubeClipper.icns"),
                    format="ICNS", append_images=layers[:-1])

    tick = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tick)
    width = 8
    points = [(13, 34), (27, 47), (51, 18)]
    draw.line(points, fill="white", width=width, joint="curve")
    for x, y in points:
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill="white")
    tick.save(os.path.join(ASSETS, "check.png"))

    for name in ("logo.png", "logo_256.png", "TubeClipper.ico",
                 "TubeClipper.icns", "check.png"):
        path = os.path.join(ASSETS, name)
        print(f"  {name:<20} {os.path.getsize(path):>10,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
