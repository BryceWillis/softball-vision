"""Dependency preflight: report the health of external tools before a run.

Item 54a. Checks each dependency the pipeline needs — yt-dlp, ffmpeg, and a
Tesseract OCR engine — and reports a uniform status the CLI ``start``
command and the web index page can render as guidance. Never raises: a
missing dependency becomes ``ok: False`` plus an actionable install hint,
not a traceback.

Every helper ships inside the package (yt-dlp and tesserocr as Python
modules, ffmpeg via imageio-ffmpeg), so the checks probe the *modules* first
and fall back to host binaries only for source installs that lack an extra.
A frozen bundle never gets pip/brew advice — its only real fix is a fresh
download of the app.
"""

from __future__ import annotations

import shutil
from typing import List, Optional

from sidelinehd_extractor.build_info import running_frozen
from sidelinehd_extractor.ocr import (
    OCR_BUNDLE_DAMAGED_MESSAGE,
    tesseract_install_hint,
    tesseract_version,
    tesserocr_backend_available,
    tesserocr_engine_version,
)
from sidelinehd_extractor.youtube import (
    installed_ytdlp_version,
    load_ytdlp_module,
    resolve_ffmpeg_location,
)

FFMPEG_REINSTALL_MESSAGE = (
    "ffmpeg ships with this package via the imageio-ffmpeg dependency. "
    "Reinstall with `pip install -e .` so the bundled build is available."
)
FFMPEG_BUNDLE_DAMAGED_MESSAGE = (
    "This app includes its own copy of ffmpeg, but this copy of the app "
    "failed to load it. Download a fresh copy of the app from the Releases "
    "page and replace this one."
)


def preflight_dependencies() -> List[dict]:
    """Return the status of each external dependency as a list of dicts.

    Each entry has ``name``, ``ok`` (bool), ``detail`` (what was found), and
    ``install_hint`` (actionable fix, ``None`` when the dependency is healthy).
    """

    return [
        _check_ytdlp(),
        _check_ffmpeg(),
        _check_tesseract(),
    ]


def missing_dependencies(statuses: Optional[List[dict]] = None) -> List[dict]:
    """Return only the unhealthy entries from a preflight report."""

    if statuses is None:
        statuses = preflight_dependencies()
    return [status for status in statuses if not status["ok"]]


def _status(name: str, ok: bool, detail: str, install_hint: Optional[str] = None) -> dict:
    return {"name": name, "ok": ok, "detail": detail, "install_hint": install_hint}


def _check_ytdlp() -> dict:
    try:
        module = load_ytdlp_module()
    except FileNotFoundError as exc:
        return _status(
            "yt-dlp",
            ok=False,
            detail="the yt_dlp module is not importable",
            install_hint=str(exc),
        )
    version = installed_ytdlp_version(module)
    detail = f"yt_dlp module {version}" if version else "yt_dlp module (version unknown)"
    return _status("yt-dlp", ok=True, detail=detail)


def _check_ffmpeg() -> dict:
    location = resolve_ffmpeg_location()
    if location is None:
        return _status(
            "ffmpeg",
            ok=False,
            detail="no system ffmpeg and the bundled build is unavailable",
            install_hint=(
                FFMPEG_BUNDLE_DAMAGED_MESSAGE
                if running_frozen()
                else FFMPEG_REINSTALL_MESSAGE
            ),
        )
    return _status("ffmpeg", ok=True, detail=location)


def _check_tesseract() -> dict:
    # The in-process tesserocr module is what the bundled app runs on and
    # what ``create_ocr_backend("tesserocr")`` prefers everywhere — check it
    # first so the report describes the engine that will actually be used.
    if tesserocr_backend_available():
        version = tesserocr_engine_version()
        detail = (
            f"tesserocr module (Tesseract {version})"
            if version
            else "tesserocr module (Tesseract version unknown)"
        )
        return _status("tesseract", ok=True, detail=detail)
    if running_frozen():
        # A bundle without a working tesserocr is a broken bundle; a host CLI
        # cannot be assumed and must never be advised.
        return _status(
            "tesseract",
            ok=False,
            detail="the bundled OCR engine failed to load",
            install_hint=OCR_BUNDLE_DAMAGED_MESSAGE,
        )
    if shutil.which("tesseract") is None:
        return _status(
            "tesseract",
            ok=False,
            detail="not found on PATH",
            install_hint=tesseract_install_hint(),
        )
    version = tesseract_version()
    detail = f"version {version}" if version else "found on PATH (version unknown)"
    return _status("tesseract", ok=True, detail=detail)
