"""Manual event correction helpers."""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, List, Optional

from sidelinehd_extractor.calibration import parse_timestamp_value
from sidelinehd_extractor.models import Event, EventType, HalfInning


@dataclass(frozen=True)
class EventCorrection:
    """One CSV correction targeting an event near a timestamp."""

    timestamp_seconds: float
    field_name: str
    value: str
    event_type: Optional[EventType] = None
    match_window_seconds: float = 0.5
    reason: Optional[str] = None
    label: Optional[str] = None
    player_number: Optional[str] = None
    player_name: Optional[str] = None
    inning: Optional[int] = None
    half: Optional[HalfInning] = None


# Canonical column order for written corrections files — a superset of what
# load_event_corrections accepts, so hand-edited files round-trip.
CORRECTION_CSV_COLUMNS = (
    "event_type",
    "timestamp",
    "field",
    "value",
    "match_window_seconds",
    "reason",
    "label",
    "player_number",
    "player_name",
    "inning",
    "half",
)


def correction_key(correction: EventCorrection) -> tuple:
    """Identity for de-duplication: one correction per (type, timestamp, field)."""

    return (
        correction.event_type.value if correction.event_type else "",
        round(correction.timestamp_seconds, 3),
        correction.field_name.strip(),
    )


def upsert_event_correction(
    corrections: Iterable[EventCorrection],
    correction: EventCorrection,
) -> List[EventCorrection]:
    """Replace the correction with the same key, or append; preserves order."""

    key = correction_key(correction)
    result = list(corrections)
    for index, existing in enumerate(result):
        if correction_key(existing) == key:
            result[index] = correction
            return result
    result.append(correction)
    return result


def remove_event_correction(
    corrections: Iterable[EventCorrection],
    key: tuple,
) -> List[EventCorrection]:
    """Drop the correction matching the (type, timestamp, field) key, if any."""

    return [existing for existing in corrections if correction_key(existing) != key]


def write_event_corrections(path: Path, corrections: Iterable[EventCorrection]) -> None:
    """Write corrections as CSV with the full canonical header."""

    destination = path.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CORRECTION_CSV_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for correction in corrections:
            writer.writerow(
                {
                    "event_type": correction.event_type.value if correction.event_type else "",
                    "timestamp": _format_seconds(correction.timestamp_seconds),
                    "field": correction.field_name,
                    "value": correction.value,
                    "match_window_seconds": _format_seconds(correction.match_window_seconds),
                    "reason": correction.reason or "",
                    "label": correction.label or "",
                    "player_number": correction.player_number or "",
                    "player_name": correction.player_name or "",
                    "inning": "" if correction.inning is None else str(correction.inning),
                    "half": correction.half.value if correction.half else "",
                }
            )


def _format_seconds(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text or "0"


def load_event_corrections(path: Path) -> List[EventCorrection]:
    """Load event corrections from CSV."""

    corrections = []
    with path.expanduser().open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return corrections
        required = {"field", "value"}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"corrections CSV is missing required columns: {', '.join(sorted(missing))}")
        if "timestamp_seconds" not in reader.fieldnames and "timestamp" not in reader.fieldnames:
            raise ValueError("corrections CSV must include timestamp_seconds or timestamp")

        for row_number, row in enumerate(reader, start=2):
            if _is_blank_row(row):
                continue
            corrections.append(_correction_from_row(row, row_number))
    return corrections


def apply_event_corrections(
    events: Iterable[Event],
    corrections: Iterable[EventCorrection],
) -> List[Event]:
    """Apply CSV corrections to events and return corrected copies."""

    corrected_events = list(events)
    deleted_indexes = set()

    for correction in corrections:
        if _is_add_field(correction.field_name):
            corrected_events.append(_event_from_add_correction(correction))
            continue
        index = _find_target_event(corrected_events, correction, deleted_indexes)
        if _is_delete_field(correction.field_name):
            deleted_indexes.add(index)
            continue
        corrected_events[index] = _apply_field_correction(corrected_events[index], correction)

    return sorted(
        [event for index, event in enumerate(corrected_events) if index not in deleted_indexes],
        key=lambda event: event.timestamp_seconds,
    )


