"""Draw the default app icon: an "SHD" monogram on the app's blue.

Dev-time tool, run by hand — never by the build (M5 slice 68a). The build
consumes the committed ``sidelinehd.icns``; this script exists so the default
artwork is reproducible and the swap procedure is self-documenting: replace
``icon-1024.png`` (by editing this script or with real artwork), re-run
``make-icns.sh``, rebuild. See packaging/build-macos.md.

The artwork is deliberately modest — a rounded square in the web app's button
blue carrying the "SHD" monogram the menubar item has carried all along. It is
expected to be replaced whenever real artwork exists. Never player names,
photographs, or SidelineHD-owned artwork.

Usage (needs Pillow and the macOS system fonts):

    python packaging/icon/generate_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CANVAS = 1024
# Apple's macOS icon grid: an 824x824 tile centered in the 1024 canvas.
MARGIN = 100
CORNER_RADIUS = 185
FILL = "#0969da"  # the web app's primary button blue
TEXT = "SHD"
TEXT_WIDTH_FRACTION = 0.60  # of the tile width

# Helvetica Neue ships with macOS at this stable path; it is a .ttc holding
# several faces, so the Bold face is found by name rather than a magic index.
FONT_PATH = Path("/System/Library/Fonts/HelveticaNeue.ttc")

OUTPUT = Path(__file__).resolve().parent / "icon-1024.png"


def _bold_face(path: Path, size: int) -> ImageFont.FreeTypeFont:
    if not path.exists():
        sys.exit(
            f"Font not found: {path}\n"
            "This is a dev-time tool for regenerating the default artwork; "
            "it needs the macOS system Helvetica Neue and may simply require "
            "running on a Mac."
        )
    for index in range(32):
        try:
            font = ImageFont.truetype(str(path), size=size, index=index)
        except OSError:
            break
        family, style = font.getname()
        if family == "Helvetica Neue" and style == "Bold":
            return font
    sys.exit(f"No 'Helvetica Neue Bold' face found in {path}")


def _sized_to_width(target_width: float) -> ImageFont.FreeTypeFont:
    """The Bold face at whatever point size renders TEXT at target_width."""
    probe_size = 100
    probe = _bold_face(FONT_PATH, probe_size)
    left, _, right, _ = probe.getbbox(TEXT)
    size = round(probe_size * target_width / (right - left))
    return _bold_face(FONT_PATH, size)


def main() -> None:
    tile = CANVAS - 2 * MARGIN
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (MARGIN, MARGIN, CANVAS - MARGIN, CANVAS - MARGIN),
        radius=CORNER_RADIUS,
        fill=FILL,
    )

    font = _sized_to_width(tile * TEXT_WIDTH_FRACTION)
    # Optical centering: center the ink box of the all-caps monogram, not the
    # font's line box — the line box carries descender space no capital uses,
    # which would float the text visibly high.
    left, top, right, bottom = draw.textbbox((0, 0), TEXT, font=font)
    x = (CANVAS - (right - left)) / 2 - left
    y = (CANVAS - (bottom - top)) / 2 - top
    draw.text((x, y), TEXT, font=font, fill="white")

    image.save(OUTPUT)
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
