"""Export helpers for YouTube-friendly timestamps."""

from __future__ import annotations

from collections.abc import Iterable

from sidelinehd_extractor.models import Event, EventType


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
) -> str:
    """Render inning and half-inning events as YouTube description chapters."""

    lines = []
    first_chapter_seconds = None
    for event in events:
        if event.event_type in {EventType.INNING_START, EventType.HALF_INNING_START}:
            if first_chapter_seconds is None:
                first_chapter_seconds = event.timestamp_seconds
            lines.append(f"{format_timestamp(event.timestamp_seconds)} {event.label}")

    if include_intro and lines and first_chapter_seconds and first_chapter_seconds > 0:
        lines.insert(0, f"0:00 {intro_label}")
    return "\n".join(lines)


def export_at_bat_comment(
    events: Iterable[Event],
    include_inning_headers: bool = True,
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
    return "\n".join(lines)


def format_inning_header(inning: int) -> str:
    """Return a readable pinned-comment inning header."""

    if inning is None:
        return "Unknown Inning"
    return f"{_ordinal(inning)} Inning"


def _ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"
