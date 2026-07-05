"""Dependency preflight: report the health of external tools before a run.

Item 54a. Checks each external dependency the pipeline needs — yt-dlp,
ffmpeg, and Tesseract — and reports a uniform status the CLI ``start``
command and the web index page can render as guidance. Never raises: a
missing dependency becomes ``ok: False`` plus an OS-specific install hint,
not a traceback.
"""

from __future__ import annotations

import shutil
from typing import List, Optional

from sidelinehd_extractor.ocr import tesseract_install_hint, tesseract_version
from sidelinehd_extractor.youtube import (
    YTDLP_REINSTALL_MESSAGE,
    command_as_string,
    default_ytdlp_executable,
    resolve_ffmpeg_location,
)

FFMPEG_REINSTALL_MESSAGE = (
    "ffmpeg ships with this package via the imageio-ffmpeg dependency. "
    "Reinstall with `pip install -e .` so the bundled build is available."
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
        command = default_ytdlp_executable()
    except FileNotFoundError:
        return _status(
            "yt-dlp",
            ok=False,
            detail="not found on PATH or as an installed Python module",
            install_hint=YTDLP_REINSTALL_MESSAGE,
        )
    return _status("yt-dlp", ok=True, detail=command_as_string(command))


def _check_ffmpeg() -> dict:
    location = resolve_ffmpeg_location()
    if location is None:
        return _status(
            "ffmpeg",
            ok=False,
            detail="no system ffmpeg and the bundled build is unavailable",
            install_hint=FFMPEG_REINSTALL_MESSAGE,
        )
    return _status("ffmpeg", ok=True, detail=location)


def _check_tesseract() -> dict:
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
