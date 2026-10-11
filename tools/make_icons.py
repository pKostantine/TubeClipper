"""Generate Windows, macOS, and UI assets from the supplied logo.png.

Same approach as TrackSync and Glasswood, whose icons sit correctly in the
Dock: macOS app icons are NOT full-bleed.  The artwork is an 824x824
rounded square centred on a 1024x1024 transparent canvas, and the system
draws the full canvas, so a full-bleed icon comes out larger and squarer
than every neighbour.  Nothing else is baked in: no shadow, nothing outside
the shape.  Windows has the opposite convention, so the .ico stays
full-bleed.
"""

import os
import shutil
import sys

from PIL import Image, ImageChops, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")

ICO_SIZES = [256, 128, 64, 48, 32, 24, 16]
ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]

MAC_CANVAS = 1024
MAC_INSET = 824 / 1024.0

#: Apple's corner is a continuous curve, not a circular arc.  A superellipse
#: |x|^n + |y|^n = 1 with n around 5 is very close.
SQUIRCLE_N = 5.0


def squircle_mask(size, n=SQUIRCLE_N, supersample=4):
    """Antialiased superellipse mask, solved one row at a time."""
    s = size * supersample
    a = s / 2.0
    mask = Image.new("L", (s, s), 0)
    draw = ImageDraw.Draw(mask)
    for row in range(s):
        t = abs((row + 0.5) - a) / a
        if t >= 1.0:
            continue
        x = a * (1.0 - t ** n) ** (1.0 / n)
        draw.line([(a - x, row), (a + x - 1, row)], fill=255)
    return mask.resize((size, size), Image.Resampling.LANCZOS)


def macos_icon(im, canvas=MAC_CANVAS, inset=MAC_INSET):
    """Fit the artwork to Apple's icon grid: inset, and squircle-cornered."""
    shape = int(round(canvas * inset))
    art = im.resize((shape, shape), Image.Resampling.LANCZOS).convert("RGBA")
    art.putalpha(ImageChops.multiply(art.getchannel("A"), squircle_mask(shape)))
    out = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    off = (canvas - shape) // 2
    out.paste(art, (off, off), art)
    return out


def check_tick():
    tick = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tick)
    points = [(13, 34), (27, 47), (51, 18)]
    draw.line(points, fill="white", width=8, joint="curve")
    for x, y in points:
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill="white")
    return tick


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

    shutil.copyfile(source, os.path.join(ASSETS, "logo.png"))
    square.resize((256, 256), Image.Resampling.LANCZOS).save(
        os.path.join(ASSETS, "logo_256.png"))
    square.save(os.path.join(ASSETS, "TubeClipper.ico"), format="ICO",
                sizes=[(s, s) for s in ICO_SIZES])

    mac = macos_icon(square)
    layers = [mac.resize((s, s), Image.Resampling.LANCZOS) for s in ICNS_SIZES]
    layers[-1].save(os.path.join(ASSETS, "TubeClipper.icns"),
                    format="ICNS", append_images=layers[:-1])
    mac.resize((512, 512), Image.Resampling.LANCZOS).save(
        os.path.join(ASSETS, "icon_macos_preview.png"))

    check_tick().save(os.path.join(ASSETS, "check.png"))

    for name in ("logo_256.png", "TubeClipper.ico", "TubeClipper.icns",
                 "icon_macos_preview.png", "check.png"):
        path = os.path.join(ASSETS, name)
        print(f"  {name:<24} {os.path.getsize(path):>10,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
