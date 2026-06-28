"""Configuration file loaders for templates and rosters."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Optional

from sidelinehd_extractor.models import OverlayTemplate, RegionFraction, Roster, RosterPlayer


def _read_json(path: Path) -> Dict[str, Any]:
    with path.expanduser().open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return data


def load_overlay_template(path: Path) -> OverlayTemplate:
    """Load an overlay template JSON file."""

    source = path.expanduser()
    data = _read_json(source)
    raw_regions = data.get("regions")
    if not isinstance(raw_regions, dict) or not raw_regions:
        raise ValueError("overlay template must include a non-empty 'regions' object")

    regions = {}
    for name, raw_region in raw_regions.items():
        if not isinstance(raw_region, dict):
            raise ValueError(f"region '{name}' must be an object")
        regions[name] = RegionFraction(
            x=float(raw_region["x"]),
            y=float(raw_region["y"]),
            width=float(raw_region["width"]),
            height=float(raw_region["height"]),
        )

    return OverlayTemplate(
        name=str(data.get("name") or source.stem),
        video_width=data.get("video_width"),
        video_height=data.get("video_height"),
        regions=regions,
        notes=data.get("notes"),
    )


def default_overlay_template() -> OverlayTemplate:
    """Return a safe fallback template that crops the whole frame."""

    return OverlayTemplate(
        name="full_frame",
        regions={"full_frame": RegionFraction(x=0.0, y=0.0, width=1.0, height=1.0)},
        notes="Fallback template used when no overlay template is provided.",
    )


def load_roster(path: Path, team_name: Optional[str] = None) -> Roster:
    """Load a roster from CSV or JSON."""

    source = path.expanduser()
    suffix = source.suffix.lower()
    if suffix == ".csv":
        return load_roster_csv(source, team_name=team_name)
    if suffix == ".json":
        return load_roster_json(source, team_name=team_name)
    raise ValueError("roster must be a .csv or .json file")


def load_roster_csv(path: Path, team_name: Optional[str] = None) -> Roster:
    """Load a roster CSV.

    Required columns are ``number`` and ``full_name``. Optional columns are
    ``preferred_name``, ``display_name``, and ``aliases``. Aliases are separated
    with semicolons.
    """

    source = path.expanduser()
    players = []
    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("roster CSV must include a header row")
        required = {"number", "full_name"}
        missing = required.difference(reader.fieldnames)
        if missing:
            raise ValueError(f"roster CSV missing required columns: {', '.join(sorted(missing))}")

        for row in reader:
            number = (row.get("number") or "").strip()
            full_name = (row.get("full_name") or "").strip()
            if not number or not full_name:
                continue
            preferred_name = (row.get("preferred_name") or "").strip() or None
            display_name = (row.get("display_name") or "").strip() or None
            aliases = [
                alias.strip()
                for alias in (row.get("aliases") or "").split(";")
                if alias.strip()
            ]
            players.append(
                RosterPlayer(
                    number=number,
                    full_name=full_name,
                    preferred_name=preferred_name,
                    display_name=display_name,
                    aliases=aliases,
                )
            )

    return Roster(team_name=team_name or source.stem, players=players)


def load_roster_json(path: Path, team_name: Optional[str] = None) -> Roster:
    """Load a roster JSON file."""

    source = path.expanduser()
    data = _read_json(source)
    raw_players = data.get("players")
    if not isinstance(raw_players, list):
        raise ValueError("roster JSON must include a 'players' list")

    players = []
    for raw_player in raw_players:
        if not isinstance(raw_player, dict):
            raise ValueError("each roster player must be an object")
        players.append(
            RosterPlayer(
                number=str(raw_player["number"]).strip(),
                full_name=str(raw_player["full_name"]).strip(),
                preferred_name=raw_player.get("preferred_name"),
                display_name=raw_player.get("display_name"),
                aliases=list(raw_player.get("aliases") or []),
            )
        )

    return Roster(team_name=team_name or str(data.get("team_name") or source.stem), players=players)
