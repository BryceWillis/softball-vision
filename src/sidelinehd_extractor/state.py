"""Parse OCR samples into structured overlay state rows."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sidelinehd_extractor.constants import (
    BATTER_SOURCE_BATTER_CARD,
    BATTER_SOURCE_LINEUP_NUMBER,
    BATTER_SOURCE_LINEUP_STRIP,
    INNING_ARROW_DOWN,
    INNING_ARROW_UP,
    LINEUP_STRIP_CONFIDENCE_KEY,
    MAX_PLAUSIBLE_SCORE,
)
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
                    source_detail=row.get("source_detail"),
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


def parse_score(value: Optional[str]) -> Optional[int]:
    """Parse a score digit from OCR text.

    Implausible reads (3+ digits or above ``MAX_PLAUSIBLE_SCORE``) are OCR
    noise — e.g. a scorebug glyph fused onto the real score ("164" for 16) —
    and are treated as missing rather than as values (item 60).
    """

    if not value:
        return None
    match = re.search(r"\d+", value)
    if not match:
        return None
    digits = match.group(0)
    score = int(digits)
    if len(digits) > 2 or score > MAX_PLAUSIBLE_SCORE:
        return None
    return score


def _normalize_game_status(value: Optional[str]) -> Optional[str]:
    """Normalize recognized scorebug status labels."""

    if not value:
        return None
    lowered = value.lower()
    if "final" in lowered:
        return "final"
    tokens = re.findall(r"[a-z]+", lowered)
    game_indexes = [
        index
        for index, token in enumerate(tokens)
        if token.startswith(("gam", "qam", "oam"))
    ]
    soon_tokens = {"soon", "boon", "book", "oon", "oom", "eom"}
    # Interim OCR heuristic: keep this conservative and token-adjacent. The
    # durable version belongs with item 40's confidence/fuzzy matching work.
    if any(
        candidate in soon_tokens
        for index in game_indexes
        for candidate in tokens[index + 1 : index + 4]
    ):
        return "pregame"
    return None


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


def state_from_samples(
    timestamp_seconds: float, samples_by_field: Dict[str, OCRSample]
) -> OverlayState:
    """Build one OverlayState from OCR samples at a single timestamp."""

    count_text = _sample_text(samples_by_field, "count")
    balls, strikes = parse_count(count_text)
    game_status = _normalize_game_status(_sample_text(samples_by_field, "game_status"))
    inning, half = parse_inning(_confident_sample_text(samples_by_field, "inning"))
    arrow_half = _inning_arrow_half(samples_by_field.get("inning"))
    if arrow_half is not None and inning is not None:
        # The pixel-detected arrow direction beats any text-derived guess —
        # but only alongside a real inning read; the pregame overlay's green
        # text triggers arrow detections with no inning on screen.
        half = arrow_half
    away_score = parse_score(_confident_sample_text(samples_by_field, "left_score"))
    home_score = parse_score(_confident_sample_text(samples_by_field, "right_score"))
    if game_status == "pregame":
        # The pregame scorebug shows no game state; anything OCR'd from it
        # (countdown fragments, status-text artifacts) is noise that would
        # otherwise smooth/confirm into phantom innings and chapters.
        inning = None
        half = None
        away_score = None
        home_score = None
    batter_card_text = _sample_text(samples_by_field, "batter_card_number")
    lineup_strip_sample = samples_by_field.get("lineup_strip")
    lineup_strip_confidence = (
        lineup_strip_sample.source_detail if lineup_strip_sample else None
    )
    lineup_strip_text = _sample_text(samples_by_field, "lineup_strip")
    lineup_text = _sample_text(samples_by_field, "batter_number")
    batter_card_number = parse_jersey_number(batter_card_text)
    lineup_strip_number = parse_jersey_number(lineup_strip_text)
    lineup_number = parse_jersey_number(lineup_text)
    active_lineup_number = lineup_strip_number or lineup_number

    if batter_card_number:
        batter_number = batter_card_number
        batter_number_source = BATTER_SOURCE_BATTER_CARD
    elif lineup_strip_number:
        batter_number = lineup_strip_number
        batter_number_source = BATTER_SOURCE_LINEUP_STRIP
    elif lineup_number:
        batter_number = lineup_number
        batter_number_source = BATTER_SOURCE_LINEUP_NUMBER
    else:
        batter_number = None
        batter_number_source = None

    batter_number_disagreement = None
    if batter_card_number and active_lineup_number and batter_card_number != active_lineup_number:
        batter_number_disagreement = (
            f"batter_card={batter_card_number} lineup={active_lineup_number}"
        )

    return OverlayState(
        timestamp_seconds=timestamp_seconds,
        inning=inning,
        half=half,
        balls=balls,
        strikes=strikes,
        away_score=away_score,
        home_score=home_score,
        batter_number=batter_number,
        metadata={
            "batter_name": _sample_text(samples_by_field, "batter_card_name"),
            "batter_number_source": batter_number_source,
            "batter_number_disagreement": batter_number_disagreement,
            "lineup_strip_number": lineup_strip_number,
            "lineup_batter_number": lineup_number,
            "game_status": game_status,
            LINEUP_STRIP_CONFIDENCE_KEY: lineup_strip_confidence,
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
    away_scores = _smooth_score_sequence([state.away_score for state in states])
    home_scores = _smooth_score_sequence([state.home_score for state in states])

    for index, state in enumerate(states):
        inning = state.inning
        half = state.half
        previous_inning = _nearby_known_value(states, index, "inning", -1)
        next_inning = _nearby_known_value(states, index, "inning", 1)
        previous_half = _nearby_known_value(states, index, "half", -1)
        next_half = _nearby_known_value(states, index, "half", 1)

        if inning is None:
            inning = previous_inning if previous_inning is not None else next_inning
        if half is None:
            if inning is not None and previous_inning is not None and inning > previous_inning:
                half = HalfInning.TOP
            else:
                half = previous_half if previous_half is not None else next_half

        smoothed.append(
            replace(
                state,
                inning=inning,
                half=half,
                away_score=away_scores[index],
                home_score=home_scores[index],
            )
        )

    return smoothed


# Scores are cumulative, so a read below the established score is OCR noise
# (measured: a stray leading-digit-dropped "2" landing on the exact half
# boundary turned a 12-7 chapter into 2-7) unless the scoreboard operator
# corrected a miskeyed score, which persists — hence the consecutive-read
# confirmation. Large forward jumps get a shorter confirmation: a legitimate
# multi-run rally read after an OCR gap persists, a corrupted read does not.
_SCORE_DECREASE_CONFIRMATIONS = 3
_SCORE_JUMP_CONFIRMATIONS = 2
_SCORE_MAX_UNCONFIRMED_JUMP = 4


def _smooth_score_sequence(values: List[Optional[int]]) -> List[Optional[int]]:
    """Reject non-monotonic score reads unless consecutive reads confirm them.

    ``None`` gaps stay ``None`` — this guard never invents a score, it only
    suppresses contradictions: an unconfirmed decrease (or implausibly large
    increase) is replaced with the established score.
    """

    result = list(values)
    established: Optional[int] = None
    for index, value in enumerate(values):
        if value is None:
            continue
        if established is None or value == established:
            established = value
            continue
        if value < established:
            if _confirmed_by_consecutive_reads(values, index, _SCORE_DECREASE_CONFIRMATIONS):
                established = value
            else:
                result[index] = established
        elif value - established > _SCORE_MAX_UNCONFIRMED_JUMP:
            if _confirmed_by_consecutive_reads(values, index, _SCORE_JUMP_CONFIRMATIONS):
                established = value
            else:
                result[index] = established
        else:
            established = value
    return result


def _confirmed_by_consecutive_reads(
    values: List[Optional[int]], index: int, required: int
) -> bool:
    """Whether the next non-``None`` reads repeat ``values[index]`` ``required`` times."""

    target = values[index]
    seen = 1
    for value in values[index + 1 :]:
        if value is None:
            continue
        if value != target:
            return False
        seen += 1
        if seen >= required:
            return True
    return seen >= required


def _nearby_known_value(
    states: List[OverlayState],
    index: int,
    attr_name: str,
    direction: int,
) -> object:
    timestamp_seconds = states[index].timestamp_seconds
    cursor = index + direction
    while 0 <= cursor < len(states):
        candidate = states[cursor]
        gap_seconds = abs(candidate.timestamp_seconds - timestamp_seconds)
        if gap_seconds > _MAX_STATE_SMOOTH_GAP_SECONDS:
            return None
        value = getattr(candidate, attr_name)
        if value is not None:
            return value
        cursor += direction
    return None


def parse_samples_file(samples_path: Path, output_path: Optional[Path] = None) -> StateParseResult:
    """Parse a samples JSONL file and write states JSONL."""

    source = samples_path.expanduser()
    destination = output_path.expanduser() if output_path else source.parent / "states.jsonl"
    states = parse_states(load_ocr_samples(source))
    write_jsonl(destination, states)
    return StateParseResult(input_path=source, output_path=destination, state_count=len(states))


def _inning_arrow_half(sample: Optional[OCRSample]) -> Optional[HalfInning]:
    """Map the inning sample's pixel-detected arrow direction to a half."""

    if sample is None:
        return None
    if sample.source_detail == INNING_ARROW_UP:
        return HalfInning.TOP
    if sample.source_detail == INNING_ARROW_DOWN:
        return HalfInning.BOTTOM
    return None


