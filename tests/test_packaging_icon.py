"""Guard tests for the app icon build wiring (M5 slice 68a).

A Dock app whose bundle carries no ``.icns`` shows a generic blank tile —
which reads as *more* broken than no icon decision at all. The icon is
committed artwork consumed directly by the PyInstaller spec, so nothing in
the build would notice the spec regressing to ``icon=None`` or the assets
going missing until someone launched a bundle and looked. These tests are
that look, at the text level, the same way ``test_docs.py`` guards the
README's test instructions.
"""

from __future__ import annotations

from pathlib import Path

import cv2

PACKAGING = Path(__file__).resolve().parents[1] / "packaging"
SPEC = PACKAGING / "sidelinehd.spec"
ICON_DIR = PACKAGING / "icon"


def test_spec_references_the_committed_icns() -> None:
    text = SPEC.read_text(encoding="utf-8")
    assert '"icon", "sidelinehd.icns"' in text
    assert "icon=ICON_PATH" in text
    assert "icon=None" not in text


def test_spec_fails_fast_when_the_icon_is_missing() -> None:
    # The check must sit in the spec itself, before Analysis — a build must
    # never silently produce a blank-tile bundle.
    text = SPEC.read_text(encoding="utf-8")
    guard = text.index("if not os.path.isfile(ICON_PATH)")
    assert guard < text.index("a = Analysis(")


def test_icon_assets_exist_and_are_non_empty() -> None:
    icns = ICON_DIR / "sidelinehd.icns"
    source_png = ICON_DIR / "icon-1024.png"
    assert icns.is_file() and icns.stat().st_size > 0
    assert source_png.is_file() and source_png.stat().st_size > 0


def test_the_icns_is_actually_an_icns() -> None:
    # The Apple Icon Image format opens with the magic bytes "icns"; a
    # truncated or accidentally-text file would pass a bare size check.
    with (ICON_DIR / "sidelinehd.icns").open("rb") as fh:
        assert fh.read(4) == b"icns"


def test_source_png_is_1024_rgba_with_transparent_corners() -> None:
    # The item-71 defect this guards: the supplied master is 1254x1254 RGB
    # with *opaque white* corners, and macOS masks nothing on a .icns, so a
    # straight resize would paint four pale wedges into the Dock. The pipeline
    # input must be the derived 1024 RGBA tile whose corners are fully
    # transparent. Decoded with cv2 (a core dependency) rather than Pillow,
    # which lives in the `ocr` extra and would ImportError on CI's [dev,web].
    img = cv2.imread(str(ICON_DIR / "icon-1024.png"), cv2.IMREAD_UNCHANGED)
    assert img is not None, "icon-1024.png is unreadable"
    assert img.shape[:2] == (1024, 1024)
    assert img.shape[2] == 4, "icon-1024.png has no alpha channel"
    h, w = img.shape[:2]
    corners = [img[0, 0], img[0, w - 1], img[h - 1, 0], img[h - 1, w - 1]]
    assert all(int(px[3]) == 0 for px in corners), "a corner pixel is not transparent"
