"""Export helpers for YouTube-friendly timestamps."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Optional

from sidelinehd_extractor.models import Event, EventType


PROJECT_URL = "https://github.com/BryceWillis/softball-vision"
PROJECT_CREDIT = (
    "Timestamps generated with SidelineHD Chapter and At-Bat Extractor "
    f"(MIT License): {PROJECT_URL}"
)

_CHAPTER_EVENT_TYPES = (
    EventType.INNING_START,
    EventType.HALF_INNING_START,
    EventType.GAME_FINAL,
)

# Which chapter survives when two render at the same timestamp: the most
# terminal one. A half-inning a final lands on is a zero-length chapter and
# carries nothing the Final line does not already carry, score included.
_CHAPTER_TERMINALITY = {
    EventType.INNING_START: 0,
    EventType.HALF_INNING_START: 1,
    EventType.GAME_FINAL: 2,
}


def format_timestamp(seconds: float) -> str:
    """Format seconds as a YouTube timestamp.

    Durations under one hour are emitted as ``M:SS``. Longer durations use
    ``H:MM:SS``.
    """

    if seconds < 0:
        raise ValueError("seconds must be non-negative")

    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def export_youtube_chapters(
    events: Iterable[Event],
    include_intro: bool = True,
    intro_label: str = "Pregame",
    include_credit: bool = True,
    include_score: bool = True,
) -> str:
    """Render inning and half-inning events as YouTube description chapters."""

    lines = []
    first_chapter_stamp = None
    for stamp, event in _collapse_chapter_collisions(events):
        if first_chapter_stamp is None:
            first_chapter_stamp = stamp
        lines.append(f"{stamp} {_chapter_label(event, include_score=include_score)}")

    intro_stamp = format_timestamp(0)
    if include_intro and lines and first_chapter_stamp != intro_stamp:
        lines.insert(0, f"{intro_stamp} {intro_label}")
    return _render_lines_with_credit(lines, include_credit=include_credit)


def _collapse_chapter_collisions(events: Iterable[Event]) -> list[tuple[str, Event]]:
    """Return one chapter event per rendered timestamp, most terminal wins.

    YouTube requires chapter timestamps to be strictly increasing, and renders
    **no chapters at all** — silently — when two lines share one. So a
    ``GAME_FINAL`` landing on the same state as the last ``HALF_INNING_START``
    costs the whole description rather than one line (CR-117).

    Collisions are judged on the *rendered* stamp, not the raw float, because
    ``format_timestamp`` truncates: two events 0.7s apart render identically
    while comparing as different numbers.

    The fix belongs here rather than in ``detect_events`` — ``events.jsonl``
    should keep recording both facts, since the half-inning really did start
    and the game really did end, and the constraint being violated is
    YouTube's rather than the state machine's.
    """

    chosen: dict[str, Event] = {}
    for event in events:
        if event.event_type not in _CHAPTER_EVENT_TYPES:
            continue
        stamp = format_timestamp(event.timestamp_seconds)
        previous = chosen.get(stamp)
        if previous is None or (
            _CHAPTER_TERMINALITY[event.event_type]
            >= _CHAPTER_TERMINALITY[previous.event_type]
        ):
            # Ties on type keep the later event for the same reason the rule
            # exists: the earlier one's chapter has no duration to offer.
            chosen[stamp] = event
    return list(chosen.items())


def export_at_bat_comment(
    events: Iterable[Event],
    include_inning_headers: bool = True,
    include_credit: bool = True,
) -> str:
    """Render our team's at-bats as a pasteable pinned-comment timestamp list."""

    lines = []
    current_inning = None
    active_inning = None
    for event in events:
        if event.event_type in {EventType.INNING_START, EventType.HALF_INNING_START} and event.inning is not None:
            active_inning = event.inning
        if event.event_type == EventType.AT_BAT_START:
            event_inning = active_inning if active_inning is not None else event.inning
            if include_inning_headers and event_inning != current_inning:
                if lines:
                    lines.append("")
                lines.append(format_inning_header(event_inning))
                current_inning = event_inning
            lines.append(f"{format_timestamp(event.timestamp_seconds)} {event.label}")
    return _render_lines_with_credit(lines, include_credit=include_credit)


def format_inning_header(inning: Optional[int]) -> str:
    """Return a readable pinned-comment inning header."""

    if inning is None:
        return "Unknown Inning"
    return f"{_ordinal(inning)} Inning"


def _chapter_label(event: Event, include_score: bool = True) -> str:
    label = event.label
    if include_score and event.event_type in {
        EventType.HALF_INNING_START,
        EventType.GAME_FINAL,
    }:
        away_score = event.metadata.get("away_score")
        home_score = event.metadata.get("home_score")
        if away_score is not None and home_score is not None:
            label = f"{label} ({away_score}-{home_score})"
    return label


def _ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def _render_lines_with_credit(lines: list[str], include_credit: bool = True) -> str:
    if include_credit and lines:
        lines = [*lines, "", PROJECT_CREDIT]
    return "\n".join(lines)
