"""Build provenance for the packaged app (item 67a).

A frozen ``.app`` bundle has no git checkout and its CWD is the data dir, so
item 65's ``git_short_sha()`` returns ``None`` and the footer degrades to a
bare version string — nothing distinguishes a bundle built today from one
built in March. The PyInstaller spec bakes a ``build_info.json`` (version,
short SHA, build date) into the bundle; this module reads it back.

A launcher must never fail to launch over a provenance file: every read
error here — missing file, malformed JSON, wrong shape — degrades to the
source-path lookup rather than raising.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

BUILD_INFO_FILENAME = "build_info.json"


@dataclass(frozen=True)
class BuildStamp:
    version: str
    sha: Optional[str]
    built_at: Optional[str]  # ISO-8601 UTC, e.g. "2026-07-20T18:04:05Z"
    origin: Literal["bundle", "source"]


def _bundle_stamp() -> Optional[BuildStamp]:
    """Read the baked ``build_info.json``, or ``None`` on any defect at all."""

    try:
        bundle_dir = Path(getattr(sys, "_MEIPASS", "") or Path(sys.executable).parent)
        raw = json.loads((bundle_dir / BUILD_INFO_FILENAME).read_text(encoding="utf-8"))
        version = raw["version"]
        sha = raw.get("sha")
        built_at = raw.get("built_at")
        if not isinstance(version, str) or not version:
            return None
        if not (sha is None or isinstance(sha, str)):
            return None
        if not (built_at is None or isinstance(built_at, str)):
            return None
        return BuildStamp(
            version=version, sha=sha or None, built_at=built_at or None, origin="bundle"
        )
    except Exception:
        return None


def build_stamp() -> BuildStamp:
    """The provenance of the running code, read on demand.

    Frozen with a healthy baked file → ``origin="bundle"``. Everything else —
    running from source, or a bundle whose ``build_info.json`` is missing or
    corrupt — falls back to item 65's package-version + git lookup with
    ``origin="source"``. ``origin`` is decided by ``sys.frozen``, never by
    whether the file happened to be readable.
    """

    if getattr(sys, "frozen", False):
        stamp = _bundle_stamp()
        if stamp is not None:
            return stamp
    # Lazy import: lifecycle imports desktop, which imports this module —
    # a top-level import here would close that loop.
    from sidelinehd_extractor.webapp import lifecycle

    return BuildStamp(
        version=lifecycle.package_version(),
        sha=lifecycle.git_short_sha(),
        built_at=None,
        origin="source",
    )


def stamp_label(stamp: BuildStamp) -> str:
    """Item 65's banner vocabulary plus a build date: ``v0.2.0 (a1b2c3d) · built 2026-07-20``.

    Absent segments drop cleanly, so the source path with no git renders
    just ``v0.2.0``.
    """

    from sidelinehd_extractor.webapp import lifecycle

    label = lifecycle.version_display(stamp.version, stamp.sha)
    if stamp.built_at:
        label += f" · built {_display_date(stamp.built_at)}"
    return label


def _display_date(built_at: str) -> str:
    """The date portion of the ISO timestamp — or the raw string if unparseable.

    The stamp is for a human's eyes, not for arithmetic; a bad timestamp
    must render, not raise.
    """

    try:
        return datetime.fromisoformat(built_at.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return built_at
