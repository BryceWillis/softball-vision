"""Deterministic OCR backends for overlay crops."""

from __future__ import annotations

import csv
import io
import shutil
import subprocess
import tempfile
import re
import sys
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence

from sidelinehd_extractor.build_info import running_frozen
from sidelinehd_extractor.constants import (
    INNING_ARROW_DOWN,
    INNING_ARROW_UP,
    LINEUP_SOURCE_FULL_STRIP,
    LINEUP_SOURCE_HIGHLIGHT,
)


@dataclass(frozen=True)
class OCRBackendResult:
    """OCR text plus backend metadata.

    Confidence is normalized to a 0.0-1.0 scale when the backend exposes it.
    """

    text: str
    normalized_text: str
    confidence: Optional[float] = None
    backend: str = "none"
    source_detail: Optional[str] = None


@dataclass(frozen=True)
class OCRFieldConfig:
    """Tesseract settings for one crop field.

    ``preprocess`` names a strategy in ``PREPROCESS_STRATEGIES`` so binarization
    is tunable per field/template without touching ``preprocess_for_ocr``.
    """

    psm: int = 7
    whitelist: Optional[str] = None
    scale: int = 4
    optional: bool = False
    preprocess: str = "default"


OCRCallable = Callable[[object, str], OCRBackendResult]


FIELD_CONFIGS: Dict[str, OCRFieldConfig] = {
    "scorebug_full": OCRFieldConfig(psm=6, scale=3),
    "batter_card": OCRFieldConfig(psm=6, scale=4),
    "left_team": OCRFieldConfig(psm=7, scale=4),
    "right_team": OCRFieldConfig(psm=7, scale=4),
    "batter_card_name": OCRFieldConfig(psm=7, scale=5),
    "lineup_strip": OCRFieldConfig(psm=7, scale=5),
    "inning": OCRFieldConfig(
        psm=8, whitelist="0123456789Oo", scale=6, preprocess="scorebug_glyph_isolate"
    ),
    # count is three glyphs ("1-2"), not an isolated glyph: measurement showed
    # the pad strategy costs it confidence with no accuracy gain, so it keeps
    # the default binarization (it still gets multi-PSM voting).
    "count": OCRFieldConfig(psm=7, whitelist="0123456789- ", scale=6),
    "left_score": OCRFieldConfig(
        psm=8, whitelist="0123456789Oo", scale=6, preprocess="scorebug_glyph_isolate"
    ),
    "right_score": OCRFieldConfig(
        psm=8, whitelist="0123456789Oo", scale=6, preprocess="scorebug_glyph_isolate"
    ),
    "game_status": OCRFieldConfig(psm=7, scale=4, optional=True),
    "batter_number": OCRFieldConfig(
        psm=10, whitelist="0123456789#", scale=6, preprocess="numeric_glyph_pad"
    ),
    "on_deck_number": OCRFieldConfig(
        psm=10, whitelist="0123456789#", scale=6, preprocess="numeric_glyph_pad"
    ),
    "batter_card_number": OCRFieldConfig(
        psm=10, whitelist="0123456789#", scale=6, preprocess="numeric_glyph_pad"
    ),
}

NUMERIC_CONFIDENCE_FIELDS = {
    "left_score",
    "right_score",
    "count",
    "inning",
    "batter_number",
    "batter_card_number",
    "on_deck_number",
}

# The isolated-glyph scorebug fields do not confidence-vote: the isolate
# strategy hands OCR a single clean word, where PSM 8 is the correct
# segmentation, and a mis-segmented PSM 7/10 read can outscore it on
# self-reported confidence (measured: a real "0" losing to an "8"). They
# fall back through _SCOREBUG_FALLBACK_PSMS only when a PSM yields nothing.
SCOREBUG_ISOLATED_FIELDS = frozenset({"left_score", "right_score", "inning"})

# Item 43: the critical numeric fields are OCR'd under both PSM 7 and PSM 10
# and the higher-confidence normalized read wins (tie -> the whitelist-valid
# candidate). Same membership as the item-40 min-confidence set minus the
# isolated-glyph fields above: these are the fields where a single misread
# glyph flips an event. Text fields are never double-run.
MULTI_PSM_VOTE_FIELDS = frozenset(NUMERIC_CONFIDENCE_FIELDS) - SCOREBUG_ISOLATED_FIELDS

_VOTE_PSMS = (7, 10)
_SCOREBUG_FALLBACK_PSMS = (8, 7, 10)

# The scorebug digits are rendered by SidelineHD in one fixed blocky font, so
# the isolated glyphs are classified by template matching against reference
# digits harvested from real footage before Tesseract ever runs. Tesseract
# misreads this font systematically ("9" -> "3" under every PSM, measured
# 0/4 vs 11/11 for the template match on the 2026-07-08 game), so it is only
# the fallback when a glyph matches no reference confidently. Agreement is
# the fraction of pixels identical to the reference at canonical size; the
# margin is the gap to the runner-up digit (measured worst correct margin:
# 0.066 across 96 labeled crops from two games).
SCOREBUG_DIGIT_MATCH_SOURCE = "scorebug_digit_match"
_SCOREBUG_DIGIT_TEMPLATE_SIZE = (48, 64)  # (width, height)
_SCOREBUG_DIGIT_MIN_AGREEMENT = 0.90
_SCOREBUG_DIGIT_MIN_MARGIN = 0.03
_SCOREBUG_DIGIT_MAX_GLYPHS = 2
_SCOREBUG_DIGIT_MIN_HEIGHT_FRACTION = 0.5

MIN_SUPPORTED_TESSERACT_VERSION = (4, 1)


class OCRBackendUnavailable(RuntimeError):
    """Raised when the requested OCR backend is not installed."""


class OCRError(RuntimeError):
    """Raised when OCR execution fails."""


