"""Command-line interface for the local extraction pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, List, Optional

from sidelinehd_extractor.calibration import (
    extract_calibration_frames,
    parse_timestamp_list,
    parse_timestamp_value,
    render_template_guide,
)
from sidelinehd_extractor.crops import extract_crop_from_video, save_crop
from sidelinehd_extractor.config import load_overlay_template, load_roster
from sidelinehd_extractor.corrections import apply_event_corrections, load_event_corrections
from sidelinehd_extractor.events import detect_events_file, load_events
from sidelinehd_extractor.exports import export_at_bat_comment, export_youtube_chapters
from sidelinehd_extractor.models import HalfInning, RegionFraction, Roster
from sidelinehd_extractor.ocr import (
    OCRBackendUnavailable,
    OCRError,
    create_ocr_backend,
    ocr_image_file,
    write_preprocessed_image,
)
from sidelinehd_extractor.publish import write_publish_kit
from sidelinehd_extractor.processing import process_video
from sidelinehd_extractor.review import render_event_review
from sidelinehd_extractor.review_report import write_review_report
from sidelinehd_extractor.roster import default_roster_path, parse_team_list, write_roster_csv
from sidelinehd_extractor.serialization import to_plain_data
from sidelinehd_extractor.state import parse_samples_file
from sidelinehd_extractor.video import probe_video, read_frame_at
from sidelinehd_extractor.workflow import export_paths as workflow_export_paths
from sidelinehd_extractor.workflow import run_game, run_youtube_game
from sidelinehd_extractor.youtube import (
    DEFAULT_FORMAT_SELECTOR,
    DEFAULT_YOUTUBE_CLIENT,
    YTDLPError,
    download_youtube_video,
)


def _to_json(value: object) -> str:
    return json.dumps(to_plain_data(value), indent=2)


def _format_progress_timestamp(seconds: float) -> str:
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _build_progress_callback(every: int) -> Callable[[int, int, float, int, int], None]:
    every = max(every, 1)

    def progress(
        timestamp_index: int,
        total_timestamps: int,
        timestamp_seconds: float,
        sample_count: int,
        total_expected_samples: int,
    ) -> None:
        if (
            timestamp_index == 1
            or timestamp_index == total_timestamps
            or timestamp_index % every == 0
        ):
            percent = (timestamp_index / total_timestamps * 100) if total_timestamps else 100
            print(
                "processing "
                f"{timestamp_index}/{total_timestamps} timestamps "
                f"({percent:5.1f}%) "
                f"at {_format_progress_timestamp(timestamp_seconds)}; "
                f"{sample_count}/{total_expected_samples} samples",
                file=sys.stderr,
                flush=True,
            )

    return progress


def _build_stage_callback() -> Callable[[str], None]:
    labels = {
        "download": "downloading YouTube video",
        "process": "processing video OCR samples",
        "parse-states": "parsing OCR samples into states",
        "detect-events": "detecting chapters and at-bats",
        "export": "writing YouTube text exports",
    }

    def progress(stage_name: str) -> None:
        print(f"run-game: {labels.get(stage_name, stage_name)}", file=sys.stderr, flush=True)

    return progress


def _default_run_fields(args: argparse.Namespace) -> List[str]:
    return _parse_field_list(args.field) or [
        "inning",
        "count",
        "lineup_strip",
        "batter_card_name",
        "batter_card_number",
        "batter_number",
    ]


def _parse_batting_half(value: str) -> Optional[HalfInning]:
    if value == "top":
        return HalfInning.TOP
    if value == "bottom":
        return HalfInning.BOTTOM
    return None


def _is_auto_batting_half(value: str) -> bool:
    return value == "auto"


def _build_batting_half_inference_callback():
    def progress(inference) -> None:
        print(inference.message, file=sys.stderr, flush=True)

    return progress


def _cmd_probe(args: argparse.Namespace) -> int:
    video = probe_video(args.video_path, compute_hash=args.hash)
    print(_to_json(video))
    return 0


def _calibration_output_dir(base_dir: Path, video_path: Path) -> Path:
    return base_dir.expanduser() / video_path.stem


def _parse_field_list(values: List[str]) -> Optional[List[str]]:
    fields = []
    for value in values:
        fields.extend(item.strip() for item in value.split(",") if item.strip())
    return fields or None


def _cmd_download(args: argparse.Namespace) -> int:
    result = download_youtube_video(
        url=args.url,
        output_dir=args.output_dir,
        format_selector=args.format,
        merge_output_format=args.merge_output_format,
        write_info_json=not args.no_info_json,
        no_playlist=not args.playlist,
        youtube_client=args.youtube_client,
    )
    print(_to_json(result))
    return 0


def _cmd_calibration_frames(args: argparse.Namespace) -> int:
    timestamps = parse_timestamp_list(args.timestamp) if args.timestamp else None
    output_dir = args.output_dir or _calibration_output_dir(
        Path("calibration_frames"), args.video_path
    )
    result = extract_calibration_frames(
        video_path=args.video_path,
        output_dir=output_dir,
        timestamps_seconds=timestamps,
    )
    print(_to_json(result))
    return 0


def _cmd_prepare_youtube(args: argparse.Namespace) -> int:
    download = download_youtube_video(
        url=args.url,
        output_dir=args.video_dir,
        format_selector=args.format,
        merge_output_format=args.merge_output_format,
        write_info_json=not args.no_info_json,
        no_playlist=not args.playlist,
        youtube_client=args.youtube_client,
    )
    if download.video_path is None:
        raise ValueError("yt-dlp did not report a downloaded video path")

    timestamps = parse_timestamp_list(args.timestamp) if args.timestamp else None
    calibration_output_dir = args.frames_dir or _calibration_output_dir(
        Path("calibration_frames"), download.video_path
    )
    frames = extract_calibration_frames(
        video_path=download.video_path,
        output_dir=calibration_output_dir,
        timestamps_seconds=timestamps,
    )
    print(_to_json({"download": download, "calibration_frames": frames}))
    return 0


def _cmd_extract_frame(args: argparse.Namespace) -> int:
    region = RegionFraction(x=args.x, y=args.y, width=args.width, height=args.height)
    crop = extract_crop_from_video(args.video_path, parse_timestamp_value(args.timestamp), region)
    destination = save_crop(crop, args.output_path)
    print(destination)
    return 0


def _cmd_template_guide(args: argparse.Namespace) -> int:
    template = load_overlay_template(args.template)
    frame = read_frame_at(args.video_path, parse_timestamp_value(args.timestamp))
    destination = render_template_guide(frame, template, args.output_path)
    print(destination)
    return 0


def _cmd_ocr_image(args: argparse.Namespace) -> int:
    if args.preprocessed_output:
        write_preprocessed_image(args.image_path, args.preprocessed_output, args.field)
    result = ocr_image_file(args.image_path, args.field, backend=args.ocr)
    print(_to_json({"image_path": args.image_path, "field": args.field, "ocr": result}))
    return 0


def _cmd_process(args: argparse.Namespace) -> int:
    template = load_overlay_template(args.template) if args.template else None
    roster = load_roster(args.roster, team_name=args.team_name) if args.roster else None
    ocr_backend = create_ocr_backend(args.ocr)
    result = process_video(
        video_path=args.video_path,
        output_dir=args.output_dir,
        template=template,
        roster=roster,
        sample_every_seconds=args.sample_every,
        start_seconds=parse_timestamp_value(args.start),
        end_seconds=parse_timestamp_value(args.end) if args.end else None,
        save_crops=not args.no_crops,
        ocr=ocr_backend,
        fields=_parse_field_list(args.field),
        progress=None if args.quiet else _build_progress_callback(args.progress_every),
        compute_video_hash=args.hash_video,
    )
    print(_to_json(result))
    return 0


def _cmd_make_roster(args: argparse.Namespace) -> int:
    if str(args.input_path) == "-":
        text = sys.stdin.read()
        team_name = args.team_name or args.output.stem
    else:
        source = args.input_path.expanduser()
        text = source.read_text(encoding="utf-8")
        team_name = args.team_name or source.stem
    roster = parse_team_list(text, team_name=team_name)
    result = write_roster_csv(roster, args.output)
    print(_to_json(result))
    return 0


def _cmd_setup_roster(args: argparse.Namespace) -> int:
    is_tty = sys.stdin.isatty()
    team_name = args.team_name
    if not team_name:
        if not is_tty:
            print("Error: --team-name is required when stdin is not a terminal.", file=sys.stderr)
            return 1
        team_name = input("Team name: ").strip()
        if not team_name:
            print("Error: team name is required.", file=sys.stderr)
            return 1

    if is_tty:
        print("Paste roster lines like '#26 Amelia V.'. Press Enter twice when done:")
        lines = _read_roster_lines_interactive()
    else:
        lines = sys.stdin.read().splitlines()

    if not any(line.strip() for line in lines):
        print("Error: no roster lines entered.", file=sys.stderr)
        return 1

    try:
        roster = parse_team_list("\n".join(lines), team_name=team_name)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output_path = args.output or default_roster_path(team_name)
    display_output_path = output_path.expanduser().resolve()
    if is_tty:
        _print_roster_preview(roster)
        response = (
            input(f"\nWrite {len(roster.players)} players to {display_output_path}? [Y/n] ")
            .strip()
            .lower()
        )
        if response and response not in {"y", "yes"}:
            print("Cancelled.", file=sys.stderr)
            return 1

    result = write_roster_csv(roster, output_path)
    print(f"Wrote {result.player_count} players to {result.output_path}")
    if is_tty:
        print("")
        print("Use your roster:")
        print(f"  {_format_roster_next_command(result.output_path)}")
    return 0


def _read_roster_lines_interactive() -> List[str]:
    lines = []
    blank_count = 0
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            blank_count += 1
            if blank_count >= 2:
                break
        else:
            blank_count = 0
        lines.append(line)
    return lines


def _print_roster_preview(roster: Roster) -> None:
    rows = [
        (
            player.number,
            player.display_name or player.full_name,
            "; ".join(player.aliases),
        )
        for player in roster.players
    ]
    headers = ("#", "Name", "Aliases")
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    print("")
    print("Roster preview:")
    print(_format_roster_preview_row(headers, widths))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(_format_roster_preview_row(row, widths))


def _format_roster_preview_row(row: tuple[str, str, str], widths: List[int]) -> str:
    return " | ".join(value.ljust(widths[index]) for index, value in enumerate(row))


def _format_roster_next_command(roster_path: Path) -> str:
    return (
        "sidelinehd-extractor run-youtube 'YOUTUBE_URL' "
        f"--roster {roster_path} "
        "--template YOUR_TEMPLATE"
    )


def _cmd_run_game(args: argparse.Namespace) -> int:
    template = load_overlay_template(args.template) if args.template else None
    roster = load_roster(args.roster, team_name=args.team_name) if args.roster else None
    ocr_backend = create_ocr_backend(args.ocr)
    corrections = load_event_corrections(args.corrections) if args.corrections else None
    result = run_game(
        video_path=args.video_path,
        output_dir=args.output_dir,
        template=template,
        roster=roster,
        sample_every_seconds=args.sample_every,
        start_seconds=parse_timestamp_value(args.start),
        end_seconds=parse_timestamp_value(args.end) if args.end else None,
        save_crops=not args.no_crops,
        ocr=ocr_backend,
        fields=_default_run_fields(args),
        progress=None if args.quiet else _build_progress_callback(args.progress_every),
        compute_video_hash=args.hash_video,
        output_prefix=args.output_prefix,
        corrections=corrections,
        stage_progress=None if args.quiet else _build_stage_callback(),
        include_chapter_intro=not args.no_chapter_intro,
        chapter_intro_label=args.chapter_intro_label,
        include_at_bat_inning_headers=not args.no_at_bat_inning_headers,
        batting_half=_parse_batting_half(args.batting_half),
        auto_detect_batting_half=_is_auto_batting_half(args.batting_half),
        min_at_bat_spacing_seconds=args.min_at_bat_spacing,
        min_at_bat_spacing_roster_confirmed_seconds=args.min_at_bat_spacing_roster_confirmed,
        batting_half_inference_progress=(
            None if args.quiet else _build_batting_half_inference_callback()
        ),
    )
    print(
        _to_json(
            {
                "run_dir": result.run_dir,
                "manifest_path": result.manifest_path,
                "samples_path": result.samples_path,
                "states_path": result.states_path,
                "events_path": result.events_path,
                "chapters_path": result.chapters_path,
                "at_bats_path": result.at_bats_path,
                "sample_count": result.sample_count,
                "state_count": result.state_count,
                "event_count": result.event_count,
                "batting_half_inference": result.batting_half_inference,
                "next_commands": [
                    (
                        "PYTHONPATH=src python3 -m sidelinehd_extractor.cli "
                        f"review-events '{result.run_dir}' --kind at-bats"
                    ),
                    (
                        "PYTHONPATH=src python3 -m sidelinehd_extractor.cli "
                        f"review-events '{result.run_dir}' --kind chapters"
                    ),
                ],
            }
        )
    )
    return 0


def _cmd_run_youtube(args: argparse.Namespace) -> int:
    template = load_overlay_template(args.template) if args.template else None
    roster = load_roster(args.roster, team_name=args.team_name) if args.roster else None
    ocr_backend = create_ocr_backend(args.ocr)
    corrections = load_event_corrections(args.corrections) if args.corrections else None
    result = run_youtube_game(
        url=args.url,
        video_dir=args.video_dir,
        output_dir=args.output_dir,
        template=template,
        roster=roster,
        sample_every_seconds=args.sample_every,
        start_seconds=parse_timestamp_value(args.start),
        end_seconds=parse_timestamp_value(args.end) if args.end else None,
        save_crops=not args.no_crops,
        ocr=ocr_backend,
        fields=_default_run_fields(args),
        progress=None if args.quiet else _build_progress_callback(args.progress_every),
        compute_video_hash=args.hash_video,
        output_prefix=args.output_prefix,
        corrections=corrections,
        stage_progress=None if args.quiet else _build_stage_callback(),
        include_chapter_intro=not args.no_chapter_intro,
        chapter_intro_label=args.chapter_intro_label,
        include_at_bat_inning_headers=not args.no_at_bat_inning_headers,
        batting_half=_parse_batting_half(args.batting_half),
        auto_detect_batting_half=_is_auto_batting_half(args.batting_half),
        min_at_bat_spacing_seconds=args.min_at_bat_spacing,
        min_at_bat_spacing_roster_confirmed_seconds=args.min_at_bat_spacing_roster_confirmed,
        batting_half_inference_progress=(
            None if args.quiet else _build_batting_half_inference_callback()
        ),
        format_selector=args.format,
        merge_output_format=args.merge_output_format,
        write_info_json=not args.no_info_json,
        no_playlist=not args.playlist,
        youtube_client=args.youtube_client,
    )
    run = result.run
    print(
        _to_json(
            {
                "download": result.download,
                "run_dir": run.run_dir,
                "manifest_path": run.manifest_path,
                "samples_path": run.samples_path,
                "states_path": run.states_path,
                "events_path": run.events_path,
                "chapters_path": run.chapters_path,
                "at_bats_path": run.at_bats_path,
                "sample_count": run.sample_count,
                "state_count": run.state_count,
                "event_count": run.event_count,
                "batting_half_inference": run.batting_half_inference,
                "next_commands": [
                    (
                        "PYTHONPATH=src python3 -m sidelinehd_extractor.cli "
                        f"review-events '{run.run_dir}' --kind at-bats"
                    ),
                    (
                        "PYTHONPATH=src python3 -m sidelinehd_extractor.cli "
                        f"review-events '{run.run_dir}' --kind chapters"
                    ),
                ],
            }
        )
    )
    return 0


def _cmd_parse_states(args: argparse.Namespace) -> int:
    input_path = args.input_path
    if input_path.is_dir():
        input_path = input_path / "samples.jsonl"
    result = parse_samples_file(input_path, output_path=args.output)
    print(_to_json(result))
    return 0


def _cmd_detect_events(args: argparse.Namespace) -> int:
    input_path = args.input_path
    if input_path.is_dir():
        input_path = input_path / "states.jsonl"
    roster = load_roster(args.roster, team_name=args.team_name) if args.roster else None
    result = detect_events_file(
        input_path,
        output_path=args.output,
        roster=roster,
        batting_half=_parse_batting_half(args.batting_half),
        min_at_bat_spacing_seconds=args.min_at_bat_spacing,
        min_at_bat_spacing_roster_confirmed_seconds=args.min_at_bat_spacing_roster_confirmed,
    )
    print(_to_json(result))
    return 0


def _events_path_from_run_path(run_path: Path) -> Path:
    if run_path.is_dir():
        return run_path / "events.jsonl"
    return run_path


def _load_events_for_cli(run_path: Path, corrections_path: Optional[Path] = None):
    events = load_events(_events_path_from_run_path(run_path))
    if corrections_path:
        events = apply_event_corrections(events, load_event_corrections(corrections_path))
    return events


def _cmd_review_events(args: argparse.Namespace) -> int:
    events = _load_events_for_cli(args.run_path, corrections_path=args.corrections)
    roster = load_roster(args.roster, team_name=args.team_name) if args.roster else None
    print(render_event_review(events, kind=args.kind, roster=roster))
    return 0


def _cmd_review_report(args: argparse.Namespace) -> int:
    result = write_review_report(
        run_path=args.run_path,
        output_path=args.output,
        kind=args.kind,
        roster=load_roster(args.roster, team_name=args.team_name) if args.roster else None,
    )
    print(_to_json(result))
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    events = _load_events_for_cli(args.run_path, corrections_path=args.corrections)
    if args.kind == "chapters":
        text = export_youtube_chapters(
            events,
            include_intro=not args.no_chapter_intro,
            intro_label=args.chapter_intro_label,
        )
    else:
        text = export_at_bat_comment(
            events,
            include_inning_headers=not args.no_at_bat_inning_headers,
        )

    if args.output:
        args.output.expanduser().parent.mkdir(parents=True, exist_ok=True)
        args.output.expanduser().write_text(text + ("\n" if text else ""), encoding="utf-8")
        print(args.output)
    else:
        print(text)
    return 0


def _cmd_publish_helper(args: argparse.Namespace) -> int:
    default_chapters, default_at_bats = workflow_export_paths(args.run_path)
    result = write_publish_kit(
        run_path=args.run_path,
        chapters_path=args.chapters or default_chapters,
        at_bats_path=args.at_bats or default_at_bats,
        output_path=args.output,
        output_dir=args.output_dir,
        game_name=args.game_name,
        generate_html=not args.no_html,
    )
    print(_to_json(result))
    return 0


def _add_run_processing_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", "-o", type=Path, default=Path("runs"))
    parser.add_argument("--template", type=Path, help="Overlay template JSON file.")
    parser.add_argument("--roster", type=Path, help="Roster CSV or JSON file.")
    parser.add_argument("--team-name", help="Team name override for roster CSV/JSON.")
    parser.add_argument(
        "--sample-every",
        type=float,
        default=5.0,
        help="Seconds between sampled frames.",
    )
    parser.add_argument(
        "--start", default="0", help="Start timestamp as seconds, M:SS, or H:MM:SS."
    )
    parser.add_argument("--end", help="Optional end timestamp as seconds, M:SS, or H:MM:SS.")
    parser.add_argument("--ocr", choices=("none", "tesseract"), default="tesseract")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Print progress every N sampled timestamps.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output.")
    parser.add_argument(
        "--field",
        action="append",
        default=[],
        help=(
            "Template field to process. Repeatable or comma-separated. Defaults to "
            "inning,count,lineup_strip,batter_card_name,batter_card_number,batter_number."
        ),
    )
    parser.add_argument("--no-crops", action="store_true", help="Do not write crop image files.")
    parser.add_argument(
        "--hash-video",
        action="store_true",
        help="Compute a full-video SHA-256 for audit metadata. Slower on large videos.",
    )
    parser.add_argument(
        "--output-prefix",
        type=Path,
        help="Output prefix for text exports, such as scratch/full.",
    )
    parser.add_argument(
        "--corrections", type=Path, help="Optional corrections CSV to apply to exports."
    )
    parser.add_argument(
        "--chapter-intro-label",
        default="Pregame",
        help="Label for the automatic 0:00 chapter when the first chapter starts later.",
    )
    parser.add_argument(
        "--no-chapter-intro",
        action="store_true",
        help="Do not prepend an automatic 0:00 chapter.",
    )
    parser.add_argument(
        "--no-at-bat-inning-headers",
        action="store_true",
        help="Do not add inning headers to the at-bat pinned-comment export.",
    )
    parser.add_argument(
        "--batting-half",
        choices=("auto", "top", "bottom", "both"),
        default="auto",
        help=(
            "Which half contains your rostered team's at-bats. Default auto infers from "
            "roster-matched batter-card names; top/bottom override inference."
        ),
    )
    parser.add_argument(
        "--min-at-bat-spacing",
        type=float,
        default=45.0,
        help="Minimum seconds between emitted at-bat starts.",
    )
    parser.add_argument(
        "--min-at-bat-spacing-roster-confirmed",
        type=float,
        default=20.0,
        dest="min_at_bat_spacing_roster_confirmed",
        metavar="SECONDS",
        help="Minimum seconds between at-bats when the new batter is roster-confirmed.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sidelinehd-extractor",
        description="Extract SidelineHD overlay timestamps from local game videos.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser("download", help="Download a YouTube video with yt-dlp.")
    download.add_argument("url")
    download.add_argument("--output-dir", "-o", type=Path, default=Path("videos"))
    download.add_argument(
        "--format", default=DEFAULT_FORMAT_SELECTOR, help="yt-dlp format selector."
    )
    download.add_argument("--merge-output-format", default="mp4")
    download.add_argument(
        "--youtube-client",
        default=DEFAULT_YOUTUBE_CLIENT,
        help="YouTube player client for yt-dlp extractor args. Use '' to disable.",
    )
    download.add_argument("--no-info-json", action="store_true")
    download.add_argument("--playlist", action="store_true", help="Allow playlist downloads.")
    download.set_defaults(func=_cmd_download)

    prepare_youtube = subparsers.add_parser(
        "prepare-youtube",
        help="Download a YouTube video and extract calibration frames.",
    )
    prepare_youtube.add_argument("url")
    prepare_youtube.add_argument("--video-dir", type=Path, default=Path("videos"))
    prepare_youtube.add_argument("--frames-dir", type=Path)
    prepare_youtube.add_argument("--timestamp", "-t", action="append", default=[])
    prepare_youtube.add_argument(
        "--format",
        default=DEFAULT_FORMAT_SELECTOR,
        help="yt-dlp format selector.",
    )
    prepare_youtube.add_argument("--merge-output-format", default="mp4")
    prepare_youtube.add_argument(
        "--youtube-client",
        default=DEFAULT_YOUTUBE_CLIENT,
        help="YouTube player client for yt-dlp extractor args. Use '' to disable.",
    )
    prepare_youtube.add_argument("--no-info-json", action="store_true")
    prepare_youtube.add_argument(
        "--playlist", action="store_true", help="Allow playlist downloads."
    )
    prepare_youtube.set_defaults(func=_cmd_prepare_youtube)

    probe = subparsers.add_parser("probe", help="Print basic metadata for a video file.")
    probe.add_argument("video_path", type=Path)
    probe.add_argument("--hash", action="store_true", help="Compute the full-file SHA-256 digest.")
    probe.set_defaults(func=_cmd_probe)

    extract_frame = subparsers.add_parser(
        "extract-frame",
        help="Extract a frame crop using frame-relative coordinates.",
    )
    extract_frame.add_argument("video_path", type=Path)
    extract_frame.add_argument("output_path", type=Path)
    extract_frame.add_argument("--timestamp", "-t", default="0")
    extract_frame.add_argument("--x", type=float, default=0.0)
    extract_frame.add_argument("--y", type=float, default=0.0)
    extract_frame.add_argument("--width", type=float, default=1.0)
    extract_frame.add_argument("--height", type=float, default=1.0)
    extract_frame.set_defaults(func=_cmd_extract_frame)

    calibration_frames = subparsers.add_parser(
        "calibration-frames",
        help="Extract full-frame PNGs for overlay template calibration.",
    )
    calibration_frames.add_argument("video_path", type=Path)
    calibration_frames.add_argument("--output-dir", "-o", type=Path)
    calibration_frames.add_argument(
        "--timestamp",
        "-t",
        action="append",
        default=[],
        help="Seconds, M:SS, H:MM:SS, or comma-separated list. Repeatable.",
    )
    calibration_frames.set_defaults(func=_cmd_calibration_frames)

    template_guide = subparsers.add_parser(
        "template-guide",
        help="Draw overlay template regions on a video frame.",
    )
    template_guide.add_argument("video_path", type=Path)
    template_guide.add_argument("output_path", type=Path)
    template_guide.add_argument("--template", required=True, type=Path)
    template_guide.add_argument("--timestamp", "-t", default="0")
    template_guide.set_defaults(func=_cmd_template_guide)

    ocr_image = subparsers.add_parser(
        "ocr-image",
        help="Run OCR on one crop image for backend/preprocessing checks.",
    )
    ocr_image.add_argument("image_path", type=Path)
    ocr_image.add_argument("--field", required=True, help="Template field name, such as count.")
    ocr_image.add_argument("--ocr", choices=("none", "tesseract"), default="tesseract")
    ocr_image.add_argument(
        "--preprocessed-output",
        type=Path,
        help="Optional path to save the image after OCR preprocessing.",
    )
    ocr_image.set_defaults(func=_cmd_ocr_image)

    process = subparsers.add_parser(
        "process",
        help="Sample a video and write crop/OCR audit artifacts.",
    )
    process.add_argument("video_path", type=Path)
    process.add_argument("--output-dir", "-o", type=Path, default=Path("runs"))
    process.add_argument("--template", type=Path, help="Overlay template JSON file.")
    process.add_argument("--roster", type=Path, help="Roster CSV or JSON file.")
    process.add_argument("--team-name", help="Team name override for roster CSV/JSON.")
    process.add_argument(
        "--sample-every",
        type=float,
        default=5.0,
        help="Seconds between sampled frames.",
    )
    process.add_argument(
        "--start", default="0", help="Start timestamp as seconds, M:SS, or H:MM:SS."
    )
    process.add_argument("--end", help="Optional end timestamp as seconds, M:SS, or H:MM:SS.")
    process.add_argument("--ocr", choices=("none", "tesseract"), default="none")
    process.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Print progress every N sampled timestamps.",
    )
    process.add_argument("--quiet", action="store_true", help="Suppress progress output.")
    process.add_argument(
        "--field",
        action="append",
        default=[],
        help="Template field to process. Repeatable or comma-separated. Defaults to all fields.",
    )
    process.add_argument("--no-crops", action="store_true", help="Do not write crop image files.")
    process.add_argument(
        "--hash-video",
        action="store_true",
        help="Compute a full-video SHA-256 for audit metadata. Slower on large videos.",
    )
    process.set_defaults(func=_cmd_process)

    make_roster = subparsers.add_parser(
        "make-roster",
        help="Convert a pasted team list into roster CSV.",
    )
    make_roster.add_argument(
        "input_path",
        type=Path,
        help="Text file with lines like '#26 Amelia V.', or '-' for stdin.",
    )
    make_roster.add_argument("--output", "-o", type=Path, default=Path("roster.csv"))
    make_roster.add_argument(
        "--team-name", help="Team name for JSON summaries and future metadata."
    )
    make_roster.set_defaults(func=_cmd_make_roster)

    setup_roster = subparsers.add_parser(
        "setup-roster",
        help="Interactively paste a team roster and save it to rosters/.",
    )
    setup_roster.add_argument(
        "--team-name",
        help="Team name. Required when stdin is not a terminal.",
    )
    setup_roster.add_argument("--output", "-o", type=Path, help="Override the default output path.")
    setup_roster.set_defaults(func=_cmd_setup_roster)

    run_game_parser = subparsers.add_parser(
        "run-game",
        help="Process a video end-to-end and write both YouTube exports.",
    )
    run_game_parser.add_argument("video_path", type=Path)
    _add_run_processing_arguments(run_game_parser)
    run_game_parser.set_defaults(func=_cmd_run_game)

    run_youtube = subparsers.add_parser(
        "run-youtube",
        help="Download a YouTube video, process it, and write both YouTube exports.",
    )
    run_youtube.add_argument("url")
    run_youtube.add_argument("--video-dir", type=Path, default=Path("videos"))
    _add_run_processing_arguments(run_youtube)
    run_youtube.add_argument(
        "--format",
        default=DEFAULT_FORMAT_SELECTOR,
        help="yt-dlp format selector.",
    )
    run_youtube.add_argument("--merge-output-format", default="mp4")
    run_youtube.add_argument(
        "--youtube-client",
        default=DEFAULT_YOUTUBE_CLIENT,
        help="YouTube player client for yt-dlp extractor args. Use '' to disable.",
    )
    run_youtube.add_argument("--no-info-json", action="store_true")
    run_youtube.add_argument("--playlist", action="store_true", help="Allow playlist downloads.")
    run_youtube.set_defaults(func=_cmd_run_youtube)

    parse_states = subparsers.add_parser(
        "parse-states",
        help="Parse OCR samples into structured overlay states.",
    )
    parse_states.add_argument("input_path", type=Path, help="Run directory or samples.jsonl file.")
    parse_states.add_argument("--output", "-o", type=Path, help="Output states JSONL path.")
    parse_states.set_defaults(func=_cmd_parse_states)

    detect_events = subparsers.add_parser(
        "detect-events",
        help="Detect inning and at-bat events from parsed overlay states.",
    )
    detect_events.add_argument("input_path", type=Path, help="Run directory or states.jsonl file.")
    detect_events.add_argument("--output", "-o", type=Path, help="Output events JSONL path.")
    detect_events.add_argument("--roster", type=Path, help="Roster CSV or JSON file.")
    detect_events.add_argument("--team-name", help="Team name override for roster CSV/JSON.")
    detect_events.add_argument(
        "--batting-half",
        choices=("top", "bottom", "both"),
        default="both",
        help="Only emit at-bats from this half-inning. Use top for away teams, bottom for home teams.",
    )
    detect_events.add_argument(
        "--min-at-bat-spacing",
        type=float,
        default=45.0,
        help="Minimum seconds between emitted at-bat starts.",
    )
    detect_events.add_argument(
        "--min-at-bat-spacing-roster-confirmed",
        type=float,
        default=20.0,
        dest="min_at_bat_spacing_roster_confirmed",
        metavar="SECONDS",
        help="Minimum seconds between at-bats when the new batter is roster-confirmed.",
    )
    detect_events.set_defaults(func=_cmd_detect_events)

    review_events = subparsers.add_parser(
        "review-events",
        help="Print detected events with suspicious-review flags.",
    )
    review_events.add_argument("run_path", type=Path, help="Run directory or events.jsonl file.")
    review_events.add_argument(
        "--kind", "-k", choices=("all", "chapters", "at-bats"), default="all"
    )
    review_events.add_argument(
        "--corrections", type=Path, help="Optional corrections CSV to preview."
    )
    review_events.add_argument(
        "--roster", type=Path, help="Roster CSV or JSON file for roster-aware flags."
    )
    review_events.add_argument("--team-name", help="Team name override for roster CSV/JSON.")
    review_events.set_defaults(func=_cmd_review_events)

    review_report = subparsers.add_parser(
        "review-report",
        help="Write a Markdown report for questionable events with raw OCR and correction examples.",
    )
    review_report.add_argument("run_path", type=Path, help="Run directory or events.jsonl file.")
    review_report.add_argument(
        "--kind", "-k", choices=("all", "chapters", "at-bats"), default="all"
    )
    review_report.add_argument("--output", "-o", type=Path, help="Output Markdown path.")
    review_report.add_argument(
        "--roster", type=Path, help="Roster CSV or JSON file for roster-aware flags."
    )
    review_report.add_argument("--team-name", help="Team name override for roster CSV/JSON.")
    review_report.set_defaults(func=_cmd_review_report)

    export = subparsers.add_parser("export", help="Export detected events as pasteable text.")
    export.add_argument("run_path", type=Path)
    export.add_argument("--kind", "-k", choices=("chapters", "at-bats"), default="chapters")
    export.add_argument("--output", "-o", type=Path, help="Optional text output file.")
    export.add_argument(
        "--corrections", type=Path, help="Optional corrections CSV to apply before export."
    )
    export.add_argument(
        "--chapter-intro-label",
        default="Pregame",
        help="Label for the automatic 0:00 chapter when exporting chapters.",
    )
    export.add_argument(
        "--no-chapter-intro",
        action="store_true",
        help="Do not prepend an automatic 0:00 chapter when exporting chapters.",
    )
    export.add_argument(
        "--no-at-bat-inning-headers",
        action="store_true",
        help="Do not add inning headers when exporting at-bats.",
    )
    export.set_defaults(func=_cmd_export)

    publish_helper = subparsers.add_parser(
        "publish-helper",
        help="Create a game-named Markdown paste kit for YouTube publishing.",
    )
    publish_helper.add_argument("run_path", type=Path, help="Run directory.")
    publish_helper.add_argument("--chapters", type=Path, help="Chapters text file.")
    publish_helper.add_argument("--at-bats", type=Path, help="At-bats text file.")
    publish_helper.add_argument("--output", "-o", type=Path, help="Output Markdown file.")
    publish_helper.add_argument(
        "--output-dir",
        type=Path,
        help="Base output directory when --output is not supplied. Defaults to RUN/exports.",
    )
    publish_helper.add_argument(
        "--no-html",
        action="store_true",
        help="Only write the Markdown paste kit; skip the HTML copy helper.",
    )
    publish_helper.add_argument(
        "--game-name", help="Override game name used in the kit title and folder."
    )
    publish_helper.set_defaults(func=_cmd_publish_helper)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except YTDLPError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OCRBackendUnavailable, OCRError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except json.JSONDecodeError as error:
        print(f"Error: invalid JSON: {error}", file=sys.stderr)
        return 1
    except (ValueError, FileNotFoundError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
