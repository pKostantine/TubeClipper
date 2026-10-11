"""Fit a superellipse to Apple's corner, and characterise the baked shadow."""
import glob, os, subprocess, sys, tempfile
from PIL import Image

REF = "/System/Applications/Music.app"

def png_1024(app):
    icns = glob.glob(os.path.join(app, "Contents", "Resources", "*.icns"))[0]
    tmp = tempfile.mktemp(suffix=".png")
    subprocess.run(["sips", "-s", "format", "png", "-Z", "1024", icns,
                    "--out", tmp], capture_output=True)
    return Image.open(tmp).convert("RGBA")

im = png_1024(REF)
W, H = im.size
px = im.load()
A = lambda x, y: px[x, y][3]

# --- the solid shape -------------------------------------------------------
solid = lambda x, y: A(x, y) >= 250
xs = [x for x in range(W) if any(solid(x, y) for y in range(0, H, 2))]
ys = [y for y in range(H) if any(solid(x, y) for x in range(0, W, 2))]
x0, x1, y0, y1 = xs[0], xs[-1], ys[0], ys[-1]
side = x1 - x0 + 1
a = side / 2.0
cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
print(f"shape {side}x{y1 - y0 + 1} at ({x0},{y0}) centre ({cx},{cy})")

left_at = lambda y: next((x for x in range(x0, x1 + 1) if solid(x, y)), None)
samples = [(y, left_at(y)) for y in range(y0, y0 + 230, 3)]
samples = [(y, lx) for y, lx in samples if lx is not None]

def predict(n, y):
    t = abs((y - cy) / a)
    if t >= 1:
        return a
    return a - a * (1 - t ** n) ** (1.0 / n)

best = None
for i in range(300, 800):
    n = i / 100.0
    err = max(abs((a - (lx - cx + a)) - predict(n, y)) for y, lx in samples)
    #            measured inset  = x0-side distance
    inset = lambda lx: lx - x0
    err = max(abs(inset(lx) - predict(n, y)) for y, lx in samples)
    if best is None or err < best[1]:
        best = (n, err)
print(f"best superellipse n = {best[0]:.2f}, worst-case error {best[1]:.1f}px "
      f"at 1024 (= {best[1] / 1024 * 128:.2f}px at Dock size)")

# --- the shadow ------------------------------------------------------------
print("\nalpha just outside the shape (0 = none, 255 = opaque):")
for name, probe in (
        ("left  ", lambda d: A(int(x0 - d), int(cy))),
        ("right ", lambda d: A(int(x1 + d), int(cy))),
        ("top   ", lambda d: A(int(cx), int(y0 - d))),
        ("bottom", lambda d: A(int(cx), int(y1 + d)))):
    vals = []
    for d in (2, 5, 10, 20, 30, 40, 50, 60):
        try:
            vals.append(f"{d}:{probe(d)}")
        except IndexError:
            vals.append(f"{d}:-")
    print(f"  {name} " + "  ".join(vals))

# --- compare a plain circular rounded rect ---------------------------------
import math
def circ_inset(r, y):
    dy = abs(y - cy)
    flat = a - r
    if dy <= flat:
        return 0.0
    k = dy - flat
    if k >= r:
        return r
    return r - math.sqrt(max(0.0, r * r - k * k))

best_c = None
for i in range(150, 350):
    r = float(i)
    err = max(abs((lx - x0) - circ_inset(r, y)) for y, lx in samples)
    if best_c is None or err < best_c[1]:
        best_c = (r, err)
print(f"best circular radius = {best_c[0]:.0f}  ({best_c[0]/side:.4f} of side), "
      f"worst-case error {best_c[1]:.1f}px at 1024 "
      f"(= {best_c[1]/1024*128:.2f}px at Dock size)")
