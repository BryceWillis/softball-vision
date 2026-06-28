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
        index = _find_target_event(corrected_events, correction, deleted_indexes)
        if _is_delete_field(correction.field_name):
            deleted_indexes.add(index)
            continue
        corrected_events[index] = _apply_field_correction(corrected_events[index], correction)

    return [event for index, event in enumerate(corrected_events) if index not in deleted_indexes]


def _correction_from_row(row: dict, row_number: int) -> EventCorrection:
    timestamp_text = (row.get("timestamp_seconds") or row.get("timestamp") or "").strip()
    if not timestamp_text:
        raise ValueError(f"corrections row {row_number} is missing a timestamp")

    event_type_text = (row.get("event_type") or "").strip()
    event_type = EventType(event_type_text) if event_type_text else None
    match_window_text = (row.get("match_window_seconds") or row.get("match_window") or "").strip()

    return EventCorrection(
        timestamp_seconds=parse_timestamp_value(timestamp_text),
        event_type=event_type,
        field_name=(row.get("field") or "").strip(),
        value=(row.get("value") or "").strip(),
        match_window_seconds=float(match_window_text) if match_window_text else 0.5,
        reason=(row.get("reason") or "").strip() or None,
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


def _is_delete_field(field_name: str) -> bool:
    return field_name.strip() in {"delete", "remove", "skip"}


def _is_blank_row(row: dict) -> bool:
    return not any((value or "").strip() for value in row.values())