def normalize_ocr_text(text: str, field_name: Optional[str] = None) -> str:
    """Collapse OCR output into a single paste/debug-friendly line."""

    normalized = " ".join(text.replace("\x0c", " ").split())
    if field_name == "count":
        match = re.search(r"\b\d\s*-\s*\d\b", normalized)
        if match:
            return re.sub(r"\s+", "", match.group(0))
    if field_name in {"left_score", "right_score", "inning"}:
        # The bold scorebug zero classifies as the letter O under PSM 8; the
        # digit whitelist alone would silently drop the read.
        normalized = normalized.replace("o", "0").replace("O", "0")
    if field_name in {
        "left_score",
        "right_score",
        "lineup_strip",
        "batter_number",
        "on_deck_number",
        "batter_card_number",
    }:
        match = re.search(r"#?\d+", normalized)
        if match:
            return match.group(0)
    return normalized


def no_ocr(_image: object, _field_name: str) -> OCRBackendResult:
    """OCR backend that intentionally returns no text."""

    return OCRBackendResult(text="", normalized_text="", backend="none")


#: What a frozen app says when its embedded OCR engine fails to load. Never
#: brew/pip advice: a bundle user has no environment to install into, and the
#: only real fix is a fresh copy of the app.
OCR_BUNDLE_DAMAGED_MESSAGE = (
    "This app includes its own text reader (OCR), but this copy of the app "
    "failed to load it. Download a fresh copy of the app from the Releases "
    "page and replace this one."
)


def create_ocr_backend(name: str) -> OCRCallable:
    """Create an OCR callable by backend name."""

    if name == "none":
        return no_ocr
    if name == "tesseract":
        ensure_tesseract_available()
        _record_tesseract_version(tesseract_ocr_image)
        return tesseract_ocr_image
    if name == "tesserocr":
        backend = _optional_tesserocr_backend()
        if backend is not None:
            _record_tesseract_version(backend)
            return backend
        if running_frozen():
            # The bundle ships tesserocr; falling back to a host CLI here is
            # exactly the masking that hid a broken bundle behind a healthy
            # terminal PATH. Fail loudly with bundle-appropriate advice.
            raise OCRBackendUnavailable(OCR_BUNDLE_DAMAGED_MESSAGE)
        ensure_tesseract_available()
        _record_tesseract_version(tesseract_ocr_image)
        return tesseract_ocr_image
    raise ValueError(f"unknown OCR backend: {name}")


def ensure_tesseract_available() -> None:
    """Raise a clear error if the Tesseract CLI is unavailable."""

    if shutil.which("tesseract") is None:
        if running_frozen():
            raise OCRBackendUnavailable(OCR_BUNDLE_DAMAGED_MESSAGE)
        raise OCRBackendUnavailable(
            "Tesseract OCR was not found on PATH. "
            f"{_tesseract_install_hint()} Then rerun with `--ocr tesseract`."
        )


