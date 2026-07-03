"""Sanitized Markdown feedback logs for completed runs."""

from __future__ import annotations

import json
import platform
import re
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from sidelinehd_extractor.events import load_events, load_states
from sidelinehd_extractor.exports import format_timestamp
from sidelinehd_extractor.models import Event, OCRSample, Roster, RosterPlayer
from sidelinehd_extractor.review import collect_event_review_rows
from sidelinehd_extractor.state import group_samples_by_timestamp, load_ocr_samples


@dataclass(frozen=True)
class FeedbackLogResult:
    """Summary of a written feedback log."""

    output_path: Path


@dataclass(frozen=True)
class FeedbackLog:
    """Sanitized feedback payload ready to render."""

    environment: Dict[str, Any]
    run_warnings: List[dict]
    review_flags: List[dict]
    event_sequence: List[dict]
    note: Optional[str] = None


@dataclass(frozen=True)
class RunFeedbackData:
    """Completed run artifacts used to produce a feedback log."""

    run_dir: Path
    manifest: Dict[str, Any]
    events: List[Event]
    samples: List[OCRSample]
    roster: Optional[Roster] = None
    note: Optional[str] = None


@dataclass
class NameSanitizer:
    """Stable per-log player/team pseudonymizer."""

    replacements: Dict[str, str] = field(default_factory=dict)
    team_replacements: Dict[str, str] = field(default_factory=dict)
    _next_player_index: int = 0

    def add_player_variants(self, variants: Iterable[Optional[str]]) -> None:
        cleaned = [variant.strip() for variant in variants if variant and variant.strip()]
        if not cleaned:
            return
        pseudonym = None
        for variant in cleaned:
            existing = self.replacements.get(_normalize_replacement_key(variant))
            if existing:
                pseudonym = existing
                break
        if pseudonym is None:
            pseudonym = _player_label(self._next_player_index)
            self._next_player_index += 1
        for variant in cleaned:
            self._add_player_replacement(variant, pseudonym)
            for token in _name_tokens(variant):
                self._add_player_replacement(token, pseudonym)

    def add_team(self, value: Optional[str], pseudonym: str = "Team") -> None:
        if not value or not value.strip():
            return
        self.team_replacements[_normalize_replacement_key(value)] = pseudonym

    def sanitize_text(self, value: Optional[str]) -> str:
        text = "" if value is None else str(value)
        text = _apply_replacements(text, self.replacements)
        text = _apply_replacements(text, self.team_replacements)
        return text

    def sanitize_value(self, value: Any, key: Optional[str] = None) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            if key and "team" in key.lower():
                return _team_pseudonym_for_key(key)
            return self.sanitize_text(value)
        if isinstance(value, dict):
            sanitized = {}
            for child_key, child_value in sorted(value.items()):
                if _is_dropped_key(str(child_key)):
                    continue
                sanitized[child_key] = self.sanitize_value(child_value, key=str(child_key))
            return sanitized
        if isinstance(value, list):
            return [self.sanitize_value(item, key=key) for item in value]
        return value

    def _add_player_replacement(self, value: str, pseudonym: str) -> None:
        self.replacements.setdefault(_normalize_replacement_key(value), pseudonym)


def write_feedback_log(
    run_path: Path,
    output_path: Optional[Path] = None,
    note: Optional[str] = None,
) -> FeedbackLogResult:
    """Write a sanitized Markdown feedback log for a completed run."""

    data = load_feedback_data(run_path, note=note)
    sanitizer = build_name_sanitizer(data)
    log = sanitize_feedback(data, sanitizer)
    text = render_feedback_log(log)
    destination = output_path.expanduser() if output_path else data.run_dir / "feedback.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text + "\n", encoding="utf-8")
    return FeedbackLogResult(output_path=destination)


