"""End-to-end local game processing workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from sidelinehd_extractor.corrections import EventCorrection, apply_event_corrections
from sidelinehd_extractor.events import (
    BattingHalfInference,
    detect_events_file,
    filter_at_bats_to_half,
    infer_batting_half,
    load_events,
    validate_batting_order,
)
from sidelinehd_extractor.exports import export_at_bat_comment, export_youtube_chapters
from sidelinehd_extractor.models import HalfInning, OverlayTemplate, Roster
from sidelinehd_extractor.naming import game_slug_for_run
from sidelinehd_extractor.ocr import OCRCallable, no_ocr
from sidelinehd_extractor.processing import process_video, write_jsonl
from sidelinehd_extractor.state import parse_samples_file
from sidelinehd_extractor.youtube import (
    DEFAULT_FORMAT_SELECTOR,
    DEFAULT_YOUTUBE_CLIENT,
    DownloadResult,
    download_youtube_video,
)


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
    sample_every_seconds: float = 5.0,
    start_seconds: float = 0.0,
    end_seconds: Optional[float] = None,
    save_crops: bool = True,
    ocr: OCRCallable = no_ocr,
    fields: Optional[Iterable[str]] = None,
    progress: Optional[Callable[[int, int, float, int, int], None]] = None,
    compute_video_hash: bool = False,
    output_prefix: Optional[Path] = None,
    corrections: Optional[Iterable[EventCorrection]] = None,
    stage_progress: Optional[Callable[[str], None]] = None,
    include_chapter_intro: bool = True,
    chapter_intro_label: str = "Pregame",
    include_inning_score: bool = True,
    include_at_bat_inning_headers: bool = True,
    batting_half: Optional[HalfInning] = None,
    auto_detect_batting_half: bool = False,
    min_at_bat_spacing_seconds: float = 45.0,
    min_at_bat_spacing_roster_confirmed_seconds: float = 20.0,
    order_validation: bool = True,
    batting_half_inference_progress: Optional[Callable[[BattingHalfInference], None]] = None,
) -> RunGameResult:
    """Process video, detect events, and write both YouTube text exports."""

    _stage(stage_progress, "process")
    process_result = process_video(
        video_path=video_path,
        output_dir=output_dir,
        template=template,
        roster=roster,
        sample_every_seconds=sample_every_seconds,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        save_crops=save_crops,
        ocr=ocr,
        fields=fields,
        progress=progress,
        compute_video_hash=compute_video_hash,
    )
    _stage(stage_progress, "parse-states")
    state_result = parse_samples_file(process_result.samples_path)
    _stage(stage_progress, "detect-events")
    event_result = detect_events_file(
        state_result.output_path,
        roster=roster,
        batting_half=None if auto_detect_batting_half else batting_half,
        min_at_bat_spacing_seconds=min_at_bat_spacing_seconds,
        min_at_bat_spacing_roster_confirmed_seconds=min_at_bat_spacing_roster_confirmed_seconds,
        order_validation=order_validation and not auto_detect_batting_half,
    )
    order_validation_ran = bool(roster is not None and order_validation and not auto_detect_batting_half)

    _stage(stage_progress, "export")
    events = load_events(event_result.output_path)
    batting_half_inference = None
    if auto_detect_batting_half:
        batting_half_inference = infer_batting_half(events, roster)
        if batting_half_inference_progress is not None:
            batting_half_inference_progress(batting_half_inference)
        events = filter_at_bats_to_half(events, batting_half_inference.inferred_half)
        if (
            roster is not None
            and order_validation
            and batting_half_inference.inferred_half is not None
        ):
            events = validate_batting_order(events, roster=roster)
            order_validation_ran = True
        write_jsonl(event_result.output_path, events)
    _update_manifest_detection_config(
        process_result.manifest_path,
        {
            "min_at_bat_spacing_seconds": min_at_bat_spacing_seconds,
            "min_at_bat_spacing_roster_confirmed_seconds": (
                min_at_bat_spacing_roster_confirmed_seconds
            ),
            "batting_half": "auto" if auto_detect_batting_half else _half_value(batting_half),
            "order_validation_requested": order_validation,
            "order_validation_ran": order_validation_ran,
        },
    )
    event_count = len(events)
    if corrections is not None:
        events = apply_event_corrections(events, corrections)

    chapters_path, at_bats_path = export_paths(process_result.run_dir, output_prefix)
    _write_text_export(
        chapters_path,
        export_youtube_chapters(
            events,
            include_intro=include_chapter_intro,
            intro_label=chapter_intro_label,
            include_score=include_inning_score,
        ),
    )
    _write_text_export(
        at_bats_path,
        export_at_bat_comment(
            events,
            include_inning_headers=include_at_bat_inning_headers,
        ),
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
    )


def run_youtube_game(
    url: str,
    video_dir: Path,
    output_dir: Path,
    template: Optional[OverlayTemplate] = None,
    roster: Optional[Roster] = None,
    sample_every_seconds: float = 5.0,
    start_seconds: float = 0.0,
    end_seconds: Optional[float] = None,
    save_crops: bool = True,
    ocr: OCRCallable = no_ocr,
    fields: Optional[Iterable[str]] = None,
    progress: Optional[Callable[[int, int, float, int, int], None]] = None,
    compute_video_hash: bool = False,
    output_prefix: Optional[Path] = None,
    corrections: Optional[Iterable[EventCorrection]] = None,
    stage_progress: Optional[Callable[[str], None]] = None,
    include_chapter_intro: bool = True,
    chapter_intro_label: str = "Pregame",
    include_inning_score: bool = True,
    include_at_bat_inning_headers: bool = True,
    batting_half: Optional[HalfInning] = None,
    auto_detect_batting_half: bool = False,
    min_at_bat_spacing_seconds: float = 45.0,
    min_at_bat_spacing_roster_confirmed_seconds: float = 20.0,
    order_validation: bool = True,
    batting_half_inference_progress: Optional[Callable[[BattingHalfInference], None]] = None,
    format_selector: str = DEFAULT_FORMAT_SELECTOR,
    merge_output_format: str = "mp4",
    write_info_json: bool = True,
    no_playlist: bool = True,
    youtube_client: Optional[str] = DEFAULT_YOUTUBE_CLIENT,
) -> RunYoutubeGameResult:
    """Download a YouTube game video and process it end-to-end."""

    _stage(stage_progress, "download")
    download = download_youtube_video(
        url=url,
        output_dir=video_dir,
        format_selector=format_selector,
        merge_output_format=merge_output_format,
        write_info_json=write_info_json,
        no_playlist=no_playlist,
        youtube_client=youtube_client,
    )
    if download.video_path is None:
        raise ValueError("yt-dlp did not report a downloaded video path")

    run = run_game(
        video_path=download.video_path,
        output_dir=output_dir,
        template=template,
        roster=roster,
        sample_every_seconds=sample_every_seconds,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        save_crops=save_crops,
        ocr=ocr,
        fields=fields,
        progress=progress,
        compute_video_hash=compute_video_hash,
        output_prefix=output_prefix,
        corrections=corrections,
        stage_progress=stage_progress,
        include_chapter_intro=include_chapter_intro,
        chapter_intro_label=chapter_intro_label,
        include_inning_score=include_inning_score,
        include_at_bat_inning_headers=include_at_bat_inning_headers,
        batting_half=batting_half,
        auto_detect_batting_half=auto_detect_batting_half,
        min_at_bat_spacing_seconds=min_at_bat_spacing_seconds,
        min_at_bat_spacing_roster_confirmed_seconds=min_at_bat_spacing_roster_confirmed_seconds,
        order_validation=order_validation,
        batting_half_inference_progress=batting_half_inference_progress,
    )
    return RunYoutubeGameResult(download=download, run=run)


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


def _update_manifest_detection_config(manifest_path: Path, values: dict) -> None:
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    detection = manifest.get("detection")
    if not isinstance(detection, dict):
        detection = {}
    detection.update(values)
    manifest["detection"] = detection
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _half_value(half: Optional[HalfInning]) -> str:
    return half.value if half is not None else "both"
