"""End-to-end local game processing workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

import json

from sidelinehd_extractor.corrections import EventCorrection, apply_event_corrections
from sidelinehd_extractor.events import (
    BattingHalfInference,
    DetectionConfig,
    detect_events_file,
    filter_at_bats_to_half,
    infer_batting_half,
    load_events,
    validate_batting_order,
)
from sidelinehd_extractor.exports import export_at_bat_comment, export_youtube_chapters
from sidelinehd_extractor.models import OverlayTemplate, Roster
from sidelinehd_extractor.naming import game_slug_for_run
from sidelinehd_extractor.ocr import OCRCallable, no_ocr
from sidelinehd_extractor.processing import (
    SamplingOptions,
    process_video,
    update_manifest_section,
    write_jsonl,
)
from sidelinehd_extractor.review_report import write_review_report
from sidelinehd_extractor.state import parse_samples_file
from sidelinehd_extractor.template_probe import probe_template
from sidelinehd_extractor.config import candidate_overlay_templates
from sidelinehd_extractor.youtube import (
    DownloadOptions,
    DownloadResult,
    download_youtube_video,
    extract_video_id,
)


@dataclass(frozen=True)
class ExportOptions:
    """Formatting options the text exports were produced with.

    Persisted into the run manifest so re-exports (e.g. the web corrections UI)
    reproduce the run's original formatting exactly.
    """

    include_chapter_intro: bool = True
    chapter_intro_label: str = "Pregame"
    include_inning_score: bool = True
    include_at_bat_inning_headers: bool = True

    def to_manifest(self) -> dict:
        return {
            "include_chapter_intro": self.include_chapter_intro,
            "chapter_intro_label": self.chapter_intro_label,
            "include_inning_score": self.include_inning_score,
            "include_at_bat_inning_headers": self.include_at_bat_inning_headers,
        }


@dataclass(frozen=True)
class RunGameResult:
    """Summary of an end-to-end game processing run."""

    run_dir: Path
    manifest_path: Path
    samples_path: Path
    states_path: Path
    events_path: Path
    chapters_path: Path
    at_bats_path: Path
    sample_count: int
    state_count: int
    event_count: int
    batting_half_inference: Optional[BattingHalfInference] = None
    health_warning: Optional[str] = None


#: The scorebug fields whose reads prove the template actually matched the
#: overlay. If every one of them came back empty for the whole run, OCR was
#: reading the wrong pixels regardless of how many samples were taken.
KEY_SCOREBUG_FIELDS = ("left_score", "right_score", "count", "inning")

NO_SCOREBOARD_WARNING = (
    "No scoreboard detected — the template may not match this video's overlay. "
    "The run finished but produced no usable scoreboard reads, so the chapter "
    "and at-bat exports are empty or unreliable. Check that the video shows the "
    "SidelineHD overlay and that the overlay template matches its layout."
)

TEMPLATE_LOW_SCORE_WARNING = (
    "The scoreboard overlay in this video did not match the known layout well "
    "in a quick pre-check, so the results may come out empty or unreliable. "
    "The run is continuing with the standard layout — check that the video "
    "shows the SidelineHD scoreboard overlay."
)


def scoreboard_health_warning(
    event_count: int,
    field_read_stats: dict,
) -> Optional[str]:
    """Post-run health check: a warning string when the run read no scoreboard.

    Fires when the run produced zero events, or when every key scorebug field
    (``KEY_SCOREBUG_FIELDS``) read empty across the whole run — a field missing
    from the stats counts as empty. Item 54 P2: a run must never report "done"
    with silently useless output.
    """

    if event_count == 0:
        return NO_SCOREBOARD_WARNING
    all_key_fields_empty = all(
        (field_read_stats.get(field_name) or {}).get("non_empty_count", 0) == 0
        for field_name in KEY_SCOREBUG_FIELDS
    )
    if all_key_fields_empty:
        return NO_SCOREBOARD_WARNING
    return None


@dataclass(frozen=True)
class RunYoutubeGameResult:
    """Summary of a download-plus-process run."""

    download: DownloadResult
    run: RunGameResult


def run_game(
    video_path: Path,
    output_dir: Path,
    template: Optional[OverlayTemplate] = None,
    roster: Optional[Roster] = None,
    ocr: OCRCallable = no_ocr,
    progress: Optional[Callable[[int, int, float, int, int], None]] = None,
    output_prefix: Optional[Path] = None,
    corrections: Optional[Iterable[EventCorrection]] = None,
    stage_progress: Optional[Callable[[str], None]] = None,
    sampling: SamplingOptions = SamplingOptions(),
    export_options: ExportOptions = ExportOptions(),
    detection: DetectionConfig = DetectionConfig(),
    batting_half_inference_progress: Optional[Callable[[BattingHalfInference], None]] = None,
    generate_review_report: bool = True,
    auto_detect_template: bool = True,
) -> RunGameResult:
    """Process video, detect events, and write both YouTube text exports."""

    # Item 55: with no explicit template, probe a few frames before the long
    # OCR pass — today a fail-fast guard against a mismatched overlay (warns
    # up front instead of after ~40 wasted minutes), and the selection hook
    # for item 26's additional layouts. Never blocks or fails the run.
    template_probe_result = None
    if template is None and auto_detect_template and ocr is not no_ocr:
        _stage(stage_progress, "probe")
        try:
            template_probe_result = probe_template(
                video_path, candidate_overlay_templates(), ocr
            )
        except Exception as exc:  # noqa: BLE001 - probe must never kill a run
            _stage(stage_progress, f"warning template-probe-failed: {exc}")
        else:
            template = template_probe_result.template
            if template_probe_result.low_score:
                _stage(
                    stage_progress,
                    f"warning template-autodetect-low-score: {TEMPLATE_LOW_SCORE_WARNING}",
                )

    _stage(stage_progress, "process")
    process_result = process_video(
        video_path=video_path,
        output_dir=output_dir,
        template=template,
        roster=roster,
        ocr=ocr,
        progress=progress,
        sampling=sampling,
    )
    _emit_process_warnings(stage_progress, process_result.warnings)
    if template_probe_result is not None:
        update_manifest_section(
            process_result.manifest_path,
            "template_autodetect",
            template_probe_result.to_manifest(),
        )
    _stage(stage_progress, "parse-states")
    state_result = parse_samples_file(process_result.samples_path)
    _stage(stage_progress, "detect-events")
    event_result = detect_events_file(
        state_result.output_path,
        roster=roster,
        config=detection,
    )
    order_validation_ran = bool(roster is not None and detection.initial_order_validation())

    _stage(stage_progress, "export")
    events = load_events(event_result.output_path)
    batting_half_inference = None
    if detection.auto_detect_batting_half:
        batting_half_inference = infer_batting_half(events, roster)
        if batting_half_inference_progress is not None:
            batting_half_inference_progress(batting_half_inference)
        events = filter_at_bats_to_half(events, batting_half_inference.inferred_half)
        if (
            roster is not None
            and detection.order_validation
            and batting_half_inference.inferred_half is not None
        ):
            events = validate_batting_order(events, roster=roster)
            order_validation_ran = True
        write_jsonl(event_result.output_path, events)
    _update_manifest_detection_config(
        process_result.manifest_path,
        {
            **detection.to_manifest(),
            "order_validation_ran": order_validation_ran,
        },
    )
    event_count = len(events)

    # Item 54 P2: never finish silently useless. Skip when OCR was disabled
    # (no_ocr runs are calibration/dry runs and read nothing by design).
    health_warning = None
    if ocr is not no_ocr:
        health_warning = scoreboard_health_warning(
            event_count, process_result.field_read_stats
        )
        update_manifest_section(
            process_result.manifest_path,
            "health",
            {
                "event_count": event_count,
                "no_scoreboard_detected": health_warning is not None,
                "message": health_warning,
            },
        )
        if health_warning is not None:
            _stage(stage_progress, f"warning no-scoreboard-detected: {health_warning}")

    chapters_path, at_bats_path = finalize_run_exports(
        process_result.run_dir,
        corrections=corrections,
        output_prefix=output_prefix,
        export_options=export_options,
        roster=roster,
        generate_review_report=generate_review_report,
        stage_progress=stage_progress,
    )

    return RunGameResult(
        run_dir=process_result.run_dir,
        manifest_path=process_result.manifest_path,
        samples_path=process_result.samples_path,
        states_path=state_result.output_path,
        events_path=event_result.output_path,
        chapters_path=chapters_path,
        at_bats_path=at_bats_path,
        sample_count=process_result.sample_count,
        state_count=state_result.state_count,
        event_count=event_count,
        batting_half_inference=batting_half_inference,
        health_warning=health_warning,
    )


def run_youtube_game(
    url: str,
    video_dir: Path,
    output_dir: Path,
    template: Optional[OverlayTemplate] = None,
    roster: Optional[Roster] = None,
    ocr: OCRCallable = no_ocr,
    progress: Optional[Callable[[int, int, float, int, int], None]] = None,
    output_prefix: Optional[Path] = None,
    corrections: Optional[Iterable[EventCorrection]] = None,
    stage_progress: Optional[Callable[[str], None]] = None,
    sampling: SamplingOptions = SamplingOptions(),
    export_options: ExportOptions = ExportOptions(),
    detection: DetectionConfig = DetectionConfig(),
    download_options: DownloadOptions = DownloadOptions(),
    batting_half_inference_progress: Optional[Callable[[BattingHalfInference], None]] = None,
    generate_review_report: bool = True,
    auto_detect_template: bool = True,
) -> RunYoutubeGameResult:
    """Download a YouTube game video and process it end-to-end."""

    _stage(stage_progress, "download")
    download = download_youtube_video(
        url=url,
        output_dir=video_dir,
        download_options=download_options,
    )
    if download.video_path is None:
        raise ValueError("yt-dlp did not report a downloaded video path")

    run = run_game(
        video_path=download.video_path,
        output_dir=output_dir,
        template=template,
        roster=roster,
        ocr=ocr,
        progress=progress,
        output_prefix=output_prefix,
        corrections=corrections,
        stage_progress=stage_progress,
        sampling=sampling,
        export_options=export_options,
        detection=detection,
        batting_half_inference_progress=batting_half_inference_progress,
        generate_review_report=generate_review_report,
        auto_detect_template=auto_detect_template,
    )
    # Item 63: single-URL runs must carry the source video identity too — the
    # review UI deep-links rows from ``youtube.video_id``. The batch path
    # overwrites this with the richer playlist entry data afterwards.
    record_youtube_source(run.manifest_path, extract_video_id(url), url)
    return RunYoutubeGameResult(download=download, run=run)


def record_youtube_source(
    manifest_path: Path,
    video_id: Optional[str],
    url: Optional[str],
    *,
    playlist_index: Optional[int] = None,
    title: Optional[str] = None,
) -> None:
    """Persist the source YouTube identity to the manifest ``youtube`` section.

    Shared by single-URL runs and the playlist batch path. The review UI reads
    ``youtube.video_id`` back to deep-link review rows to the source video.
    """

    values: dict = {"video_id": video_id, "url": url}
    if playlist_index is not None:
        values["playlist_index"] = playlist_index
    if title is not None:
        values["title"] = title
    update_manifest_section(manifest_path, "youtube", values)


def finalize_run_exports(
    run_dir: Path,
    *,
    corrections: Optional[Iterable[EventCorrection]] = None,
    output_prefix: Optional[Path] = None,
    export_options: Optional[ExportOptions] = None,
    roster: Optional[Roster] = None,
    generate_review_report: bool = True,
    stage_progress: Optional[Callable[[str], None]] = None,
) -> tuple[Path, Path]:
    """Apply corrections, write both text exports, and refresh the review report.

    The shared tail of ``run_game``, also callable on an existing run dir (the
    web corrections UI re-exports through here). When ``export_options`` is
    given it is persisted to the manifest's ``export`` section together with
    ``output_prefix``; when omitted, both are loaded back from the manifest so
    a re-export reproduces the run's original formatting and file locations.
    """

    manifest_path = run_dir / "manifest.json"
    if export_options is None:
        export_options, output_prefix = load_export_options(manifest_path)
    else:
        update_manifest_section(
            manifest_path,
            "export",
            {
                **export_options.to_manifest(),
                "output_prefix": str(output_prefix) if output_prefix else None,
            },
        )

    events = load_events(run_dir / "events.jsonl")
    if corrections is not None:
        events = apply_event_corrections(events, corrections)

    chapters_path, at_bats_path = export_paths(run_dir, output_prefix)
    _write_text_export(
        chapters_path,
        export_youtube_chapters(
            events,
            include_intro=export_options.include_chapter_intro,
            intro_label=export_options.chapter_intro_label,
            include_score=export_options.include_inning_score,
        ),
    )
    _write_text_export(
        at_bats_path,
        export_at_bat_comment(
            events,
            include_inning_headers=export_options.include_at_bat_inning_headers,
        ),
    )

    # Item 48: the review report is a standard run artifact, but its
    # generation must never fail the run (or a re-export) itself.
    if generate_review_report:
        _stage(stage_progress, "review-report")
        try:
            write_review_report(run_dir, roster=roster)
        except Exception as exc:  # noqa: BLE001
            _stage(stage_progress, f"warning review-report-failed: {exc}")

    return chapters_path, at_bats_path


def load_export_options(manifest_path: Path) -> tuple[ExportOptions, Optional[Path]]:
    """Read the persisted export options + output prefix from a run manifest.

    Falls back to defaults for runs recorded before the section existed (or an
    unreadable manifest) — those match what web jobs use.
    """

    defaults = ExportOptions()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults, None
    section = manifest.get("export")
    if not isinstance(section, dict):
        return defaults, None
    options = ExportOptions(
        include_chapter_intro=bool(
            section.get("include_chapter_intro", defaults.include_chapter_intro)
        ),
        chapter_intro_label=str(
            section.get("chapter_intro_label", defaults.chapter_intro_label)
        ),
        include_inning_score=bool(
            section.get("include_inning_score", defaults.include_inning_score)
        ),
        include_at_bat_inning_headers=bool(
            section.get("include_at_bat_inning_headers", defaults.include_at_bat_inning_headers)
        ),
    )
    prefix = section.get("output_prefix")
    return options, Path(prefix) if prefix else None


def export_paths(run_dir: Path, output_prefix: Optional[Path] = None) -> tuple[Path, Path]:
    """Return chapter and at-bat export paths for an optional output prefix."""

    if output_prefix:
        prefix = output_prefix.expanduser()
    else:
        game_slug = game_slug_for_run(run_dir)
        prefix = run_dir / "exports" / game_slug / game_slug
    return (
        prefix.with_name(f"{prefix.name}_chapters.txt"),
        prefix.with_name(f"{prefix.name}_at_bats.txt"),
    )


def _write_text_export(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + ("\n" if text else ""), encoding="utf-8")


def _stage(callback: Optional[Callable[[str], None]], name: str) -> None:
    if callback is not None:
        callback(name)


def _emit_process_warnings(
    callback: Optional[Callable[[str], None]],
    warnings: Iterable[dict],
) -> None:
    if callback is None:
        return
    for warning in warnings:
        code = warning.get("code") or "warning"
        field = warning.get("field")
        suffix = f": {field}" if field else ""
        callback(f"warning {code}{suffix}")


def _update_manifest_detection_config(manifest_path: Path, values: dict) -> None:
    update_manifest_section(manifest_path, "detection", values)