def tesseract_version() -> Optional[str]:
    """Return the installed Tesseract version string, if it can be parsed."""

    try:
        completed = subprocess.run(
            ["tesseract", "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    first_line = completed.stdout.splitlines()[0].strip() if completed.stdout.splitlines() else ""
    match = re.match(r"tesseract\s+([^\s]+)", first_line, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def _record_tesseract_version(backend: OCRCallable) -> None:
    if isinstance(backend, TesserocrOCRBackend):
        version = tesserocr_engine_version()
    else:
        version = tesseract_version()
    _warn_for_tesseract_version(version)
    try:
        setattr(backend, "tesseract_version", version)
    except (AttributeError, TypeError):
        pass


def _warn_for_tesseract_version(version: Optional[str]) -> None:
    if version is None:
        print(
            "Warning: could not determine Tesseract version; OCR results may vary by install.",
            file=sys.stderr,
        )
        return
    parsed = _parse_version_prefix(version)
    if parsed is None:
        print(
            f"Warning: could not interpret Tesseract version '{version}'; "
            "OCR results may vary by install.",
            file=sys.stderr,
        )
        return
    if parsed < MIN_SUPPORTED_TESSERACT_VERSION:
        minimum = ".".join(str(part) for part in MIN_SUPPORTED_TESSERACT_VERSION)
        print(
            f"Warning: Tesseract {version} is below the supported minimum {minimum}; "
            "OCR results may be unreliable.",
            file=sys.stderr,
        )


def _parse_version_prefix(version: str) -> Optional[tuple[int, int]]:
    match = re.match(r"(\d+)\.(\d+)", version)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


# White margin (in preprocessed pixels) added around isolated numeric glyphs;
# Tesseract drops or misreads lone digits whose strokes sit near the image edge.
_GLYPH_PAD_PX = 5

# Adaptive-threshold shape for text on uneven backgrounds (e.g. gradient team
# banners). Measured *worse* than Otsu on the current fixture set, so no field
# ships with it by default — it exists as a per-template tuning option.
_TEXT_ADAPTIVE_BLOCK_SIZE = 75
_TEXT_ADAPTIVE_C = 15


def _binarize_default(gray):
    """Blur + Otsu, inverted to dark-on-light (the pre-item-43 pipeline).

    The overlay text is bright on a dark translucent background. Tesseract tends
    to perform better with dark text on a light background, so invert after
    thresholding.
    """

    import cv2

    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return cv2.bitwise_not(binary)


def _binarize_numeric_glyph_pad(gray):
    """Default binarization plus a white border, tuned for isolated glyphs.

    Item 43 measurement (synthetic scorebug digit fixtures, real Tesseract):
    a small white margin recovered single digits the bare Otsu output lost
    (14/18 vs 11/18 correct) at equal confidence; the design's hard-threshold
    example regressed at every value tried, so this is the shipped numeric
    strategy instead.
    """

    import cv2

    inverted = _binarize_default(gray)
    return cv2.copyMakeBorder(
        inverted,
        _GLYPH_PAD_PX,
        _GLYPH_PAD_PX,
        _GLYPH_PAD_PX,
        _GLYPH_PAD_PX,
        cv2.BORDER_CONSTANT,
        value=255,
    )


def _binarize_text_adaptive(gray):
    """Blur + Gaussian adaptive threshold, inverted to dark-on-light."""

    import cv2

    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        _TEXT_ADAPTIVE_BLOCK_SIZE,
        _TEXT_ADAPTIVE_C,
    )
    return cv2.bitwise_not(binary)


# Scorebug glyph isolation (items 56/60): the score/inning digits are
# near-white, low-saturation glyphs drawn over backgrounds that defeat plain
# Otsu — gradient panels, dark base-diamond edges crossing the crop, and the
# saturated green inning arrow that fuses into reads ("164", "48"). Isolating
# bright low-saturation components keeps the digits and drops all of those.
# Thresholds measured on real 640x360 SidelineHD footage (both live-fire
# games): digit pixels sit at S<=~60, V>=~190; the arrow is high-saturation;
# diamonds and panels stay below the V floor.
_GLYPH_ISOLATE_MAX_SATURATION = 80
_GLYPH_ISOLATE_MIN_VALUE = 180
#: Components shorter than this fraction of the crop are specks, not digits.
_GLYPH_ISOLATE_MIN_HEIGHT_FRACTION = 0.35
_GLYPH_ISOLATE_MIN_AREA_PX = 40
#: A component this wide is a banner/edge artifact, never a digit.
_GLYPH_ISOLATE_MAX_WIDTH_FRACTION = 0.9
#: Scores/innings are at most two digits; more components means the overlay
#: is showing scrolling banner text through this region — refuse the read.
_GLYPH_ISOLATE_MAX_COMPONENTS = 2
#: White margin around the isolated glyphs, as a fraction of glyph height.
_GLYPH_ISOLATE_PAD_FRACTION = 0.5
#: Relaxed second-pass bounds: SidelineHD's FINAL view dims the losing
#: team's score to a desaturated blue-gray (measured V≈165, S≈110), below
#: the strict mask. The relaxed pass excludes the green-yellow overlay hue
#: band (status text / inning arrow, hue ≈25–95) so it cannot resurrect the
#: noise sources the strict pass exists to reject.
_GLYPH_ISOLATE_RELAXED_MAX_SATURATION = 160
_GLYPH_ISOLATE_RELAXED_MIN_VALUE = 140
_GLYPH_ISOLATE_EXCLUDED_HUE = (25, 95)

# Batter-card numbers are white "#NN" glyphs on a dark teal card. When the
# lower-third card is absent, the same crop can land on bright infield dirt or
# chalk and the old numeric pad can manufacture a plausible number from that
# texture. Gate color crops on a dark lower quartile before OCR, then use the
# isolated fallback only when the old path returns empty.
_BATTER_CARD_NUMBER_MAX_BACKGROUND_VALUE = 150
_BATTER_CARD_NUMBER_MAX_GLYPH_SATURATION = 140
_BATTER_CARD_NUMBER_MIN_GLYPH_VALUE = 145
_BATTER_CARD_NUMBER_MIN_HEIGHT_FRACTION = 0.28
_BATTER_CARD_NUMBER_MAX_WIDTH_FRACTION = 0.55
_BATTER_CARD_NUMBER_MAX_COMPONENTS = 3


_scorebug_digit_templates_cache: Optional[Dict[str, object]] = None


def _scorebug_digit_templates() -> Dict[str, object]:
    """Load (and cache) the bundled reference digit glyphs as boolean ink masks."""

    global _scorebug_digit_templates_cache
    if _scorebug_digit_templates_cache is None:
        import cv2

        from importlib import resources

        templates: Dict[str, object] = {}
        digits_dir = resources.files("sidelinehd_extractor") / "data" / "scorebug_digits"
        for digit in "0123456789":
            with resources.as_file(digits_dir / f"{digit}.png") as path:
                image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if image is None:
                raise OCRError(f"bundled scorebug digit template missing: {digit}.png")
            templates[digit] = image < 128
        _scorebug_digit_templates_cache = templates
    return _scorebug_digit_templates_cache


def match_scorebug_digits(processed, backend: str) -> Optional[OCRBackendResult]:
    """Classify isolated scorebug glyphs against the bundled reference digits.

    ``processed`` is the white-background glyph rendering produced by
    ``preprocess_for_ocr`` for a scorebug field. Returns ``None`` (caller
    falls back to Tesseract) when there are no digit-height glyphs, too many
    glyphs, or any glyph fails the agreement/margin thresholds. Confidence is
    the weakest glyph's agreement score.
    """

    import cv2

    if processed is None or not hasattr(processed, "shape") or len(processed.shape) != 2:
        return None
    height, width = processed.shape
    ink = (processed < 128).astype("uint8")
    if not ink.any():
        return None
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink)
    glyphs = []
    for index in range(1, count):
        x, y, w, h, _area = stats[index]
        if h < _SCOREBUG_DIGIT_MIN_HEIGHT_FRACTION * height:
            continue
        glyphs.append((x, processed[y : y + h, x : x + w]))
    if not glyphs or len(glyphs) > _SCOREBUG_DIGIT_MAX_GLYPHS:
        return None

    templates = _scorebug_digit_templates()
    digits = []
    weakest = 1.0
    for _x, glyph in sorted(glyphs, key=lambda item: item[0]):
        candidate = (
            cv2.resize(glyph, _SCOREBUG_DIGIT_TEMPLATE_SIZE, interpolation=cv2.INTER_AREA) < 128
        )
        scores = {digit: float((candidate == mask).mean()) for digit, mask in templates.items()}
        best = max(scores, key=scores.get)
        runner_up = max(score for digit, score in scores.items() if digit != best)
        if scores[best] < _SCOREBUG_DIGIT_MIN_AGREEMENT:
            return None
        if scores[best] - runner_up < _SCOREBUG_DIGIT_MIN_MARGIN:
            return None
        digits.append(best)
        weakest = min(weakest, scores[best])

    text = "".join(digits)
    return OCRBackendResult(
        text=text,
        normalized_text=text,
        confidence=weakest,
        backend=backend,
        source_detail=SCOREBUG_DIGIT_MATCH_SOURCE,
    )


def _isolate_scorebug_glyphs(image, scale: int, allow_relaxed_pass: bool = False):
    """Return isolated dark-on-light digit glyphs from a color scorebug crop.

    Returns ``None`` when no digit-like glyph is present (e.g. the overlay's
    scrolling-banner mode) — the caller treats that as an empty read rather
    than falling back to Otsu, which is exactly the path that produced the
    corrupted reads this strategy replaces.

    ``allow_relaxed_pass`` enables the dimmed-glyph retry and is only set for
    the score fields: the FINAL view dims the losing score below the strict
    mask, while the inning region is simply empty in every mode where the
    relaxed bounds could pick up stray banner letters instead.
    """

    import cv2

    if scale > 1:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue, saturation, value = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    strict = (saturation <= _GLYPH_ISOLATE_MAX_SATURATION) & (
        value >= _GLYPH_ISOLATE_MIN_VALUE
    )
    result, had_tall_candidates = _isolate_glyph_mask(strict)
    if result is not None:
        return result
    if not allow_relaxed_pass or had_tall_candidates:
        # Tall strict candidates mean the mask saw digit-height glyphs but
        # rejected them as banner/edge artifacts; a relaxed retry would only
        # re-admit them.
        return None
    relaxed = (
        (saturation <= _GLYPH_ISOLATE_RELAXED_MAX_SATURATION)
        & (value >= _GLYPH_ISOLATE_RELAXED_MIN_VALUE)
        & ~((hue >= _GLYPH_ISOLATE_EXCLUDED_HUE[0]) & (hue <= _GLYPH_ISOLATE_EXCLUDED_HUE[1]))
    )
    result, _ = _isolate_glyph_mask(relaxed)
    return result


def _has_dark_batter_card_number_background(image: object) -> bool:
    """Return whether a color crop looks like the active batter-card badge."""

    import cv2
    import numpy as np

    if image is None or not hasattr(image, "shape") or len(image.shape) != 3:
        return True
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return bool(
        np.percentile(hsv[..., 2], 25) <= _BATTER_CARD_NUMBER_MAX_BACKGROUND_VALUE
    )


def _isolate_batter_card_number_glyphs(image, scale: int):
    """Return isolated dark-on-light "#NN" glyphs from an active card crop."""

    import cv2
    import numpy as np

    if image is None or not hasattr(image, "shape") or len(image.shape) != 3:
        return None
    if scale > 1:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation, value = hsv[..., 1], hsv[..., 2]
    mask = (
        (saturation <= _BATTER_CARD_NUMBER_MAX_GLYPH_SATURATION)
        & (value >= _BATTER_CARD_NUMBER_MIN_GLYPH_VALUE)
    ).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))

    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    height, width = mask.shape
    kept = []
    for index in range(1, count):
        x, _y, w, h, area = stats[index]
        if h < _BATTER_CARD_NUMBER_MIN_HEIGHT_FRACTION * height:
            continue
        if area < max(12, int(0.002 * height * width)):
            continue
        if w > _BATTER_CARD_NUMBER_MAX_WIDTH_FRACTION * width:
            continue
        if width > 60 and (x <= 1 or x + w >= width - 1):
            continue
        kept.append(index)
    if not kept or len(kept) > _BATTER_CARD_NUMBER_MAX_COMPONENTS:
        return None

    x0 = min(stats[index][0] for index in kept)
    y0 = min(stats[index][1] for index in kept)
    x1 = max(stats[index][0] + stats[index][2] for index in kept)
    y1 = max(stats[index][1] + stats[index][3] for index in kept)
    glyphs = np.zeros_like(mask)
    for index in kept:
        glyphs[labels == index] = 255
    tight = cv2.GaussianBlur(glyphs[y0:y1, x0:x1], (3, 3), 0)
    pad = max(3, int(_GLYPH_ISOLATE_PAD_FRACTION * tight.shape[0]))
    return cv2.copyMakeBorder(
        cv2.bitwise_not(tight),
        pad,
        pad,
        pad,
        pad,
        cv2.BORDER_CONSTANT,
        value=255,
    )


