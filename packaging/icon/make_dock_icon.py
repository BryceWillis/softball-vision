"""Derive the pipeline's ``icon-1024.png`` from the supplied dock-icon master.

Dev-time tool, run by hand after the artwork changes — never by the build or
CI, which consume the committed ``sidelinehd.icns`` (M8 slice, item 71). It
is the real-artwork counterpart to ``generate_icon.py``, which draws the
retired "SHD" monogram placeholder: this script instead conditions a supplied
photographic master into the shape ``make-icns.sh`` expects.

    python packaging/icon/make_dock_icon.py
    sh packaging/icon/make-icns.sh        # then re-render the .icns
    # rebuild per packaging/build-macos.md

Why a transform is needed, not a plain resize (measured 2026-07-21):

* the master is **1254x1254 RGB with no alpha channel**, and the corners
  outside its squircle are opaque **white** (~(254,254,254)). macOS applies
  no mask to a ``.icns`` — the artwork is composited exactly as given — so
  those white corners would render as four pale wedges framing the icon in
  the Dock, Cmd-Tab, and Finder. They must become real transparency.
* the master's squircle is **full-bleed** (touches all four canvas edges),
  where Apple's icon grid seats the tile at 80.5% of the canvas (824 on
  1024). A straight resize would render visibly larger than its Dock
  neighbours, so the tile is inset onto a transparent 1024 canvas.

The master's relative corner radius (~0.174 of its canvas) is already close
to Apple's grid (0.181), so the *shape* carries over — only scale and alpha
change. We keep the master's own corner curve rather than re-rounding it.

Uses only ``cv2`` and ``numpy``, both core dependencies — no Pillow (which
lives in the ``ocr`` extra) and nothing new to install. The master must not
contain player names, photographs of people, or SidelineHD-owned artwork.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
MASTER = HERE / "softball-vision-dock-icon.png"
OUTPUT = HERE / "icon-1024.png"

CANVAS = 1024
# Apple's macOS icon grid: an 824x824 tile centered in the 1024 canvas.
MARGIN = 100
TILE = CANVAS - 2 * MARGIN  # 824

# The master's squircle corner radius, measured against its own 1254 canvas
# (the straight top/left edges begin ~217-221 px in from each corner). Kept as
# a fraction so it survives a differently-sized master.
CORNER_RADIUS_FRACTION = 218 / 1254

# A pixel is "background white" when its darkest channel is this bright. The
# navy squircle (min channel ~8) and the yellow ball (low blue channel) sit
# far below it; only the ~(254,254,254) corners and their anti-aliased ring do.
WHITE_MIN_CHANNEL = 200
# Grow the flood-filled background inward before recolouring, to swallow the
# anti-aliased white->navy ring so no pale halo survives the downscale.
BG_DILATE_PX = 6
SUPERSAMPLE = 3  # for a smooth (anti-aliased) alpha edge


def _rounded_rect_alpha(size: int, radius: int) -> np.ndarray:
    """A full-bleed rounded-rectangle alpha mask, anti-aliased by supersample.

    255 inside the squircle, 0 outside, with a smooth ramp on the boundary.
    """
    s = size * SUPERSAMPLE
    r = radius * SUPERSAMPLE
    ys = np.arange(s)[:, None]
    xs = np.arange(s)[None, :]
    # Distance past each corner-arc centre; 0 in the straight zones.
    dx = np.maximum(np.maximum(r - xs, xs - (s - 1 - r)), 0)
    dy = np.maximum(np.maximum(r - ys, ys - (s - 1 - r)), 0)
    inside = np.hypot(dx, dy) <= r
    big = np.where(inside, np.uint8(255), np.uint8(0))
    return cv2.resize(big, (size, size), interpolation=cv2.INTER_AREA)


def _navy(master_bgr: np.ndarray) -> np.ndarray:
    """The squircle's fill colour: the median of its dark navy pixels."""
    dark = master_bgr.max(axis=2) < 90
    return np.median(master_bgr[dark], axis=0).astype(np.uint8)


def _background_mask(master_bgr: np.ndarray) -> np.ndarray:
    """The white corner region, as the flood-fill reachable from each corner.

    Bounding it to what is connected to a canvas corner keeps interior white
    (the ball's specular highlights) opaque — only the true background goes.
    """
    h, w = master_bgr.shape[:2]
    whiteish = (master_bgr.min(axis=2) > WHITE_MIN_CHANNEL).astype(np.uint8)
    bg = np.zeros((h, w), np.uint8)
    for cy, cx in [(0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)]:
        if whiteish[cy, cx]:
            flooded = whiteish.copy()
            cv2.floodFill(flooded, np.zeros((h + 2, w + 2), np.uint8), (cx, cy), 2)
            bg |= flooded == 2
    kernel = np.ones((BG_DILATE_PX * 2 + 1, BG_DILATE_PX * 2 + 1), np.uint8)
    return cv2.dilate(bg.astype(np.uint8), kernel)


def main() -> None:
    master = cv2.imread(str(MASTER), cv2.IMREAD_UNCHANGED)
    if master is None:
        raise SystemExit(f"could not read master: {MASTER}")
    if master.ndim == 3 and master.shape[2] == 4:  # drop any alpha; master is RGB
        master = master[:, :, :3]
    h, w = master.shape[:2]

    # 1. Repaint the white background (and its anti-aliased ring) navy, so no
    #    light pixel can survive into the transparent corners as a pale wedge.
    navy = _navy(master)
    master[_background_mask(master).astype(bool)] = navy

    # 2. Scale the full-bleed squircle down to the 824 tile.
    radius = round(CORNER_RADIUS_FRACTION * w)
    tile_bgr = cv2.resize(master, (TILE, TILE), interpolation=cv2.INTER_AREA)
    alpha_full = _rounded_rect_alpha(w, radius)
    tile_alpha = cv2.resize(alpha_full, (TILE, TILE), interpolation=cv2.INTER_AREA)

    # 3. Inset the tile, centred, on a fully transparent 1024 canvas.
    canvas = np.zeros((CANVAS, CANVAS, 4), np.uint8)
    tile_bgra = np.dstack([tile_bgr, tile_alpha])
    canvas[MARGIN : MARGIN + TILE, MARGIN : MARGIN + TILE] = tile_bgra

    cv2.imwrite(str(OUTPUT), canvas)
    print(f"wrote {OUTPUT}  ({CANVAS}x{CANVAS} RGBA, tile {TILE}, radius {radius})")


if __name__ == "__main__":
    main()