def load_feedback_data(run_path: Path, note: Optional[str] = None) -> RunFeedbackData:
    """Load completed run artifacts for feedback rendering."""

    run_dir = run_path.expanduser()
    if not run_dir.is_dir():
        raise ValueError("feedback requires a run directory")
    manifest_path = run_dir / "manifest.json"
    events_path = run_dir / "events.jsonl"
    samples_path = run_dir / "samples.jsonl"
    states_path = run_dir / "states.jsonl"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    if not events_path.exists():
        raise FileNotFoundError(events_path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    events = load_events(events_path)
    samples = load_ocr_samples(samples_path) if samples_path.exists() else []
    # Loading states validates the standard artifact is readable, and gives future
    # feedback fields a single place to extend from without changing the CLI.
    if states_path.exists():
        load_states(states_path)
    roster = _roster_from_manifest(manifest)
    return RunFeedbackData(
        run_dir=run_dir,
        manifest=manifest,
        events=events,
        samples=samples,
        roster=roster,
        note=note,
    )


def sanitize_feedback(data: RunFeedbackData, sanitizer: NameSanitizer) -> FeedbackLog:
    """Return a sanitized feedback payload.

    This is the privacy boundary: callers should render only the returned object.
    """

    sample_groups = group_samples_by_timestamp(data.samples)
    review_rows = [
        row
        for row in collect_event_review_rows(data.events, roster=data.roster)
        if row.flags
    ]
    review_flags = []
    for row in review_rows:
        event = row.event
        samples = sample_groups.get(round(event.timestamp_seconds, 3), {})
        review_flags.append(
            {
                "timestamp": format_timestamp(event.timestamp_seconds),
                "event_type": event.event_type.value,
                "label": sanitizer.sanitize_text(event.label),
                "player_number": event.player_number,
                "flags": [sanitizer.sanitize_text(flag) for flag in row.flags],
                "metadata": sanitizer.sanitize_value(event.metadata),
                "ocr_samples": [
                    {
                        "field": field_name,
                        "raw": sanitizer.sanitize_text(sample.raw_text.strip()),
                        "normalized": sanitizer.sanitize_text(
                            (sample.normalized_text or "").strip()
                        ),
                        "confidence": sample.confidence,
                    }
                    for field_name, sample in sorted(samples.items())
                ],
            }
        )

    event_sequence = [
        {
            "timestamp": format_timestamp(event.timestamp_seconds),
            "event_type": event.event_type.value,
            "label": sanitizer.sanitize_text(event.label),
            "inning": event.inning,
            "half": event.half.value if event.half else None,
            "player_number": event.player_number,
            "player_name": sanitizer.sanitize_text(event.player_name),
        }
        for event in data.events
    ]

    return FeedbackLog(
        environment=_feedback_environment(data.manifest),
        run_warnings=[
            sanitizer.sanitize_value(warning)
            for warning in data.manifest.get("warnings", [])
            if isinstance(warning, dict)
        ],
        review_flags=review_flags,
        event_sequence=event_sequence,
        note=data.note,
    )


def render_feedback_log(log: FeedbackLog) -> str:
    """Render a sanitized feedback payload as Markdown."""

    lines = [
        "# SidelineHD Extractor Feedback",
        "",
        "## Environment",
        "",
        "```json",
        json.dumps(log.environment, indent=2, sort_keys=True),
        "```",
        "",
    ]
    if log.note:
        lines.extend(["## User Note", "", log.note, ""])
    if log.run_warnings:
        lines.extend(
            [
                "## Run Warnings",
                "",
                "```json",
                json.dumps(log.run_warnings, indent=2, sort_keys=True),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Review Flags",
            "",
            "```json",
            json.dumps(log.review_flags, indent=2, sort_keys=True),
            "```",
            "",
            "## Event Sequence",
            "",
            "```json",
            json.dumps(log.event_sequence, indent=2, sort_keys=True),
            "```",
        ]
    )
    return "\n".join(lines).rstrip()


def build_name_sanitizer(data: RunFeedbackData) -> NameSanitizer:
    sanitizer = NameSanitizer()
    if data.roster is not None:
        sanitizer.add_team(data.roster.team_name)
        for player in data.roster.players:
            sanitizer.add_player_variants(
                [
                    player.full_name,
                    player.preferred_name,
                    player.display_name,
                    *player.aliases,
                ]
            )
    for event in data.events:
        sanitizer.add_player_variants([event.player_name])
        for key, value in event.metadata.items():
            if "name" in str(key).lower():
                sanitizer.add_player_variants([str(value)])
    for sample in data.samples:
        if "name" in sample.field_name:
            sanitizer.add_player_variants([sample.raw_text, sample.normalized_text])
    return sanitizer


def _feedback_environment(manifest: Dict[str, Any]) -> Dict[str, Any]:
    template = manifest.get("template") if isinstance(manifest.get("template"), dict) else {}
    environment = {
        "tool_version": _tool_version(),
        "platform": platform.platform(),
        "tesseract_version": manifest.get("tesseract_version"),
        "ocr_backend": manifest.get("ocr_backend"),
        "ocr_workers": manifest.get("ocr_workers"),
        "template_name": template.get("name"),
        "fields": manifest.get("fields"),
        "sample_every_seconds": manifest.get("sample_every_seconds"),
        "start_seconds": manifest.get("start_seconds"),
        "end_seconds": manifest.get("end_seconds"),
        "detection": manifest.get("detection") if isinstance(manifest.get("detection"), dict) else {},
    }
    return {key: value for key, value in environment.items() if value is not None}


def _roster_from_manifest(manifest: Dict[str, Any]) -> Optional[Roster]:
    value = manifest.get("roster")
    if not isinstance(value, dict):
        return None
    players = []
    for player in value.get("players") or []:
        if not isinstance(player, dict) or not player.get("number") or not player.get("full_name"):
            continue
        players.append(
            RosterPlayer(
                number=str(player["number"]),
                full_name=str(player["full_name"]),
                preferred_name=player.get("preferred_name"),
                display_name=player.get("display_name"),
                aliases=list(player.get("aliases") or []),
            )
        )
    return Roster(team_name=str(value.get("team_name") or "Team"), players=players)


def _tool_version() -> str:
    try:
        return metadata.version("sidelinehd-extractor")
    except metadata.PackageNotFoundError:
        return "unknown"


def _player_label(index: int) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    label = ""
    current = index
    while True:
        label = alphabet[current % len(alphabet)] + label
        current = current // len(alphabet) - 1
        if current < 0:
            break
    return f"Player {label}"


def _name_tokens(value: str) -> List[str]:
    return [token for token in re.findall(r"[A-Za-z]+", value) if len(token) >= 3]


def _normalize_replacement_key(value: str) -> str:
    return " ".join(value.lower().split())


def _apply_replacements(text: str, replacements: Dict[str, str]) -> str:
    result = text
    for source, pseudonym in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(source)}(?![A-Za-z0-9])",
            flags=re.IGNORECASE,
        )
        result = pattern.sub(pseudonym, result)
    return result


def _is_dropped_key(key: str) -> bool:
    lowered = key.lower()
    return "url" in lowered or lowered in {"video_id", "youtube_id", "crop_path"}


def _team_pseudonym_for_key(key: str) -> str:
    lowered = key.lower()
    if "left" in lowered or "away" in lowered:
        return "Away Team"
    if "right" in lowered or "home" in lowered:
        return "Home Team"
    return "Team"
