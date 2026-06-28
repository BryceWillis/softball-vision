"""Roster creation helpers for user-pasted team lists."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sidelinehd_extractor.models import Roster, RosterPlayer


ROSTER_CSV_FIELDS = ["number", "full_name", "preferred_name", "display_name", "aliases"]


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


def _clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _preferred_name(full_name: str) -> str:
    return full_name.split()[0].strip(".,")
