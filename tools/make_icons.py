"""Generate Windows, macOS, and UI assets from the supplied logo.png.

The two platforms want opposite things from the same artwork, which is the
only interesting part of this file.

Windows draws app icons exactly as given, so the .ico is the full-bleed
square: artwork edge to edge, no mask.

macOS does not mask anything either, but every other icon on the Dock has
the rounded-square shape and the surrounding margin baked into its own
artwork.  Hand macOS a full-bleed square and it renders a full-bleed
square, which next to its neighbours reads as an icon that is too big and
the wrong shape.  So the .icns is composed to Apple's grid, measured off
the system icons on macOS 26:

    canvas        1024 x 1024
    artwork        814 x 814, centred, 105px margin on all four sides
    corner         continuous curvature, not a circular arc
    shadow         faint, slightly heavier below than above

The corner is the part worth explaining.  Apple's rounded rectangle has
continuous curvature: the bend starts earlier and finishes later than a
circular arc, with no visible seam where the curve meets the straight
edge.  The shape is a rectangle with straight sides and superelliptical
corners, radius 0.264 of the side and exponent 2.5, which tracks the real
outline to within a pixel or two at full size.

A superellipse applied to the whole square is the tempting shortcut and
it is wrong: it has no straight edges at all, so it comes out visibly
squarer through the middle of the bend and more tapered at the very top.
All of these numbers come from tools/_measure_icons.py, which traces the
outline of a system icon.
"""

import os
import shutil
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")

#: Apple's icon grid, measured on macOS 26.
CANVAS = 1024
ART_FRACTION = 814 / 1024
CORNER_RADIUS = 215 / 814  # of the artwork's side
CORNER_N = 2.5             # 2 would be a plain circular arc

#: The baked shadow, matched to the falloff on the system icons.
SHADOW_ALPHA = 80
SHADOW_BLUR = 0.018        # of the canvas
SHADOW_DROP = 0.005        # of the canvas, downwards

ICNS_SIZES = (16, 32, 64, 128, 256, 512, 1024)
ICO_SIZES = (256, 128, 64, 48, 32, 24, 16)


def squircle_mask(size, radius=CORNER_RADIUS, n=CORNER_N, supersample=4):
    """A continuous-curvature rounded square, as an alpha mask.

    Straight through the middle, superelliptical in the corners.  Solved a
    row at a time rather than per pixel: at four times oversampling an
    814px mask is sixteen million pixels, which is minutes in Python,
    while the same shape is three thousand horizontal spans.  The
    oversample is what gives the edge its antialiasing when it comes back
    down to size.
    """
    s = size * supersample
    a = s / 2.0
    r = radius * s
    flat = a - r                      # rows this close to centre are full width
    mask = Image.new("L", (s, s), 0)
    draw = ImageDraw.Draw(mask)
    for row in range(s):
        dy = abs((row + 0.5) - a)
        if dy >= a:
            continue
        if dy <= flat:
            x = a
        else:
            k = (dy - flat) / r
            x = flat + r * (1.0 - k ** n) ** (1.0 / n)
        draw.line([(a - x, row), (a + x - 1, row)], fill=255)
    return mask.resize((size, size), Image.Resampling.LANCZOS)


def macos_icon(square, canvas=CANVAS):
    """Compose the artwork onto Apple's grid: margin, shape, shadow."""
    art = int(round(canvas * ART_FRACTION))
    art -= art % 2                       # even, so the margin is equal
    offset = (canvas - art) // 2

    logo = square.resize((art, art), Image.Resampling.LANCZOS)
    mask = squircle_mask(art)
    logo.putalpha(ImageChops.multiply(logo.getchannel("A"), mask))

    shadow = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, SHADOW_ALPHA),
                 (offset, offset + int(round(canvas * SHADOW_DROP))), mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(canvas * SHADOW_BLUR))

    out = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    out.alpha_composite(shadow)
    out.alpha_composite(logo, (offset, offset))
    return out


def write_icns(master, path):
    """Build the .icns, preferring iconutil so every size is a real entry."""
    import subprocess
    import tempfile

    staging = tempfile.mkdtemp(prefix="tubeclipper-iconset-")
    iconset = os.path.join(staging, "icon.iconset")
    os.makedirs(iconset, exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        master.resize((size, size), Image.Resampling.LANCZOS).save(
            os.path.join(iconset, f"icon_{size}x{size}.png"))
        master.resize((size * 2, size * 2), Image.Resampling.LANCZOS).save(
            os.path.join(iconset, f"icon_{size}x{size}@2x.png"))
    try:
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", path],
                       check=True, capture_output=True)
        shutil.rmtree(staging, ignore_errors=True)
        return "iconutil"
    except (OSError, subprocess.CalledProcessError):
        shutil.rmtree(staging, ignore_errors=True)
        layers = [master.resize((s, s), Image.Resampling.LANCZOS)
                  for s in ICNS_SIZES]
        layers[-1].save(path, format="ICNS", append_images=layers[:-1])
        return "pillow"


def check_tick():
    """The checkbox tick, drawn rather than shipped.

    A Qt checkbox can be coloured from the stylesheet but cannot be given
    a check mark that way, so the sheet points at this.
    """
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

    # Windows: edge to edge, unmasked, because that is what Explorer and
    # the taskbar expect.
    square.save(os.path.join(ASSETS, "TubeClipper.ico"), format="ICO",
                sizes=[(s, s) for s in ICO_SIZES])

    # macOS: composed onto Apple's grid.
    master = macos_icon(square)
    master.save(os.path.join(ASSETS, "icon_1024.png"))
    how = write_icns(master, os.path.join(ASSETS, "TubeClipper.icns"))

    check_tick().save(os.path.join(ASSETS, "check.png"))

    print(f"  macOS icon composed to {int(CANVAS * ART_FRACTION)}px artwork "
          f"on a {CANVAS}px canvas, built with {how}")
    for name in ("logo.png", "logo_256.png", "icon_1024.png",
                 "TubeClipper.ico", "TubeClipper.icns", "check.png"):
        path = os.path.join(ASSETS, name)
        if os.path.exists(path):
            print(f"  {name:<20} {os.path.getsize(path):>10,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
