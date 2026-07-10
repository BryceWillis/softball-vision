"""Pre-run overlay template probe (item 55).

Before the full (multi-minute) OCR pass, sample a handful of frames, OCR only
the key scorebug regions under each candidate template, and score how many
reads parse as valid field values. With multiple candidates this auto-selects
the layout; with today's single packaged candidate it is a fail-fast guard — a
low score warns that the overlay probably doesn't match *before* ~40 minutes
of OCR are spent (item 54 P2 only catches it afterwards).

Scoring de-weights ``inning`` and ``batter_card_name`` (architect validation,
Pass 23): on a real 640x360 stream the ``inning`` region misreads even under
the correct template, so it must never gate selection or the low-score floor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sidelinehd_extractor.crops import crop_frame, normalize_frame_to_template
from sidelinehd_extractor.models import OverlayTemplate
from sidelinehd_extractor.ocr import OCRCallable
from sidelinehd_extractor.state import parse_count, parse_inning, parse_score
from sidelinehd_extractor.video import probe_video, read_frames_at

#: Fields that decide the score. The three primary fields read reliably when
#: the template matches (148-181 non-empty reads over a real 2.4h run).
PRIMARY_PROBE_FIELDS = ("left_score", "right_score", "count")
#: Low-weight tie-breakers only — unreliable even under the right template.
SECONDARY_PROBE_FIELDS = ("inning", "batter_card_name")
SECONDARY_FIELD_WEIGHT = 0.25

#: Probe positions across the first third of the video; 0:00 is skipped
#: because pregame dead air rarely shows the overlay.
PROBE_DURATION_FRACTIONS = (0.10, 0.15, 0.20, 0.25, 0.30)
#: Below this duration, percentage spacing collapses into near-identical
#: frames; use fixed 30s steps instead.
SHORT_VIDEO_SECONDS = 600.0
SHORT_VIDEO_STEP_SECONDS = 30.0

#: Minimum weighted valid-read rate for a candidate to be trusted.
LOW_SCORE_FLOOR = 0.25

_MAX_PLAUSIBLE_SCORE = 30
_NAME_ALPHA_PATTERN = re.compile(r"[A-Za-z].*[A-Za-z]")


@dataclass(frozen=True)
class TemplateProbeResult:
    """Outcome of a probe pass: the chosen template plus the evidence."""

    template: OverlayTemplate
    scores: Dict[str, float]
    low_score: bool
    probe_timestamps: Tuple[float, ...]
    frames_probed: int

    def to_manifest(self) -> dict:
        return {
            "selected": self.template.name,
            "scores": {name: round(score, 4) for name, score in self.scores.items()},
            "low_score": self.low_score,
            "floor": LOW_SCORE_FLOOR,
            "probe_timestamps": list(self.probe_timestamps),
            "frames_probed": self.frames_probed,
        }


def probe_timestamps_for_duration(duration_seconds: Optional[float]) -> Tuple[float, ...]:
    """Timestamps to probe, spread over the first third of the video."""

    if not duration_seconds or duration_seconds <= 0:
        # Unknown duration: fixed early offsets; unreadable ones are skipped.
        return (30.0, 60.0, 90.0, 120.0, 150.0)
    if duration_seconds < SHORT_VIDEO_SECONDS:
        count = len(PROBE_DURATION_FRACTIONS)
        stamps = [
            SHORT_VIDEO_STEP_SECONDS * (index + 1)
            for index in range(count)
            if SHORT_VIDEO_STEP_SECONDS * (index + 1) < duration_seconds
        ]
        return tuple(stamps) or (duration_seconds / 2,)
    return tuple(duration_seconds * fraction for fraction in PROBE_DURATION_FRACTIONS)


def field_read_is_valid(field_name: str, text: str) -> bool:
    """Whether one OCR read parses as a plausible value for the field.

    Reuses the run pipeline's own normalizers so "valid" here means exactly
    what the state parser would accept.
    """

    if not text:
        return False
    if field_name in ("left_score", "right_score"):
        score = parse_score(text)
        return score is not None and 0 <= score <= _MAX_PLAUSIBLE_SCORE
    if field_name == "count":
        balls, strikes = parse_count(text)
        return balls is not None and strikes is not None
    if field_name == "inning":
        inning, _half = parse_inning(text)
        return inning is not None and 1 <= inning <= 20
    if field_name == "batter_card_name":
        return _NAME_ALPHA_PATTERN.search(text) is not None
    return bool(text.strip())


def _probe_fields(template: OverlayTemplate) -> List[Tuple[str, float]]:
    """(field, weight) pairs to OCR for one candidate — only regions it has."""

    fields = [
        (name, 1.0) for name in PRIMARY_PROBE_FIELDS if name in template.regions
    ]
    fields.extend(
        (name, SECONDARY_FIELD_WEIGHT)
        for name in SECONDARY_PROBE_FIELDS
        if name in template.regions
    )
    return fields


def score_template(
    template: OverlayTemplate, frames: Sequence[Tuple[float, object]], ocr: OCRCallable
) -> float:
    """Weighted fraction of (frame x field) reads that parse as valid."""

    fields = _probe_fields(template)
    if not fields or not frames:
        return 0.0
    total_weight = 0.0
    valid_weight = 0.0
    for _timestamp, frame in frames:
        frame = normalize_frame_to_template(frame, template)
        for field_name, weight in fields:
            total_weight += weight
            crop = crop_frame(frame, template.regions[field_name])
            try:
                result = ocr(crop, field_name)
            except Exception:  # noqa: BLE001 - a failed read scores as invalid
                continue
            text = result.normalized_text or result.text
            if field_read_is_valid(field_name, text):
                valid_weight += weight
    if total_weight == 0.0:
        return 0.0
    return valid_weight / total_weight


def probe_template(
    video_path: Path,
    candidates: Iterable[OverlayTemplate],
    ocr: OCRCallable,
    probe_timestamps: Optional[Sequence[float]] = None,
    duration_seconds: Optional[float] = None,
) -> TemplateProbeResult:
    """Score each candidate on a few sampled frames and pick the best.

    ``candidates[0]`` is treated as the packaged default: ties (and an
    all-below-floor result) resolve to it. Writes no run-dir artifacts. Frames
    that cannot be read (e.g. timestamps past a short video's end) are
    skipped; if no frame is readable the default wins with score 0 and the
    low-score flag set.
    """

    candidate_list = list(candidates)
    if not candidate_list:
        raise ValueError("probe_template requires at least one candidate template")

    if probe_timestamps is None:
        if duration_seconds is None:
            duration_seconds = probe_video(video_path).duration_seconds
        probe_timestamps = probe_timestamps_for_duration(duration_seconds)

    frames: List[Tuple[float, object]] = []
    for timestamp in probe_timestamps:
        try:
            frames.extend(read_frames_at(video_path, [timestamp]))
        except ValueError:
            continue  # unreadable timestamp — probe with the frames we have

    scores: Dict[str, float] = {}
    best = candidate_list[0]
    best_score = -1.0
    for candidate in candidate_list:
        score = score_template(candidate, frames, ocr)
        scores[candidate.name] = score
        # Strictly-greater keeps ties on the earlier candidate — the default.
        if score > best_score:
            best = candidate
            best_score = score

    low_score = best_score < LOW_SCORE_FLOOR
    if low_score:
        best = candidate_list[0]
    return TemplateProbeResult(
        template=best,
        scores=scores,
        low_score=low_score,
        probe_timestamps=tuple(probe_timestamps),
        frames_probed=len(frames),
    )
