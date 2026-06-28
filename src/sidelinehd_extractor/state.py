"""Parse OCR samples into structured overlay state rows."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sidelinehd_extractor.models import HalfInning, OCRSample, OverlayState
from sidelinehd_extractor.processing import write_jsonl


@dataclass(frozen=True)
class StateParseResult:
    """Summary of a state parsing run."""

    input_path: Path
    output_path: Path
    state_count: int


def load_ocr_samples(path: Path) -> List[OCRSample]:
    """Load OCR samples from a JSONL file."""

    samples = []
    with path.expanduser().open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            samples.append(
                OCRSample(
                    timestamp_seconds=float(row["timestamp_seconds"]),
                    field_name=str(row["field_name"]),
                    raw_text=str(row.get("raw_text") or ""),
                    video_sha256=row.get("video_sha256"),
                    normalized_text=row.get("normalized_text"),
                    confidence=row.get("confidence"),
                    crop_path=Path(row["crop_path"]) if row.get("crop_path") else None,
                )
            )
    return samples


def group_samples_by_timestamp(samples: Iterable[OCRSample]) -> Dict[float, Dict[str, OCRSample]]:
    """Group OCR samples by timestamp and field name."""

    grouped: Dict[float, Dict[str, OCRSample]] = defaultdict(dict)
    for sample in samples:
        grouped[round(sample.timestamp_seconds, 3)][sample.field_name] = sample
    return dict(grouped)


def parse_count(value: Optional[str]) -> tuple:
    """Parse a SidelineHD count string like 2-1 into balls/strikes."""

    if not value:
        return None, None
    match = re.search(r"\b([0-4])\s*-\s*([0-3])\b", value)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def parse_jersey_number(value: Optional[str]) -> Optional[str]:
    """Parse a jersey number from OCR text."""

    if not value:
        return None
    match = re.search(r"\d+", value)
    if not match:
        return None
    return match.group(0)


def parse_inning(value: Optional[str]) -> tuple:
    """Parse noisy inning OCR into inning number and a weak half-inning guess."""

    if not value:
        return None, None

    text = value.strip()
    match = re.search(r"\d+", text)
    inning = None
    half = None
    if match:
        digits = match.group(0)
        # SidelineHD's up/down inning arrow can OCR as a leading digit fused to
        # the inning number: "4" for top/up and "7" for bottom/down.
        if len(digits) > 1 and digits.startswith("7"):
            inning = _inning_from_digits(digits[1:])
            half = HalfInning.BOTTOM
        elif len(digits) > 1 and digits.startswith("4"):
            inning = _inning_from_digits(digits[1:])
            half = HalfInning.TOP
        else:
            inning = int(digits)
            if inning > 9 and len(digits) > 1:
                non_zero_digits = [digit for digit in digits if digit != "0"]
                inning = min(int(digit) for digit in non_zero_digits) if non_zero_digits else None
        if inning == 0:
            inning = None

    lowered = text.lower()
    if inning is None and lowered in {"0", "00"}:
        half = None
    elif any(token in text for token in ("▲", "△", "^", "↑")) or lowered.startswith("t"):
        half = HalfInning.TOP
    elif lowered.startswith(("o", "0")):
        half = HalfInning.TOP
    elif any(token in text for token in ("▼", "▽", "↓")) or lowered.startswith(("b", "v")):
        half = HalfInning.BOTTOM

    return inning, half


def state_from_samples(timestamp_seconds: float, samples_by_field: Dict[str, OCRSample]) -> OverlayState:
    """Build one OverlayState from OCR samples at a single timestamp."""

    count_text = _sample_text(samples_by_field, "count")
    balls, strikes = parse_count(count_text)
    inning, half = parse_inning(_sample_text(samples_by_field, "inning"))
    batter_number = parse_jersey_number(
        _sample_text(samples_by_field, "batter_card_number")
        or _sample_text(samples_by_field, "batter_number")
    )

    return OverlayState(
        timestamp_seconds=timestamp_seconds,
        inning=inning,
        half=half,
        balls=balls,
        strikes=strikes,
        batter_number=batter_number,
        metadata={
            "batter_name": _sample_text(samples_by_field, "batter_card_name"),
            "fields": {
                field_name: sample.normalized_text or sample.raw_text
                for field_name, sample in sorted(samples_by_field.items())
            },
        },
    )


def parse_states(samples: Iterable[OCRSample]) -> List[OverlayState]:
    """Parse OCR samples into timestamp-sorted overlay states."""

    states = []
    for timestamp_seconds, samples_by_field in sorted(group_samples_by_timestamp(samples).items()):
        states.append(state_from_samples(timestamp_seconds, samples_by_field))
    return smooth_states(states)


def smooth_states(states: List[OverlayState]) -> List[OverlayState]:
    """Fill short OCR gaps from adjacent stable state values."""

    smoothed = []
    next_innings = _next_known_values(states, "inning")
    next_halves = _next_known_values(states, "half")
    previous_inning = None
    previous_half = None

    for index, state in enumerate(states):
        inning = state.inning
        half = state.half

        if inning is None:
            inning = previous_inning if previous_inning is not None else next_innings[index]
        if half is None:
            if (
                inning is not None
                and previous_inning is not None
                and inning > previous_inning
            ):
                half = HalfInning.TOP
            else:
                half = previous_half if previous_half is not None else next_halves[index]

        if inning is not None:
            previous_inning = inning
        if half is not None:
            previous_half = half

        smoothed.append(replace(state, inning=inning, half=half))

    return smoothed


def _next_known_values(states: List[OverlayState], attr_name: str) -> List[object]:
    values = [None] * len(states)
    next_value = None
    for index in range(len(states) - 1, -1, -1):
        current_value = getattr(states[index], attr_name)
        if current_value is not None:
            next_value = current_value
        values[index] = next_value
    return values


def parse_samples_file(samples_path: Path, output_path: Optional[Path] = None) -> StateParseResult:
    """Parse a samples JSONL file and write states JSONL."""

    source = samples_path.expanduser()
    destination = output_path.expanduser() if output_path else source.parent / "states.jsonl"
    states = parse_states(load_ocr_samples(source))
    write_jsonl(destination, states)
    return StateParseResult(input_path=source, output_path=destination, state_count=len(states))


def _sample_text(samples_by_field: Dict[str, OCRSample], field_name: str) -> Optional[str]:
    sample = samples_by_field.get(field_name)
    if sample is None:
        return None
    return sample.normalized_text or sample.raw_text


def _inning_from_digits(value: str) -> Optional[int]:
    non_zero_digits = [digit for digit in value if digit != "0"]
    if not non_zero_digits:
        return None
    return int(non_zero_digits[0])