def _isolate_glyph_mask(candidate_mask):
    """Filter a boolean glyph mask to digit-like components and render them.

    Returns ``(rendered_glyphs_or_None, had_tall_candidates)`` where the flag
    reports whether any digit-height component existed before the banner/edge
    rejection rules ran.
    """

    import cv2
    import numpy as np

    mask = candidate_mask.astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    height, width = mask.shape
    kept = []
    right_edge_pending = []
    had_tall_candidates = False
    for index in range(1, count):
        x, y, w, h, area = stats[index]
        if h < _GLYPH_ISOLATE_MIN_HEIGHT_FRACTION * height:
            continue
        had_tall_candidates = True
        if area < _GLYPH_ISOLATE_MIN_AREA_PX:
            continue
        if w > _GLYPH_ISOLATE_MAX_WIDTH_FRACTION * width:
            continue
        if x <= 1:
            # Clipped at the left crop edge: the inning arrow beside
            # left_score bleeding in. Never a score digit.
            continue
        if x + w >= width - 1:
            # Touching the right edge could be a real trailing digit (a
            # wide leading digit shifts a two-digit score's second glyph
            # flush against the edge — "20" read as "2") or banner text
            # bleeding in. Keep it only if another digit-height glyph sits
            # to its left; a lone right-edge fragment is the banner case.
            right_edge_pending.append(index)
            continue
        kept.append(index)
    for index in right_edge_pending:
        x = stats[index][0]
        if any(stats[other][0] < x for other in kept):
            kept.append(index)
    if not kept or len(kept) > _GLYPH_ISOLATE_MAX_COMPONENTS:
        return None, had_tall_candidates

    x0 = min(stats[index][0] for index in kept)
    y0 = min(stats[index][1] for index in kept)
    x1 = max(stats[index][0] + stats[index][2] for index in kept)
    y1 = max(stats[index][1] + stats[index][3] for index in kept)
    glyphs = np.zeros_like(mask)
    for index in kept:
        glyphs[labels == index] = 255
    tight = cv2.GaussianBlur(glyphs[y0:y1, x0:x1], (3, 3), 0)
    pad = int(_GLYPH_ISOLATE_PAD_FRACTION * tight.shape[0])
    rendered = cv2.copyMakeBorder(
        cv2.bitwise_not(tight),
        pad,
        pad,
        pad,
        pad,
        cv2.BORDER_CONSTANT,
        value=255,
    )
    return rendered, had_tall_candidates


