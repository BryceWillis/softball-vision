"""Markdown review reports for questionable detected events."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sidelinehd_extractor.events import load_events, load_states
from sidelinehd_extractor.exports import format_timestamp
from sidelinehd_extractor.models import Event, EventType, OCRSample, OverlayState
from sidelinehd_extractor.review import ReviewOptions, ReviewRow, collect_event_review_rows
from sidelinehd_extractor.state import group_samples_by_timestamp, load_ocr_samples


@dataclass(frozen=True)
class ReviewReportResult:
    """Summary of a written Markdown review report."""

    output_path: Path
    flagged_count: int


def write_review_report(
    run_path: Path,
    output_path: Optional[Path] = None,
    kind: str = "all",
    options: Optional[ReviewOptions] = None,
) -> ReviewReportResult:
    """Write a Markdown report for events with review flags."""

    source = run_path.expanduser()
    run_dir = source if source.is_dir() else source.parent
    events_path = run_dir / "events.jsonl" if source.is_dir() else source
    states_path = run_dir / "states.jsonl"
    samples_path = run_dir / "samples.jsonl"
    destination = output_path.expanduser() if output_path else run_dir / "review_report.md"

    events = load_events(events_path)
    states = load_states(states_path) if states_path.exists() else []
    samples = load_ocr_samples(samples_path) if samples_path.exists() else []
    text = render_review_report(
        events=events,
        states=states,
        samples=samples,
        run_path=run_dir,
        kind=kind,
        options=options,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text + ("\n" if text else ""), encoding="utf-8")
    flagged_count = sum(1 for row in collect_event_review_rows(events, kind=kind, options=options) if row.flags)
    return ReviewReportResult(output_path=destination, flagged_count=flagged_count)


def render_review_report(
    events: Iterable[Event],
    states: Iterable[OverlayState] = (),
    samples: Iterable[OCRSample] = (),
    run_path: Optional[Path] = None,
    kind: str = "all",
    options: Optional[ReviewOptions] = None,
) -> str:
    """Render a Markdown report for flagged events."""

    rows = [row for row in collect_event_review_rows(events, kind=kind, options=options) if row.flags]
    state_list = sorted(states, key=lambda item: item.timestamp_seconds)
    sample_groups = group_samples_by_timestamp(samples)

    title = "Review Report"
    lines = [f"# {title}", ""]
    if run_path is not None:
        lines.extend([f"Run: `{run_path}`", ""])
    lines.extend(
        [
            f"Flagged events: {len(rows)}",
            "",
            "Use this file to inspect likely OCR/detection issues. Copy rows from the correction examples into a corrections CSV, then rerun export with `--corrections`.",
            "",
        ]
    )

    if not rows:
        lines.append("No questionable events found.")
        return "\n".join(lines)

    for row in rows:
        event = row.event
        nearest_state = _nearest_state(state_list, event.timestamp_seconds)
        exact_samples = sample_groups.get(round(event.timestamp_seconds, 3), {})

        lines.extend(
            [
                f"## {format_timestamp(event.timestamp_seconds)} {event.label}",
                "",
                f"- Event: `{event.event_type.value}`",
                f"- Flags: `{', '.join(row.flags)}`",
            ]
        )
        if event.inning or event.half:
            half = event.half.value if event.half else "unknown"
            inning = event.inning if event.inning is not None else "unknown"
            lines.append(f"- Inning: `{half} {inning}`")
        if event.player_name or event.player_number:
            lines.append(f"- Player: `{event.player_name or ''} #{event.player_number or ''}`")
        lines.append("")

        if nearest_state is not None:
            lines.extend(_render_state_context(nearest_state, event.timestamp_seconds))
        if exact_samples:
            lines.extend(_render_ocr_samples(exact_samples))
        else:
            lines.extend(["### Raw OCR", "", "No exact OCR samples found for this event timestamp.", ""])

        lines.extend(_render_correction_examples(event))

    return "\n".join(lines).rstrip()


def _nearest_state(states: List[OverlayState], timestamp_seconds: float) -> Optional[OverlayState]:
    if not states:
        return None
    return min(states, key=lambda state: abs(state.timestamp_seconds - timestamp_seconds))


def _render_state_context(state: OverlayState, event_timestamp_seconds: float) -> List[str]:
    delta = state.timestamp_seconds - event_timestamp_seconds
    half = state.half.value if state.half else ""
    fields = state.metadata.get("fields") or {}
    lines = [
        "### Parsed State",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| timestamp | `{format_timestamp(state.timestamp_seconds)}` ({delta:+.1f}s) |",
        f"| inning | `{half} {state.inning or ''}` |",
        f"| count | `{_format_count(state)}` |",
        f"| batter_number | `{state.batter_number or ''}` |",
        f"| batter_name | `{state.metadata.get('batter_name') or ''}` |",
    ]
    for field_name, value in sorted(fields.items()):
        lines.append(f"| OCR `{field_name}` | `{_markdown_cell(str(value))}` |")
    lines.append("")
    return lines


def _render_ocr_samples(samples_by_field: Dict[str, OCRSample]) -> List[str]:
    lines = [
        "### Raw OCR",
        "",
        "| Field | Raw | Normalized | Crop |",
        "| --- | --- | --- | --- |",
    ]
    for field_name, sample in sorted(samples_by_field.items()):
        crop = str(sample.crop_path) if sample.crop_path else ""
        lines.append(
            "| "
            f"`{field_name}` | "
            f"`{_markdown_cell(sample.raw_text.strip())}` | "
            f"`{_markdown_cell((sample.normalized_text or '').strip())}` | "
            f"`{_markdown_cell(crop)}` |"
        )
    lines.append("")
    return lines


def _render_correction_examples(event: Event) -> List[str]:
    rows = [
        {
            "event_type": event.event_type.value,
            "timestamp": format_timestamp(event.timestamp_seconds),
            "field": "delete",
            "value": "true",
            "match_window_seconds": "1",
            "reason": "Remove false positive event",
        }
    ]
    if event.event_type == EventType.AT_BAT_START:
        rows.extend(
            [
                {
                    "event_type": event.event_type.value,
                    "timestamp": format_timestamp(event.timestamp_seconds),
                    "field": "label",
                    "value": event.label,
                    "match_window_seconds": "1",
                    "reason": "Edit exported at-bat label",
                },
                {
                    "event_type": event.event_type.value,
                    "timestamp": format_timestamp(event.timestamp_seconds),
                    "field": "player_number",
                    "value": event.player_number or "",
                    "match_window_seconds": "1",
                    "reason": "Edit structured player number",
                },
                {
                    "event_type": event.event_type.value,
                    "timestamp": format_timestamp(event.timestamp_seconds),
                    "field": "player_name",
                    "value": event.player_name or "",
                    "match_window_seconds": "1",
                    "reason": "Edit structured player name",
                },
            ]
        )

    return [
        "### Correction Examples",
        "",
        "```csv",
        _csv_text(rows).rstrip(),
        "```",
        "",
    ]


def _csv_text(rows: List[dict]) -> str:
    if not rows:
        return ""
    output = io.StringIO()
    fieldnames = ["event_type", "timestamp", "field", "value", "match_window_seconds", "reason"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _format_count(state: OverlayState) -> str:
    if state.balls is None or state.strikes is None:
        return ""
    return f"{state.balls}-{state.strikes}"


def _markdown_cell(value: str) -> str:
    return value.replace("\n", "\\n").replace("|", "\\|")
