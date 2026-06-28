"""Game-name and filesystem naming helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional


def slugify(value: str, fallback: str = "game") -> str:
    """Return a conservative filename slug."""

    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or fallback


def game_name_for_run(run_path: Path, explicit_name: Optional[str] = None) -> str:
    """Return a display-ish game name from a run directory or file path."""

    if explicit_name:
        return explicit_name.strip()

    source = run_path.expanduser()
    manifest_path = source / "manifest.json" if source.is_dir() else source.parent / "manifest.json"
    if manifest_path.exists():
        manifest_name = _game_name_from_manifest(manifest_path)
        if manifest_name:
            return manifest_name

    return strip_run_timestamp(source.stem)


def game_slug_for_run(run_path: Path, explicit_name: Optional[str] = None) -> str:
    """Return a filesystem slug for a run/game."""

    return slugify(game_name_for_run(run_path, explicit_name=explicit_name))


def strip_run_timestamp(value: str) -> str:
    """Remove the run-directory timestamp suffix if present."""

    return re.sub(r"-\d{8}-\d{6}(?:-\d+)?$", "", value)


def _game_name_from_manifest(path: Path) -> Optional[str]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    video = data.get("video")
    if isinstance(video, dict) and video.get("path"):
        video_path = Path(str(video["path"]))
        info_title = _title_from_info_json(video_path)
        if info_title:
            return info_title
        return video_path.stem
    return None


def _title_from_info_json(video_path: Path) -> Optional[str]:
    info_path = video_path.with_suffix(".info.json")
    if not info_path.exists():
        return None
    with info_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    title = data.get("title")
    return str(title).strip() if title else None