PREPROCESS_STRATEGIES: Dict[str, Callable[[object], object]] = {
    "default": _binarize_default,
    "numeric_glyph_pad": _binarize_numeric_glyph_pad,
    "text_adaptive": _binarize_text_adaptive,
}

#: Strategies that need the original color crop (and do their own scaling),
#: unlike ``PREPROCESS_STRATEGIES`` entries which receive scaled grayscale.
COLOR_PREPROCESS_STRATEGIES = frozenset({"scorebug_glyph_isolate"})


def preprocess_for_ocr(image: object, field_name: str):
    """Prepare a crop image for OCR using OpenCV.

    Grayscale + upscale are shared; binarization dispatches on the field
    config's ``preprocess`` strategy.
    """

    import cv2

    if image is None:
        raise ValueError("image must be an OpenCV image array")
    if not hasattr(image, "shape") or len(image.shape) < 2:
        raise ValueError("image must be an OpenCV image array")

    config = FIELD_CONFIGS.get(field_name, OCRFieldConfig())
    if config.preprocess in COLOR_PREPROCESS_STRATEGIES:
        if len(image.shape) == 3:
            isolated = _isolate_scorebug_glyphs(
                image,
                config.scale,
                allow_relaxed_pass=field_name in ("left_score", "right_score"),
            )
            if isolated is not None:
                return isolated
            # No digit-like glyph found: emit a blank canvas so OCR returns
            # an empty read instead of noise from the raw background.
            import numpy as np

            return np.full((8, 8), 255, dtype=np.uint8)
        # Grayscale input (e.g. a saved preprocessed crop): color isolation
        # is impossible, so degrade to the numeric pad strategy.
        return _binarize_numeric_glyph_pad(
            cv2.resize(image, None, fx=config.scale, fy=config.scale, interpolation=cv2.INTER_CUBIC)
            if config.scale > 1
            else image.copy()
        )
    binarize = PREPROCESS_STRATEGIES.get(config.preprocess)
    if binarize is None:
        known = ", ".join(sorted(PREPROCESS_STRATEGIES))
        raise ValueError(
            f"unknown preprocess strategy {config.preprocess!r} for field "
            f"'{field_name}' (known: {known})"
        )

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    if config.scale > 1:
        gray = cv2.resize(
            gray,
            None,
            fx=config.scale,
            fy=config.scale,
            interpolation=cv2.INTER_CUBIC,
        )

    return binarize(gray)


def _is_whitelist_valid(text: str, whitelist: Optional[str]) -> bool:
    if not text:
        return False
    if not whitelist:
        return True
    return all(character in whitelist for character in text)


def _ocr_with_psm_voting(
    run_config: Callable[[OCRFieldConfig], OCRBackendResult],
    config: OCRFieldConfig,
    field_name: str,
) -> OCRBackendResult:
    """Run OCR once, or vote across PSMs for the critical numeric fields.

    ``run_config`` executes the backend on the same preprocessed image with a
    given config. Non-vote fields run exactly once with their configured PSM.
    Vote fields run under each of ``_VOTE_PSMS`` (configured PSM first, so a
    tie keeps pre-voting behavior); the higher-confidence normalized result
    wins, a missing confidence loses to any scored one, and an exact tie
    prefers the whitelist-valid candidate.
    """

    if field_name in SCOREBUG_ISOLATED_FIELDS:
        last: Optional[OCRBackendResult] = None
        for psm in dict.fromkeys((config.psm, *_SCOREBUG_FALLBACK_PSMS)):
            last = run_config(replace(config, psm=psm))
            if last.normalized_text:
                return last
        return last

    if field_name not in MULTI_PSM_VOTE_FIELDS:
        return run_config(config)

    psms = dict.fromkeys((config.psm, *_VOTE_PSMS))
    best: Optional[OCRBackendResult] = None
    for psm in psms:
        candidate = run_config(replace(config, psm=psm))
        if best is None or _beats_incumbent(candidate, best, config.whitelist):
            best = candidate
    return best


def _beats_incumbent(
    candidate: OCRBackendResult,
    incumbent: OCRBackendResult,
    whitelist: Optional[str],
) -> bool:
    candidate_confidence = -1.0 if candidate.confidence is None else candidate.confidence
    incumbent_confidence = -1.0 if incumbent.confidence is None else incumbent.confidence
    if candidate_confidence != incumbent_confidence:
        return candidate_confidence > incumbent_confidence
    return _is_whitelist_valid(candidate.normalized_text, whitelist) and not _is_whitelist_valid(
        incumbent.normalized_text, whitelist
    )


def _empty_ocr_result(backend: str) -> OCRBackendResult:
    return OCRBackendResult(text="", normalized_text="", confidence=None, backend=backend)


def _is_plausible_batter_card_number(text: str) -> bool:
    return bool(re.fullmatch(r"#?\d{1,2}", text))


def _ocr_batter_card_number(
    image: object,
    backend: str,
    ocr_preprocessed: Callable[[object, OCRFieldConfig, str], OCRBackendResult],
) -> OCRBackendResult:
    config = FIELD_CONFIGS["batter_card_number"]
    if not _has_dark_batter_card_number_background(image):
        return _empty_ocr_result(backend)

    processed = preprocess_for_ocr(image, "batter_card_number")
    result = _ocr_with_psm_voting(
        lambda vote_config: ocr_preprocessed(processed, vote_config, "batter_card_number"),
        config,
        "batter_card_number",
    )
    if result.normalized_text:
        return result

    isolated = _isolate_batter_card_number_glyphs(image, config.scale)
    if isolated is None:
        return result
    isolated_result = _ocr_with_psm_voting(
        lambda vote_config: ocr_preprocessed(isolated, vote_config, "batter_card_number"),
        config,
        "batter_card_number",
    )
    if _is_plausible_batter_card_number(isolated_result.normalized_text):
        return isolated_result
    return result