def _sample_text(samples_by_field: Dict[str, OCRSample], field_name: str) -> Optional[str]:
    sample = samples_by_field.get(field_name)
    if sample is None:
        return None
    return sample.normalized_text or sample.raw_text


# Item 40 confidence floor for the scorebug numeric cluster. Measured on real
# footage: genuine digit reads score 0.75-0.96 while noise artifacts (e.g. a
# pregame speck reading "7" at 0.007) sit near zero, and one such read can
# smooth into a phantom inning across the whole pregame span.
_MIN_SCOREBUG_READ_CONFIDENCE = 0.5
_MAX_STATE_SMOOTH_GAP_SECONDS = 15.0


def _confident_sample_text(
    samples_by_field: Dict[str, OCRSample], field_name: str
) -> Optional[str]:
    """Like ``_sample_text`` but drops low-confidence scorebug reads.

    A missing confidence (backends that do not report one) is accepted.
    """

    sample = samples_by_field.get(field_name)
    if sample is None:
        return None
    if sample.confidence is not None and sample.confidence < _MIN_SCOREBUG_READ_CONFIDENCE:
        return None
    return sample.normalized_text or sample.raw_text


def _inning_from_digits(value: str) -> Optional[int]:
    non_zero_digits = [digit for digit in value if digit != "0"]
    if not non_zero_digits:
        return None
    return int(non_zero_digits[0])
