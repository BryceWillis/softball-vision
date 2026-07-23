"""Roster creation helpers for user-pasted team lists."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from sidelinehd_extractor.config import load_project_config_values
from sidelinehd_extractor.models import Roster, RosterPlayer
from sidelinehd_extractor.naming import slugify


ROSTER_CSV_FIELDS = ["number", "full_name", "preferred_name", "display_name", "aliases"]

#: The directory managed rosters live in, resolved relative to CWD (the same
#: base the web app uses). Both the web routes and the CLI admin commands
#: resolve ``rosters/<slug>.csv`` through the helpers below so their slug guard
#: and default-roster logic are one implementation, not two (M7 / 70e).
ROSTERS_DIRNAME = "rosters"

#: Slugs are produced by ``slugify`` (lowercase alphanumerics and underscores),
#: so anything else is not a roster we wrote — reject it before it can name a
#: path outside ``rosters/``.
_ROSTER_SLUG_PATTERN = re.compile(r"^[a-z0-9_]+$")


class UnknownRoster(ValueError):
    """A roster slug that is invalid or names no file under ``rosters/``.

    A ``ValueError`` so the CLI's top-level handler renders it as a clean
    error; the web routes catch it and translate to their 404.
    """


def roster_csv_path(slug: str) -> Path:
    """Resolve a roster slug to its ``rosters/<slug>.csv`` path.

    Raises :class:`UnknownRoster` for anything ``slugify`` would not produce —
    the traversal guard both surfaces share.
    """

    if not _ROSTER_SLUG_PATTERN.match(slug):
        raise UnknownRoster(f"{slug!r} is not a valid roster name")
    return Path(ROSTERS_DIRNAME) / f"{slug}.csv"


def existing_roster_path(slug: str) -> Path:
    """Resolve a slug to an existing roster CSV, else raise :class:`UnknownRoster`."""

    path = roster_csv_path(slug)
    if not path.exists():
        raise UnknownRoster(f"no roster named {slug!r} under {ROSTERS_DIRNAME}/")
    return path


def configured_roster_path() -> Optional[Path]:
    """The raw roster path from ``sidelinehd.cfg``, unvalidated (expanduser only)."""

    value = load_project_config_values().get("roster")
    if not value:
        return None
    return Path(value).expanduser()


def is_configured_default(path: Path) -> bool:
    """Whether ``path`` is the roster ``sidelinehd.cfg`` names as the default."""

    configured = configured_roster_path()
    if configured is None:
        return False
    try:
        return configured.resolve() == path.resolve()
    except OSError:
        return False

#: Item 52: leading comment line that round-trips the pretty team name
#: ("St. Mary's 12U") which the slugged filename cannot carry. Readers fall
#: back to the file stem when absent, so pre-item-52 files still load.
ROSTER_TEAM_NAME_PREFIX = "# team_name:"


@dataclass(frozen=True)
class MakeRosterResult:
    """Summary of a generated roster CSV."""

    output_path: Path
    player_count: int


def parse_team_list(text: str, team_name: str = "roster") -> Roster:
    """Parse a pasted team list into a roster.

    Accepted lines look like ``#26 Amelia V.`` or ``26 Amelia V.``. Blank lines
    and comment lines beginning with ``//`` are ignored.
    """

    players = []
    seen_numbers = set()
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        player = parse_team_list_line(line, line_number=line_number)
        if player.number in seen_numbers:
            raise ValueError(f"duplicate jersey number on line {line_number}: {player.number}")
        seen_numbers.add(player.number)
        players.append(player)

    if not players:
        raise ValueError("team list did not contain any players")
    return Roster(team_name=team_name, players=players)


def parse_team_list_line(line: str, line_number: int = 1) -> RosterPlayer:
    """Parse one roster text line."""

    cleaned = re.sub(r"^\s*[-*]\s*", "", line).strip()
    match = re.match(r"^#?\s*(\d{1,3})\s*[\).:-]?\s+(.+?)\s*$", cleaned)
    if not match:
        raise ValueError(f"could not parse roster line {line_number}: {line!r}")

    number = match.group(1)
    full_name = _clean_name(match.group(2))
    if not full_name:
        raise ValueError(f"roster line {line_number} is missing a player name")

    preferred_name = _preferred_name(full_name)
    aliases = [preferred_name] if preferred_name and preferred_name != full_name else []
    return RosterPlayer(
        number=number,
        full_name=full_name,
        preferred_name=preferred_name or None,
        display_name=full_name,
        aliases=aliases,
    )


def write_roster_csv(roster: Roster, output_path: Path) -> MakeRosterResult:
    """Write a roster CSV in the format consumed by ``load_roster``."""

    destination = output_path.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        if roster.team_name:
            handle.write(f"{ROSTER_TEAM_NAME_PREFIX} {roster.team_name}\r\n")
        writer = csv.DictWriter(handle, fieldnames=ROSTER_CSV_FIELDS)
        writer.writeheader()
        for player in roster.players:
            writer.writerow(
                {
                    "number": player.number,
                    "full_name": player.full_name,
                    "preferred_name": player.preferred_name or "",
                    "display_name": player.display_name or "",
                    "aliases": ";".join(player.aliases),
                }
            )
    return MakeRosterResult(output_path=destination, player_count=len(roster.players))


def make_roster_from_lines(
    lines: Iterable[str],
    output_path: Path,
    team_name: str = "roster",
) -> MakeRosterResult:
    """Parse roster text lines and write a CSV."""

    roster = parse_team_list("\n".join(lines), team_name=team_name)
    return write_roster_csv(roster, output_path)


def default_roster_path(team_name: str) -> Path:
    """Return the default private roster path for a team name."""

    return Path("rosters") / f"{slugify(team_name, fallback='roster')}.csv"


def _clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _preferred_name(full_name: str) -> str:
    return full_name.split()[0].strip(".,")
