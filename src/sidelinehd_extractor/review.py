"""Human-readable review output for detected events."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

from sidelinehd_extractor.constants import BATTER_SOURCE_BATTER_CARD, BATTER_SOURCE_LINEUP_STRIP
from sidelinehd_extractor.exports import format_timestamp
from sidelinehd_extractor.models import Event, EventType, Roster


@dataclass(frozen=True)
class ReviewOptions:
    """Thresholds for event review warnings."""

    min_at_bat_gap_seconds: float = 45.0
    repeat_player_window_seconds: float = 180.0
    min_chapter_gap_seconds: float = 180.0


@dataclass(frozen=True)
class ReviewRow:
    """One event plus the review flags attached to it."""

    index: int
    event: Event
    flags: List[str]


def collect_event_review_rows(
    events: Iterable[Event],
    kind: str = "all",
    options: Optional[ReviewOptions] = None,
    roster: Optional[Roster] = None,
) -> List[ReviewRow]:
    """Return review rows for events, including lightweight suspicious flags."""

    options = options or ReviewOptions()
    selected_events = _filter_events(events, kind)
    flags_by_index = _review_flags(selected_events, options, roster=roster)
    return [
        ReviewRow(index=index, event=event, flags=flags_by_index[index - 1])
        for index, event in enumerate(selected_events, start=1)
    ]


def render_event_review(
    events: Iterable[Event],
    kind: str = "all",
    options: Optional[ReviewOptions] = None,
    roster: Optional[Roster] = None,
) -> str:
    """Render detected events with lightweight suspicious flags."""

    rows = collect_event_review_rows(events, kind=kind, options=options, roster=roster)

    lines = [f"{'#':>3}  {'time':<8} {'type':<19} {'label':<28} flags"]
    for row in rows:
        flags = ", ".join(row.flags) or "-"
        lines.append(
            f"{row.index:>3}  "
            f"{format_timestamp(row.event.timestamp_seconds):<8} "
            f"{row.event.event_type.value:<19} "
            f"{row.event.label:<28} "
            f"{flags}"
        )
    return "\n".join(lines)


def _filter_events(events: Iterable[Event], kind: str) -> List[Event]:
    event_list = list(events)
    if kind == "all":
        return event_list
    if kind == "chapters":
        return [
            event
            for event in event_list
            if event.event_type in {EventType.INNING_START, EventType.HALF_INNING_START}
        ]
    if kind == "at-bats":
        return [event for event in event_list if event.event_type == EventType.AT_BAT_START]
    raise ValueError(f"unsupported review kind: {kind}")


def _review_flags(
    events: List[Event],
    options: ReviewOptions,
    roster: Optional[Roster] = None,
) -> List[List[str]]:
    flags_by_index: List[List[str]] = [[] for _ in events]
    previous_at_bat = None
    previous_chapter = None

    for index, event in enumerate(events):
        if event.event_type == EventType.AT_BAT_START:
            if not event.player_name or not event.player_number:
                flags_by_index[index].append("missing-player")
            if event.metadata.get("batter_number_source") == BATTER_SOURCE_LINEUP_STRIP:
                # Non-highlight lineup-strip reads are blocked before event emission;
                # this flag therefore only marks accepted lineup-recovered at-bats.
                flags_by_index[index].append("lineup-recovered")
            disagreement = event.metadata.get("batter_number_disagreement")
            if disagreement:
                flags_by_index[index].append(f"card-vs-lineup={disagreement}")
                lineup_value = _lineup_value_from_disagreement(str(disagreement))
                if lineup_value and _lineup_has_rostered_candidate(lineup_value, roster):
                    flags_by_index[index].append(f"lineup-had-rostered-candidate={lineup_value}")
            ocr_player_number = event.metadata.get("ocr_player_number")
            if (
                roster is not None
                and event.metadata.get("batter_number_source") == BATTER_SOURCE_BATTER_CARD
                and ocr_player_number
                and not roster.name_for_number(str(ocr_player_number))
            ):
                flags_by_index[index].append(f"unrostered-card-number={ocr_player_number}")
            batter_card_name = str(event.metadata.get("batter_card_name") or "")
            if (
                batter_card_name
                and event.metadata.get("roster_match_source") != "name"
                and _is_garbled_card_name(batter_card_name)
            ):
                flags_by_index[index].append("garbled-card-name")
            if (
                ocr_player_number
                and event.player_number
                and str(ocr_player_number) != str(event.player_number)
                and not _has_roster_number_match(event)
            ):
                flags_by_index[index].append(f"ocr-number={ocr_player_number}")
            for flag in event.metadata.get("order_flags") or []:
                flags_by_index[index].append(str(flag))
            if previous_at_bat is not None:
                delta = event.timestamp_seconds - previous_at_bat.timestamp_seconds
                if delta < options.min_at_bat_gap_seconds:
                    flags_by_index[index].append(f"close-at-bat={int(delta)}s")
                if (
                    event.player_number
                    and previous_at_bat.player_number == event.player_number
                    and delta < options.repeat_player_window_seconds
                ):
                    flags_by_index[index].append(f"repeat-player={int(delta)}s")
            previous_at_bat = event

        if event.event_type in {EventType.INNING_START, EventType.HALF_INNING_START}:
            if previous_chapter is not None:
                delta = event.timestamp_seconds - previous_chapter.timestamp_seconds
                if delta < options.min_chapter_gap_seconds:
                    flags_by_index[index].append(f"close-chapter={int(delta)}s")
            previous_chapter = event

    return flags_by_index


def _has_roster_number_match(event: Event) -> bool:
    return event.metadata.get("roster_match_source") in {"name", "lineup_number"}


def _is_garbled_card_name(value: str) -> bool:
    """Return true when OCR text has no player-like alphabetic token."""

    return not any(_alphabetic_length(token) >= 3 for token in value.split())


def _alphabetic_length(value: str) -> int:
    return sum(1 for character in value if character.isalpha())


def _lineup_value_from_disagreement(value: str) -> Optional[str]:
    match = re.search(r"(?:^|\s)lineup=([0-9]+)", value)
    if not match:
        return None
    return match.group(1)


def _lineup_has_rostered_candidate(value: str, roster: Optional[Roster]) -> bool:
    """Return true when a lineup digit run contains a rostered jersey number."""

    if roster is None:
        return False
    digits = re.sub(r"\D+", "", value)
    if not digits:
        return False
    for width in (1, 2):
        for index in range(0, len(digits) - width + 1):
            if roster.name_for_number(digits[index : index + width]):
                return True
    return False