def tesseract_ocr_image(image: object, field_name: str) -> OCRBackendResult:
    """Run Tesseract OCR on an OpenCV image array."""

    ensure_tesseract_available()
    if field_name == "batter_card_number":
        return _ocr_batter_card_number(image, "tesseract", _tesseract_ocr_preprocessed_image)
    if field_name == "lineup_strip":
        highlighted = _extract_highlighted_lineup_crop(image)
        if highlighted is not None:
            processed_highlighted = preprocess_for_ocr(highlighted, "batter_number")
            highlighted_result = _tesseract_ocr_preprocessed_image(
                processed_highlighted,
                OCRFieldConfig(psm=10, whitelist="0123456789#", scale=6),
                field_name,
            )
            if highlighted_result.normalized_text:
                return replace(highlighted_result, source_detail=LINEUP_SOURCE_HIGHLIGHT)

    processed = preprocess_for_ocr(image, field_name)
    config = FIELD_CONFIGS.get(field_name, OCRFieldConfig())
    if field_name in SCOREBUG_ISOLATED_FIELDS:
        matched = match_scorebug_digits(processed, "tesseract")
        if matched is not None:
            if field_name == "inning":
                return _with_inning_arrow(matched, image)
            return matched
    result = _ocr_with_psm_voting(
        lambda vote_config: _tesseract_ocr_preprocessed_image(processed, vote_config, field_name),
        config,
        field_name,
    )
    if field_name == "lineup_strip":
        return replace(result, source_detail=LINEUP_SOURCE_FULL_STRIP)
    if field_name == "inning":
        return _with_inning_arrow(result, image)
    return result


class TesserocrOCRBackend:
    """Thread-local in-process Tesseract backend."""

    def __init__(self, tesserocr_module: object, image_module: object) -> None:
        self._tesserocr = tesserocr_module
        self._image = image_module
        self._local = threading.local()

    def __call__(self, image: object, field_name: str) -> OCRBackendResult:
        if field_name == "batter_card_number":
            return _ocr_batter_card_number(image, "tesserocr", self._ocr_preprocessed)
        if field_name == "lineup_strip":
            highlighted = _extract_highlighted_lineup_crop(image)
            if highlighted is not None:
                processed_highlighted = preprocess_for_ocr(highlighted, "batter_number")
                highlighted_result = self._ocr_preprocessed(
                    processed_highlighted,
                    OCRFieldConfig(psm=10, whitelist="0123456789#", scale=6),
                    field_name,
                )
                if highlighted_result.normalized_text:
                    return replace(highlighted_result, source_detail=LINEUP_SOURCE_HIGHLIGHT)

        processed = preprocess_for_ocr(image, field_name)
        config = FIELD_CONFIGS.get(field_name, OCRFieldConfig())
        if field_name in SCOREBUG_ISOLATED_FIELDS:
            matched = match_scorebug_digits(processed, "tesserocr")
            if matched is not None:
                if field_name == "inning":
                    return _with_inning_arrow(matched, image)
                return matched
        result = _ocr_with_psm_voting(
            lambda vote_config: self._ocr_preprocessed(processed, vote_config, field_name),
            config,
            field_name,
        )
        if field_name == "lineup_strip":
            return replace(result, source_detail=LINEUP_SOURCE_FULL_STRIP)
        if field_name == "inning":
            return _with_inning_arrow(result, image)
        return result

    def _ocr_preprocessed(
        self,
        processed_image: object,
        config: OCRFieldConfig,
        field_name: str,
    ) -> OCRBackendResult:
        api = self._api()
        api.SetPageSegMode(config.psm)
        api.SetVariable("tessedit_char_whitelist", config.whitelist or "")
        api.SetImage(self._image_from_array(processed_image))
        text = api.GetUTF8Text() or ""
        confidence = _aggregate_confidence(
            field_name,
            text.split(),
            _tesserocr_word_confidences(api),
        )
        api.Clear()
        return OCRBackendResult(
            text=text,
            normalized_text=normalize_ocr_text(text, field_name),
            confidence=confidence,
            backend="tesserocr",
        )

    def _api(self):
        api = getattr(self._local, "api", None)
        if api is None:
            kwargs = {"lang": "eng"}
            oem = getattr(getattr(self._tesserocr, "OEM", object()), "LSTM_ONLY", None)
            if oem is not None:
                kwargs["oem"] = oem
            api = self._tesserocr.PyTessBaseAPI(**kwargs)
            self._local.api = api
        return api

    def _image_from_array(self, image: object):
        return self._image.fromarray(image)


def _optional_tesserocr_backend() -> Optional[OCRCallable]:
    try:
        import tesserocr
        from PIL import Image
    except ImportError:
        return None
    return TesserocrOCRBackend(tesserocr, Image)


def tesserocr_backend_available() -> bool:
    """True when the in-process tesserocr backend can be constructed."""

    return _optional_tesserocr_backend() is not None


def warm_tesserocr_import() -> None:
    """Import tesserocr from the main thread, tolerating every failure.

    The tesserocr wheel initializes cysignals on first import, and cysignals
    installs signal handlers — which Python allows only in the main thread.
    Web requests and job runners execute on worker threads, so whichever of
    them triggered the first import would die with ``ValueError: signal only
    works in main thread``. Calling this at startup makes every later import
    a cached ``sys.modules`` lookup, safe from any thread. Failures are the
    callers' problem to diagnose (preflight, ``create_ocr_backend``); this
    warm-up must never break startup.
    """

    try:
        import tesserocr  # noqa: F401
    except Exception:
        pass


