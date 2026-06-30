"""Deterministic OCR backends for overlay crops."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence


@dataclass(frozen=True)
class OCRBackendResult:
    """OCR text plus backend metadata."""

    text: str
    normalized_text: str
    confidence: Optional[float] = None
    backend: str = "none"


@dataclass(frozen=True)
class OCRFieldConfig:
    """Tesseract settings for one crop field."""

    psm: int = 7
    whitelist: Optional[str] = None
    scale: int = 4


OCRCallable = Callable[[object, str], OCRBackendResult]


FIELD_CONFIGS: Dict[str, OCRFieldConfig] = {
    "scorebug_full": OCRFieldConfig(psm=6, scale=3),
    "batter_card": OCRFieldConfig(psm=6, scale=4),
    "left_team": OCRFieldConfig(psm=7, scale=4),
    "right_team": OCRFieldConfig(psm=7, scale=4),
    "batter_card_name": OCRFieldConfig(psm=7, scale=5),
    "lineup_strip": OCRFieldConfig(psm=7, scale=5),
    "inning": OCRFieldConfig(psm=7, whitelist="0123456789TtBbOoPp^▲△- ", scale=6),
    "count": OCRFieldConfig(psm=7, whitelist="0123456789- ", scale=6),
    "left_score": OCRFieldConfig(psm=10, whitelist="0123456789", scale=6),
    "right_score": OCRFieldConfig(psm=10, whitelist="0123456789", scale=6),
    "batter_number": OCRFieldConfig(psm=10, whitelist="0123456789#", scale=6),
    "on_deck_number": OCRFieldConfig(psm=10, whitelist="0123456789#", scale=6),
    "batter_card_number": OCRFieldConfig(psm=10, whitelist="0123456789#", scale=6),
}


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
    if field_name in {
        "left_score",
        "right_score",
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


def create_ocr_backend(name: str) -> OCRCallable:
    """Create an OCR callable by backend name."""

    if name == "none":
        return no_ocr
    if name == "tesseract":
        ensure_tesseract_available()
        return tesseract_ocr_image
    raise ValueError(f"unknown OCR backend: {name}")


def ensure_tesseract_available() -> None:
    """Raise a clear error if the Tesseract CLI is unavailable."""

    if shutil.which("tesseract") is None:
        raise OCRBackendUnavailable(
            "Tesseract OCR was not found on PATH. "
            f"{_tesseract_install_hint()} Then rerun with `--ocr tesseract`."
        )


def preprocess_for_ocr(image: object, field_name: str):
    """Prepare a crop image for OCR using OpenCV."""

    import cv2

    if image is None:
        raise ValueError("image must be an OpenCV image array")
    if not hasattr(image, "shape") or len(image.shape) < 2:
        raise ValueError("image must be an OpenCV image array")

    config = FIELD_CONFIGS.get(field_name, OCRFieldConfig())
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

    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # The overlay text is bright on a dark translucent background. Tesseract tends
    # to perform better with dark text on a light background, so invert after thresholding.
    return cv2.bitwise_not(binary)


def tesseract_ocr_image(image: object, field_name: str) -> OCRBackendResult:
    """Run Tesseract OCR on an OpenCV image array."""

    import cv2

    ensure_tesseract_available()
    processed = preprocess_for_ocr(image, field_name)
    config = FIELD_CONFIGS.get(field_name, OCRFieldConfig())

    with tempfile.TemporaryDirectory() as directory:
        input_path = Path(directory) / "crop.png"
        ok = cv2.imwrite(str(input_path), processed)
        if not ok:
            raise OCRError(f"Could not write temporary OCR image: {input_path}")

        command = _tesseract_command(input_path, config)
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise OCRError(f"Tesseract failed for field '{field_name}': {detail}")

    text = completed.stdout
    return OCRBackendResult(
        text=text,
        normalized_text=normalize_ocr_text(text, field_name),
        backend="tesseract",
    )


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


def _tesseract_command(input_path: Path, config: OCRFieldConfig) -> Sequence[str]:
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
    return command


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
