"""Configuration file loaders for templates and rosters."""

from __future__ import annotations

import configparser
import csv
import json
import sys
from importlib import resources
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from sidelinehd_extractor.models import OverlayTemplate, RegionFraction, Roster, RosterPlayer

CONFIG_FILENAME = "sidelinehd.cfg"
_PROJECT_CONFIG_SECTION = "defaults"


@dataclass(frozen=True)
class ProjectConfig:
    """Project-local defaults loaded from ``sidelinehd.cfg``."""

    roster: Optional[Path] = None
    template: Optional[Path] = None
    team_name: Optional[str] = None


def load_project_config(cwd: Optional[Path] = None) -> ProjectConfig:
    """Load project-local defaults, returning an empty config when absent."""

    root = cwd or Path.cwd()
    values = load_project_config_values(cwd=root)
    return ProjectConfig(
        roster=_project_config_path(values.get("roster"), root, "roster"),
        template=_project_config_path(values.get("template"), root, "template"),
        team_name=values.get("team_name"),
    )


def load_project_config_values(cwd: Optional[Path] = None) -> Dict[str, str]:
    """Load raw project-local default strings without validating paths."""

    root = cwd or Path.cwd()
    path = root / CONFIG_FILENAME
    if not path.exists():
        return {}

    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error as exc:
        print(f"Warning: could not read {CONFIG_FILENAME}: {exc}", file=sys.stderr)
        return {}

    if _PROJECT_CONFIG_SECTION not in parser:
        return {}

    section = parser[_PROJECT_CONFIG_SECTION]
    values = {}
    for key in ("roster", "template", "team_name"):
        value = (section.get(key) or "").strip()
        if value:
            values[key] = value
    return values


def write_project_config(config: ProjectConfig, cwd: Optional[Path] = None) -> Path:
    """Write project-local defaults to ``sidelinehd.cfg``."""

    root = cwd or Path.cwd()
    path = root / CONFIG_FILENAME
    parser = configparser.ConfigParser()
    parser[_PROJECT_CONFIG_SECTION] = {}
    if config.roster is not None:
        parser[_PROJECT_CONFIG_SECTION]["roster"] = str(config.roster)
    if config.template is not None:
        parser[_PROJECT_CONFIG_SECTION]["template"] = str(config.template)
    if config.team_name:
        parser[_PROJECT_CONFIG_SECTION]["team_name"] = config.team_name
    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle)
    return path


def _project_config_path(value: Optional[str], root: Path, key: str) -> Optional[Path]:
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    path = Path(stripped).expanduser()
    check_path = path if path.is_absolute() else root / path
    if not check_path.exists():
        print(
            f"Warning: {CONFIG_FILENAME} {key} path does not exist: {path}",
            file=sys.stderr,
        )
        return None
    return path


def _read_json(path: Path) -> Dict[str, Any]:
    with path.expanduser().open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return data


def load_overlay_template(path: Path) -> OverlayTemplate:
    """Load an overlay template JSON file."""

    source = path.expanduser()
    return _overlay_template_from_data(_read_json(source), fallback_name=source.stem)


def _overlay_template_from_data(data: Dict[str, Any], fallback_name: str) -> OverlayTemplate:
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
        name=str(data.get("name") or fallback_name),
        video_width=data.get("video_width"),
        video_height=data.get("video_height"),
        regions=regions,
        notes=data.get("notes"),
    )


BUILTIN_TEMPLATE_NAME = "sidelinehd_640x360_active"


def builtin_overlay_template() -> OverlayTemplate:
    """Load the packaged SidelineHD overlay template shipped with the tool."""

    resource = (
        resources.files("sidelinehd_extractor")
        .joinpath("data")
        .joinpath(f"{BUILTIN_TEMPLATE_NAME}.json")
    )
    data = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("packaged overlay template must be a JSON object")
    return _overlay_template_from_data(data, fallback_name=BUILTIN_TEMPLATE_NAME)


def default_overlay_template() -> OverlayTemplate:
    """Return the template used when no overlay template is configured.

    This is the packaged SidelineHD scorebug template, not a whole-frame crop:
    a run with no configured template must still read real scoreboard regions
    (a full-frame fallback OCRs mush and silently yields zero events). Callers
    that genuinely want the whole frame opt in via
    ``full_frame_overlay_template``.
    """

    return builtin_overlay_template()


def full_frame_overlay_template() -> OverlayTemplate:
    """Return the single whole-frame region template (explicit opt-in only)."""

    return OverlayTemplate(
        name="full_frame",
        regions={"full_frame": RegionFraction(x=0.0, y=0.0, width=1.0, height=1.0)},
        notes="Whole-frame template for calibration/debugging; not an OCR default.",
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