def tesserocr_engine_version() -> Optional[str]:
    """Tesseract engine version reported by the tesserocr module, or None.

    This is the version of the *embedded* libtesseract — inside a bundle the
    only engine that runs — where ``tesseract_version()`` asks whatever CLI
    happens to be on PATH, which may be a different install entirely.
    """

    try:
        import tesserocr
    except ImportError:
        return None
    try:
        raw = str(tesserocr.tesseract_version())
    except Exception:
        return None
    first_line = raw.splitlines()[0].strip() if raw.strip() else ""
    match = re.match(r"(?:tesseract\s+)?(\S+)", first_line, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _tesseract_ocr_preprocessed_image(
    processed_image: object,
    config: OCRFieldConfig,
    field_name: str,
) -> OCRBackendResult:
    """Run Tesseract on an already prepared image."""

    import cv2

    with tempfile.TemporaryDirectory() as directory:
        input_path = Path(directory) / "crop.png"
        ok = cv2.imwrite(str(input_path), processed_image)
        if not ok:
            raise OCRError(f"Could not write temporary OCR image: {input_path}")

        command = _tesseract_command(input_path, config)
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise OCRError(f"Tesseract failed for field '{field_name}': {detail}")

    text, confidence = _parse_tesseract_tsv_output(completed.stdout, field_name)
    return OCRBackendResult(
        text=text,
        normalized_text=normalize_ocr_text(text, field_name),
        confidence=confidence,
        backend="tesseract",
    )


def _parse_tesseract_tsv_output(output: str, field_name: str) -> tuple[str, Optional[float]]:
    try:
        rows = list(csv.DictReader(io.StringIO(output), delimiter="\t"))
    except csv.Error:
        return output, None
    if not rows:
        return output, None
    fieldnames = set(rows[0].keys())
    if "text" not in fieldnames or "conf" not in fieldnames:
        return output, None

    tokens = []
    confidences = []
    for row in rows:
        token = (row.get("text") or "").strip()
        if not token:
            continue
        tokens.append(token)
        confidences.append(_parse_tesseract_confidence(row.get("conf")))
    if not tokens:
        return "", None
    text = " ".join(tokens)
    return text, _aggregate_confidence(field_name, tokens, confidences)


def _parse_tesseract_confidence(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        confidence = float(value)
    except ValueError:
        return None
    if confidence < 0:
        return None
    return max(0.0, min(confidence / 100.0, 1.0))


def _aggregate_confidence(
    field_name: str,
    tokens: Sequence[str],
    confidences: Sequence[Optional[float]],
) -> Optional[float]:
    paired = [
        (token, confidence)
        for token, confidence in zip(tokens, confidences)
        if token and confidence is not None
    ]
    if not paired:
        return None
    if field_name in NUMERIC_CONFIDENCE_FIELDS:
        return min(confidence for _token, confidence in paired)

    weighted = [
        (len(token), confidence)
        for token, confidence in paired
        if confidence > 0 and len(token) > 0
    ]
    total_weight = sum(weight for weight, _confidence in weighted)
    if total_weight <= 0:
        return None
    return sum(weight * confidence for weight, confidence in weighted) / total_weight


def _tesserocr_word_confidences(api: object) -> Sequence[Optional[float]]:
    try:
        confidences = api.AllWordConfidences()
    except AttributeError:
        return []
    return [
        None if confidence < 0 else max(0.0, min(float(confidence) / 100.0, 1.0))
        for confidence in confidences
    ]


def _extract_highlighted_lineup_crop(image: object):
    """Return a tight crop around SidelineHD's highlighted lineup number."""

    import cv2
    import numpy as np

    if image is None or not hasattr(image, "shape") or len(image.shape) != 3:
        return None

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lower = np.array([25, 60, 120], dtype=np.uint8)
    upper = np.array([95, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    height, width = image.shape[:2]
    candidates = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < 12 or h < max(4, height * 0.25):
            continue
        candidates.append((area, x, y, w, h))
    if not candidates:
        return None

    _, x, y, w, h = max(candidates)
    pad_x = 1
    pad_y = 1
    left = max(0, x - pad_x)
    right = min(width, x + w + pad_x)
    top = max(0, y - pad_y)
    bottom = min(height, y + h + pad_y)
    return image[top:bottom, left:right]


#: Green-ness weighting for the inning arrow. The arrow renders about ten
#: pixels tall at the template's native 640x360, so most of the triangle is
#: anti-aliased edge: a hard ``inRange`` mask keeps only the saturated core and
#: throws the shape away with it. Measured against hand-labelled frames, the
#: binary mask classified 62% of reads correctly (a coin flip) while these
#: continuous weights score 99.9%. Hue is scored by distance from the arrow's
#: centre hue rather than by membership in a band, so a compression-dulled edge
#: pixel still contributes in proportion to how green it is.
_ARROW_HUE_CENTER = 45.0
_ARROW_HUE_SIGMA = 18.0
_ARROW_SATURATION_REFERENCE = 120.0
_ARROW_VALUE_REFERENCE = 150.0
#: Total green mass below which the crop is taken to hold no arrow at all
#: (pregame overlay, FINAL banner). Guards against reading a direction out of
#: stray specks.
_ARROW_MIN_TOTAL_MASS = 6.0
#: The arrow sits left of the inning digit. Columns carrying at least this
#: share of the peak column mass start the arrow; the run is then extended
#: rightwards so the digit's own anti-aliasing cannot join it.
_ARROW_COLUMN_MASS_FRACTION = 0.35
#: Rows below this share of the peak row mass are anti-aliased fringe, not
#: triangle. Trimming them matters: on real footage the up-arrow carries a
#: two-pixel shadow stub under its base that, left in, drags the bounding box
#: down far enough to invert the direction.
_ARROW_ROW_MASS_FRACTION = 0.30
_ARROW_MIN_ROWS = 3
#: The arrow is a roughly equilateral triangle, so what survives isolation must
#: be about as wide as it is tall and must occupy only its own corner of the
#: crop. Both guards reject green that is not an arrow at all: the FINAL
#: banner's green lettering fills the full crop width, the pregame overlay's
#: green text is two-and-a-half times wider than tall, and a compression-thinned
#: read can collapse to a single column. Measured on real frames, a genuine
#: arrow is 6x6 in a 28-wide crop — aspect 1.0, spanning 21% of the width.
_ARROW_MIN_ASPECT = 0.5
_ARROW_MAX_ASPECT = 2.0
_ARROW_MAX_WIDTH_FRACTION = 0.5


def _arrow_greenness(image: object) -> object:
    """Per-pixel green-ness of the inning crop, 0.0-1.0, without thresholding."""

    import cv2
    import numpy as np

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
    hue, saturation, value = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    hue_score = np.exp(-((hue - _ARROW_HUE_CENTER) ** 2) / (2 * _ARROW_HUE_SIGMA**2))
    return (
        hue_score
        * np.clip(saturation / _ARROW_SATURATION_REFERENCE, 0.0, 1.0)
        * np.clip(value / _ARROW_VALUE_REFERENCE, 0.0, 1.0)
    )


def _arrow_row_mass(greenness: object) -> object:
    """Return the arrow triangle's per-row green mass, or ``None``.

    Isolates the arrow from the inning digit by column mass, trims anti-aliased
    fringe rows so the remaining rows are triangle only, then rejects anything
    whose proportions are not an arrow's.
    """

    import numpy as np

    column_mass = greenness.sum(axis=0)
    if not column_mass.size or column_mass.max() <= 0:
        return None
    strong = column_mass >= _ARROW_COLUMN_MASS_FRACTION * column_mass.max()
    columns = np.flatnonzero(strong)
    if not columns.size:
        return None
    first = int(columns[0])
    last = first
    while last + 1 < strong.size and strong[last + 1]:
        last += 1
    width = last - first + 1
    if width > _ARROW_MAX_WIDTH_FRACTION * column_mass.size:
        return None
    arrow = greenness[:, first : last + 1]
    row_mass = arrow.sum(axis=1)
    if row_mass.max() <= 0:
        return None
    rows = np.flatnonzero(row_mass >= _ARROW_ROW_MASS_FRACTION * row_mass.max())
    if not rows.size:
        return None
    height = int(rows[-1]) - int(rows[0]) + 1
    if not _ARROW_MIN_ASPECT <= width / height <= _ARROW_MAX_ASPECT:
        return None
    return row_mass[int(rows[0]) : int(rows[-1]) + 1]


def detect_inning_arrow(image: object) -> Optional[str]:
    """Detect the inning arrow direction from the color inning crop.

    Returns ``INNING_ARROW_UP``, ``INNING_ARROW_DOWN``, or ``None``. A triangle
    carries most of its area on the base side, so the half of the arrow with
    the greater green mass is the base: base low means an up arrow, base high a
    down arrow. This pixel test replaces trusting the arrow's OCR rendering,
    which fuses into the inning digit as a bogus leading "4" (up) or "7" (down).

    What actually fixed this, measured by ablation against 693 hand-labelled
    frames (the previous version scored 62% — a coin flip that flipped the half
    on 21% of samples and silently discarded half of one game's at-bats):

    * **Trimming the fringe rows is the whole ballgame** — 692/693 with it,
      407/693 without. The up arrow carries a two-pixel shadow stub beneath its
      base; left in, it extends the bounding box downward far enough to put the
      real base in the *upper* half and invert every up arrow.
    * **The continuous green-ness mask** is a smaller, real gain: it turns nine
      or ten no-reads per game into confident ones, because a hard threshold on
      a ten-pixel anti-aliased glyph keeps only the saturated core.
    * **Half-mass versus third-width is not load-bearing.** Both score
      identically once the fringe is trimmed. The halves form is kept only
      because it reads the whole triangle rather than two rows; do not expect a
      test to distinguish them.
    """

    if image is None or not hasattr(image, "shape") or len(image.shape) != 3:
        return None
    greenness = _arrow_greenness(image)
    if greenness.sum() < _ARROW_MIN_TOTAL_MASS:
        return None
    row_mass = _arrow_row_mass(greenness)
    if row_mass is None or len(row_mass) < _ARROW_MIN_ROWS:
        return None
    half = len(row_mass) // 2
    top_mass = float(row_mass[:half].mean())
    bottom_mass = float(row_mass[-half:].mean())
    if top_mass == bottom_mass:
        return None
    return INNING_ARROW_UP if bottom_mass > top_mass else INNING_ARROW_DOWN


def _with_inning_arrow(result: OCRBackendResult, image: object) -> OCRBackendResult:
    """Attach the pixel-detected arrow direction to an inning OCR result."""

    direction = detect_inning_arrow(image)
    if direction is None:
        return result
    return replace(result, source_detail=direction)


def ocr_image_file(path: Path, field_name: str, backend: str = "tesseract") -> OCRBackendResult:
    """OCR a crop image from disk."""

    import cv2

    source = path.expanduser()
    image = cv2.imread(str(source))
    if image is None:
        raise FileNotFoundError(source)
    return create_ocr_backend(backend)(image, field_name)


def write_preprocessed_image(input_path: Path, output_path: Path, field_name: str) -> Path:
    """Write the OpenCV-preprocessed image used by OCR."""

    import cv2

    source = input_path.expanduser()
    image = cv2.imread(str(source))
    if image is None:
        raise FileNotFoundError(source)
    processed = preprocess_for_ocr(image, field_name)
    destination = output_path.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(destination), processed)
    if not ok:
        raise ValueError(f"Could not write preprocessed OCR image: {destination}")
    return destination


def _tesseract_command(
    input_path: Path,
    config: OCRFieldConfig,
    output_format: Optional[str] = "tsv",
) -> Sequence[str]:
    command = [
        "tesseract",
        str(input_path),
        "stdout",
        "--oem",
        "1",
        "--psm",
        str(config.psm),
        "-l",
        "eng",
    ]
    if config.whitelist:
        command.extend(["-c", f"tessedit_char_whitelist={config.whitelist}"])
    if output_format:
        command.append(output_format)
    return command


def tesseract_install_hint() -> str:
    """Return the OS-specific one-line install instruction for Tesseract."""

    return _tesseract_install_hint()


def _tesseract_install_hint() -> str:
    if sys.platform == "darwin":
        return "Install it with `brew install tesseract`."
    if sys.platform.startswith("linux"):
        return "Install it with `sudo apt install tesseract-ocr` or your distribution's equivalent."
    if sys.platform.startswith("win"):
        return (
            "Install it from the UB Mannheim Windows installer: "
            "https://github.com/UB-Mannheim/tesseract/wiki."
        )
    return "Install Tesseract OCR for your operating system and make sure `tesseract` is on PATH."