def _correction_from_row(row: dict, row_number: int) -> EventCorrection:
    timestamp_text = (row.get("timestamp_seconds") or row.get("timestamp") or "").strip()
    if not timestamp_text:
        raise ValueError(f"corrections row {row_number} is missing a timestamp")

    event_type_text = (row.get("event_type") or "").strip()
    event_type = EventType(event_type_text) if event_type_text else None
    match_window_text = (row.get("match_window_seconds") or row.get("match_window") or "").strip()
    half_text = (row.get("half") or "").strip()
    inning_text = (row.get("inning") or "").strip()

    return EventCorrection(
        timestamp_seconds=parse_timestamp_value(timestamp_text),
        event_type=event_type,
        field_name=(row.get("field") or "").strip(),
        value=(row.get("value") or "").strip(),
        match_window_seconds=float(match_window_text) if match_window_text else 0.5,
        reason=(row.get("reason") or "").strip() or None,
        label=(row.get("label") or "").strip() or None,
        player_number=(row.get("player_number") or "").strip() or None,
        player_name=(row.get("player_name") or "").strip() or None,
        inning=int(inning_text) if inning_text else None,
        half=HalfInning(half_text) if half_text else None,
    )


def _find_target_event(
    events: List[Event],
    correction: EventCorrection,
    deleted_indexes: set,
) -> int:
    candidates = []
    for index, event in enumerate(events):
        if index in deleted_indexes:
            continue
        if correction.event_type is not None and event.event_type != correction.event_type:
            continue
        distance = abs(event.timestamp_seconds - correction.timestamp_seconds)
        if distance <= correction.match_window_seconds:
            candidates.append((distance, index))

    if not candidates:
        raise ValueError(
            "no event matched correction "
            f"{correction.event_type or '*'} at {correction.timestamp_seconds:.3f}s"
        )

    candidates.sort()
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        raise ValueError(
            "multiple events matched correction "
            f"{correction.event_type or '*'} at {correction.timestamp_seconds:.3f}s"
        )
    return candidates[0][1]


def _apply_field_correction(event: Event, correction: EventCorrection) -> Event:
    field_name = correction.field_name.strip()
    value = correction.value

    if field_name == "label":
        return replace(event, label=value)
    if field_name == "timestamp_seconds":
        return replace(event, timestamp_seconds=parse_timestamp_value(value))
    if field_name == "player_number":
        return replace(event, player_number=value or None)
    if field_name == "player_name":
        return replace(event, player_name=value or None)
    if field_name == "inning":
        return replace(event, inning=int(value) if value else None)
    if field_name == "half":
        return replace(event, half=HalfInning(value) if value else None)
    if field_name == "event_type":
        return replace(event, event_type=EventType(value))

    raise ValueError(f"unsupported correction field: {field_name}")


def _event_from_add_correction(correction: EventCorrection) -> Event:
    if correction.event_type is None:
        raise ValueError("add correction requires event_type")
    label = correction.label or correction.value
    if not label:
        label = _format_added_event_label(correction)
    return Event(
        event_type=correction.event_type,
        timestamp_seconds=correction.timestamp_seconds,
        label=label,
        inning=correction.inning,
        half=correction.half,
        player_number=correction.player_number,
        player_name=correction.player_name,
        metadata={"source": "manual_correction"},
    )


def _format_added_event_label(correction: EventCorrection) -> str:
    if correction.player_name and correction.player_number:
        return f"{correction.player_name} (#{correction.player_number})"
    if correction.player_number:
        return f"#{correction.player_number}"
    raise ValueError("add correction requires label or player_number")


def _is_add_field(field_name: str) -> bool:
    return field_name.strip() in {"add", "insert"}


def _is_delete_field(field_name: str) -> bool:
    return field_name.strip() in {"delete", "remove", "skip"}


def _is_blank_row(row: dict) -> bool:
    return not any((value or "").strip() for value in row.values())
