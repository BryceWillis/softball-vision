"""Core data models for the SidelineHD extraction pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


ScalarValue = Optional[Union[str, int, float, bool]]
PathLike = Union[str, Path]


class HalfInning(str, Enum):
    """A baseball or softball half-inning."""

    TOP = "top"
    BOTTOM = "bottom"


class EventType(str, Enum):
    """High-level events emitted by the validated overlay state stream."""

    GAME_START = "game_start"
    INNING_START = "inning_start"
    HALF_INNING_START = "half_inning_start"
    AT_BAT_START = "at_bat_start"
    SCORE_CHANGE = "score_change"
    UNKNOWN = "unknown"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_range(name: str, value: Optional[float], minimum: float, maximum: float) -> None:
    if value is None:
        return
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")


def _validate_minimum(name: str, value: Optional[float], minimum: float) -> None:
    if value is None:
        return
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")


@dataclass(frozen=True)
class Video:
    """A local source video and probe metadata."""

    path: Path
    sha256: Optional[str] = None
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    frame_count: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", self.path.expanduser())
        _validate_minimum("duration_seconds", self.duration_seconds, 0)
        _validate_minimum("width", self.width, 1)
        _validate_minimum("height", self.height, 1)
        _validate_minimum("fps", self.fps, 0)
        _validate_minimum("frame_count", self.frame_count, 0)


@dataclass(frozen=True)
class RegionFraction:
    """A frame-relative rectangular region.

    Coordinates are fractions in the inclusive-exclusive normalized frame space:
    ``x`` and ``y`` are the top-left corner, while ``width`` and ``height`` are
    positive extents.
    """

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        _validate_range("x", self.x, 0.0, 1.0)
        _validate_range("y", self.y, 0.0, 1.0)
        _validate_range("width", self.width, 0.0, 1.0)
        _validate_range("height", self.height, 0.0, 1.0)
        if self.width <= 0:
            raise ValueError("width must be > 0")
        if self.height <= 0:
            raise ValueError("height must be > 0")
        if self.x + self.width > 1.0:
            raise ValueError("x + width must be <= 1.0")
        if self.y + self.height > 1.0:
            raise ValueError("y + height must be <= 1.0")


@dataclass
class OverlayTemplate:
    """Named crop regions for a SidelineHD overlay layout."""

    name: str
    video_width: Optional[int] = None
    video_height: Optional[int] = None
    regions: Dict[str, RegionFraction] = field(default_factory=dict)
    notes: Optional[str] = None


@dataclass
class OCRSample:
    """Raw OCR output captured for a field at a specific video timestamp."""

    timestamp_seconds: float
    field_name: str
    raw_text: str
    video_sha256: Optional[str] = None
    normalized_text: Optional[str] = None
    confidence: Optional[float] = None
    crop_path: Optional[Path] = None
    source_detail: Optional[str] = None
    created_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        _validate_minimum("timestamp_seconds", self.timestamp_seconds, 0)
        _validate_range("confidence", self.confidence, 0.0, 1.0)


@dataclass(frozen=True)
class OverlayState:
    """Validated state inferred from one or more OCR samples."""

    timestamp_seconds: float
    inning: Optional[int] = None
    half: Optional[HalfInning] = None
    balls: Optional[int] = None
    strikes: Optional[int] = None
    outs: Optional[int] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    batter_number: Optional[str] = None
    batting_team: Optional[str] = None
    confidence: Optional[float] = None
    source_sample_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_minimum("timestamp_seconds", self.timestamp_seconds, 0)
        _validate_minimum("inning", self.inning, 1)
        _validate_range("balls", self.balls, 0, 4)
        _validate_range("strikes", self.strikes, 0, 3)
        _validate_range("outs", self.outs, 0, 3)
        _validate_minimum("home_score", self.home_score, 0)
        _validate_minimum("away_score", self.away_score, 0)
        _validate_range("confidence", self.confidence, 0.0, 1.0)


@dataclass
class Event:
    """A timestamped moment suitable for review or export."""

    event_type: EventType
    timestamp_seconds: float
    label: str
    inning: Optional[int] = None
    half: Optional[HalfInning] = None
    player_number: Optional[str] = None
    player_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_minimum("timestamp_seconds", self.timestamp_seconds, 0)
        _validate_minimum("inning", self.inning, 1)


@dataclass
class Correction:
    """Manual correction applied during review."""

    target_type: str
    target_id: str
    field_name: str
    original_value: ScalarValue = None
    corrected_value: ScalarValue = None
    reason: Optional[str] = None
    created_at: datetime = field(default_factory=_utc_now)


@dataclass
class RosterPlayer:
    """One player in the local team roster."""

    number: str
    full_name: str
    preferred_name: Optional[str] = None
    display_name: Optional[str] = None
    aliases: List[str] = field(default_factory=list)


@dataclass
class Roster:
    """Local team roster keyed by jersey number."""

    team_name: str
    players: List[RosterPlayer] = field(default_factory=list)

    def name_for_number(self, number: Union[str, int]) -> Optional[str]:
        normalized = str(number).strip().lstrip("#")
        for player in self.players:
            if player.number.strip().lstrip("#") == normalized:
                return player.display_name or player.full_name or player.preferred_name
        return None

    def number_for_name(self, name: str) -> Optional[str]:
        normalized = normalize_roster_name(name)
        if not normalized:
            return None
        fuzzy_matches = []
        for player in self.players:
            candidates = [
                player.full_name,
                player.preferred_name,
                player.display_name,
                *player.aliases,
            ]
            for candidate in candidates:
                if not candidate:
                    continue
                candidate_name = normalize_roster_name(candidate)
                if candidate_name == normalized:
                    return player.number.strip().lstrip("#")
                if min(len(candidate_name), len(normalized)) >= 5:
                    score = SequenceMatcher(None, candidate_name, normalized).ratio()
                    if score >= 0.84:
                        fuzzy_matches.append((score, player.number.strip().lstrip("#")))
        if fuzzy_matches:
            fuzzy_matches.sort(reverse=True)
            return fuzzy_matches[0][1]
        return None


def normalize_roster_name(value: str) -> str:
    """Normalize a player name for roster/OCR matching."""

    return "".join(character.lower() for character in value if character.isalpha())
