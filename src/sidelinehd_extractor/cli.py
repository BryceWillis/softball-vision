"""Command-line interface for the local extraction pipeline."""

from __future__ import annotations

import argparse
import errno
import json
import socket
import sys
import webbrowser
from pathlib import Path
from typing import Callable, List, Optional

from sidelinehd_extractor.batch import run_playlist_batch
from sidelinehd_extractor.calibration import (
    extract_calibration_frames,
    parse_timestamp_list,
    parse_timestamp_value,
    render_template_guide,
)
from sidelinehd_extractor.crops import extract_crop_from_video, save_crop
from sidelinehd_extractor.config import (
    CONFIG_FILENAME,
    ProjectConfig,
    load_configured_roster,
    load_overlay_template,
    load_project_config,
    load_project_config_values,
    load_roster,
    set_default_roster_config,
    write_project_config,
)
from sidelinehd_extractor.corrections import (
    apply_event_corrections,
    load_event_corrections,
    remove_event_correction,
    write_event_corrections,
)
from sidelinehd_extractor.events import DetectionConfig, detect_events_file, load_events
from sidelinehd_extractor.exports import export_at_bat_comment, export_youtube_chapters
from sidelinehd_extractor.feedback import write_feedback_log
from sidelinehd_extractor.models import HalfInning, RegionFraction, Roster
from sidelinehd_extractor.ocr import (
    OCRBackendUnavailable,
    OCRError,
    create_ocr_backend,
    ocr_image_file,
    write_preprocessed_image,
)
from sidelinehd_extractor.preflight import preflight_dependencies
from sidelinehd_extractor.publish import write_publish_kit
from sidelinehd_extractor.processing import SamplingOptions, process_video
from sidelinehd_extractor.review import render_event_review
from sidelinehd_extractor.review_report import write_review_report
from sidelinehd_extractor.roster import (
    default_roster_path,
    existing_roster_path,
    is_configured_default,
    parse_team_list,
    write_roster_csv,
)
from sidelinehd_extractor.serialization import to_plain_data
from sidelinehd_extractor.state import parse_samples_file
from sidelinehd_extractor.video import probe_video, read_frame_at
from sidelinehd_extractor.workflow import export_paths as workflow_export_paths
from sidelinehd_extractor.workflow import (
    ExportOptions,
    finalize_run_exports,
    run_game,
    run_youtube_game,
)
from sidelinehd_extractor.webapp.lifecycle import (
    ORIGIN_APP,
    ServerStateRegistration,
    git_short_sha,
    is_pid_alive,
    read_server_state,
    restart_decline_message,
    status_message,
    stop_recorded_server,
    unregistered_warning,
    version_display,
)
from sidelinehd_extractor.youtube import (
    DownloadOptions,
    YTDLPError,
    download_youtube_video,
)


#: The corrections file name written into every run dir (mirrors the web app's
#: ``CORRECTIONS_FILENAME``); ``clear-corrections`` reads and rewrites it.
CORRECTIONS_FILENAME = "corrections.csv"


def _to_json(value: object) -> str:
    return json.dumps(to_plain_data(value), indent=2)


def _next_commands(run_dir: object) -> list:
    """Follow-up review commands for a finished run.

    Item 19: uses the installed console script with double-quoted paths so the
    commands are copy/pasteable on macOS/Linux shells, PowerShell, and cmd.exe
    alike (single quotes are literal characters in cmd.exe).
    """

    return [
        f'sidelinehd-extractor review-events "{run_dir}" --kind at-bats',
        f'sidelinehd-extractor review-events "{run_dir}" --kind chapters',
    ]


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


def _build_batch_progress_callback() -> Callable[[str], None]:
    def progress(message: str) -> None:
        print(f"run-playlist: {message}", file=sys.stderr, flush=True)

    return progress


def _default_run_fields(args: argparse.Namespace) -> List[str]:
    return _parse_field_list(args.field) or [
        "inning",
        "count",
        "left_score",
        "right_score",
        "game_status",
        "lineup_strip",
        "batter_card_name",
        "batter_card_number",
        "batter_number",
    ]


#: The one source of the pipeline defaults the parsers advertise. Every
#: ``default=`` below reads a field off one of these instead of repeating a
#: literal, so a tuning change lands in the dataclass alone (M4 / CR-47).
_DETECTION_DEFAULTS = DetectionConfig()
_EXPORT_DEFAULTS = ExportOptions()
_SAMPLING_DEFAULTS = SamplingOptions()
_DOWNLOAD_DEFAULTS = DownloadOptions()


def _parse_batting_half(value: str) -> Optional[HalfInning]:
    if value == "top":
        return HalfInning.TOP
    if value == "bottom":
        return HalfInning.BOTTOM
    return None


def _is_auto_batting_half(value: str) -> bool:
    return value == "auto"


def _detection_config_from_args(args: argparse.Namespace) -> DetectionConfig:
    """Build the detection config every run/detect command shares.

    ``detect-events`` offers no ``auto`` choice for ``--batting-half`` — half
    inference runs in ``run_game``, above ``detect_events_file`` — so for that
    command ``_is_auto_batting_half`` is simply always False.
    """

    return DetectionConfig(
        batting_half=_parse_batting_half(args.batting_half),
        auto_detect_batting_half=_is_auto_batting_half(args.batting_half),
        min_at_bat_spacing_seconds=args.min_at_bat_spacing,
        min_at_bat_spacing_roster_confirmed_seconds=args.min_at_bat_spacing_roster_confirmed,
        min_game_final_observations=args.min_game_final_observations,
        order_validation=not args.no_order_validation,
    )


def _export_options_from_args(args: argparse.Namespace) -> ExportOptions:
    """Build the export formatting options the run commands share."""

    return ExportOptions(
        include_chapter_intro=not args.no_chapter_intro,
        chapter_intro_label=args.chapter_intro_label,
        include_inning_score=not args.no_inning_score,
        include_at_bat_inning_headers=not args.no_at_bat_inning_headers,
    )


def _sampling_options_from_args(args: argparse.Namespace) -> SamplingOptions:
    """Build the sampling options every run command shares."""

    return SamplingOptions(
        sample_every_seconds=args.sample_every,
        start_seconds=parse_timestamp_value(args.start),
        end_seconds=parse_timestamp_value(args.end) if args.end else None,
        fields=tuple(_default_run_fields(args)),
        save_crops=args.save_crops,
        compute_video_hash=args.hash_video,
        ocr_workers=args.ocr_workers,
    )


def _download_options_from_args(args: argparse.Namespace) -> DownloadOptions:
    """Build the yt-dlp download options every downloading command shares.

    ``--youtube-client ''`` disables the player-client override; that empty
    sentinel is a CLI convention, so it is mapped to ``None`` here rather than
    stored in the dataclass.

    ``run-playlist`` deliberately has no ``--playlist`` flag — it walks the
    playlist itself and downloads one video per entry — so it falls back to
    the single-video default here, which the batch path then enforces anyway.
    """

    return DownloadOptions(
        format_selector=args.format,
        merge_output_format=args.merge_output_format,
        write_info_json=not args.no_info_json,
        no_playlist=not getattr(args, "playlist", False),
        youtube_client=args.youtube_client or None,
    )


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


def _apply_config_defaults(
    args: argparse.Namespace,
    use_roster: bool = False,
    use_template: bool = False,
    use_team_name: bool = True,
) -> None:
    """Apply ``sidelinehd.cfg`` values where the user did not pass CLI flags."""

    config = load_project_config()
    if use_roster and hasattr(args, "roster") and not getattr(args, "roster"):
        args.roster = config.roster
    if use_template and hasattr(args, "template") and not getattr(args, "template"):
        args.template = config.template
    if use_team_name and hasattr(args, "team_name") and not getattr(args, "team_name"):
        args.team_name = config.team_name


def _cmd_download(args: argparse.Namespace) -> int:
    result = download_youtube_video(
        url=args.url,
        output_dir=args.output_dir,
        download_options=_download_options_from_args(args),
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
        download_options=_download_options_from_args(args),
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
    _apply_config_defaults(args, use_template=True, use_team_name=False)
    template = load_overlay_template(args.template) if args.template else None
    roster = load_roster(args.roster, team_name=args.team_name) if args.roster else None
    ocr_backend = create_ocr_backend(args.ocr)
    result = process_video(
        video_path=args.video_path,
        output_dir=args.output_dir,
        template=template,
        roster=roster,
        ocr=ocr_backend,
        progress=None if args.quiet else _build_progress_callback(args.progress_every),
        sampling=SamplingOptions(
            sample_every_seconds=args.sample_every,
            start_seconds=parse_timestamp_value(args.start),
            end_seconds=parse_timestamp_value(args.end) if args.end else None,
            # The audit command keeps crops on by default and defaults to every
            # template field; the run commands do neither.
            fields=_parse_field_list(args.field),
            save_crops=not args.no_crops,
            compute_video_hash=args.hash_video,
            ocr_workers=args.ocr_workers,
        ),
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
        _offer_config_update(result.output_path, team_name=team_name)
        print("")
        print("Use your roster:")
        print(f"  {_format_roster_next_command(result.output_path)}")
    return 0


def _cmd_delete_roster(args: argparse.Namespace) -> int:
    # 70e: the CLI half of POST /rosters/{slug}/delete. The slug guard and the
    # default-roster fact come from the same helpers the route uses; the browser
    # confirm becomes --yes (or an interactive prompt). UnknownRoster (a
    # ValueError) bubbles to main() for a clean "Error: ..." on a bad/missing slug.
    path = existing_roster_path(args.slug)
    if not args.yes:
        if is_configured_default(path):
            consequence = (
                f"'{args.slug}' is the configured default roster; deleting it means runs "
                "will not match roster names until you set a new default."
            )
        else:
            consequence = f"Delete roster '{args.slug}' ({path})?"
        if not sys.stdin.isatty():
            print(f"Error: {consequence} Re-run with --yes to confirm.", file=sys.stderr)
            return 1
        response = input(f"{consequence} Delete it? [y/N] ").strip().lower()
        if response not in {"y", "yes"}:
            print("Cancelled.", file=sys.stderr)
            return 1
    path.unlink()
    print(f"Deleted {path}")
    return 0


def _cmd_set_default_roster(args: argparse.Namespace) -> int:
    # 70e: the CLI half of POST /rosters/{slug}/set-default, through the same
    # config writer, so the template and any unmanaged key are preserved.
    path = existing_roster_path(args.slug)
    written = set_default_roster_config(path)
    print(f"Default roster set to {path} (wrote {written})")
    return 0


def _cmd_clear_corrections(args: argparse.Namespace) -> int:
    # 70e: the CLI half of POST /jobs/{job_id}/corrections/clear. Mirrors the
    # route's granularity — the UI clears one (event_type, timestamp, field)
    # correction; --all clears every one — then re-exports through the same tail
    # so the on-disk artifacts and corrections.csv cannot disagree.
    corrections_path = args.run / CORRECTIONS_FILENAME
    if not corrections_path.exists():
        print(f"No corrections file at {corrections_path}; nothing to clear.")
        return 0

    existing = load_event_corrections(corrections_path)
    if args.all:
        remaining: list = []
    else:
        if not args.timestamp or not args.field:
            print(
                "Error: specify --all, or both --timestamp and --field to identify the "
                "correction to clear.",
                file=sys.stderr,
            )
            return 1
        key = (
            (args.event_type or "").strip(),
            round(parse_timestamp_value(args.timestamp), 3),
            args.field.strip(),
        )
        remaining = remove_event_correction(existing, key)

    if len(remaining) == len(existing):
        # Absent file handled above; here the file exists but the selector
        # matched nothing (or --all on an already-empty file). Idempotent no-op.
        print("No matching corrections to clear.")
        return 0

    write_event_corrections(corrections_path, remaining)
    finalize_run_exports(args.run, corrections=remaining, roster=load_configured_roster())
    cleared = len(existing) - len(remaining)
    print(f"Cleared {cleared} correction(s); {len(remaining)} remaining. Re-exported {args.run}.")
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
    # Item 19: double quotes so the suggestion pastes cleanly on Windows
    # shells too (cmd.exe treats single quotes as literal characters).
    return (
        'sidelinehd-extractor run-youtube "YOUTUBE_URL" '
        f"--roster {roster_path} "
        "--template YOUR_TEMPLATE"
    )


def _offer_config_update(
    roster_path: Path,
    team_name: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> None:
    root = cwd or Path.cwd()
    config_path = root / CONFIG_FILENAME
    existing_values = load_project_config_values(cwd=root)
    existing_roster = _config_path_value(existing_values.get("roster"))
    if existing_roster == roster_path:
        return

    verb = "Update" if config_path.exists() else "Create"
    response = (
        input(f"\n{verb} {CONFIG_FILENAME} to use this roster by default? [Y/n] ")
        .strip()
        .lower()
    )
    if response and response not in {"y", "yes"}:
        return

    template = _config_path_value(existing_values.get("template"))
    if template is None:
        template_input = input("Template path (Enter to skip): ").strip()
        template = Path(template_input) if template_input else None

    written = write_project_config(
        ProjectConfig(
            roster=roster_path,
            template=template,
            team_name=existing_values.get("team_name") or team_name,
        ),
        cwd=root,
    )
    print(f"Wrote {written}")


def _config_path_value(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    stripped = value.strip()
    return Path(stripped) if stripped else None


def _cmd_run_game(args: argparse.Namespace) -> int:
    _apply_config_defaults(args, use_roster=True, use_template=True)
    template = load_overlay_template(args.template) if args.template else None
    roster = load_roster(args.roster, team_name=args.team_name) if args.roster else None
    ocr_backend = create_ocr_backend(args.ocr)
    corrections = load_event_corrections(args.corrections) if args.corrections else None
    result = run_game(
        video_path=args.video_path,
        output_dir=args.output_dir,
        template=template,
        roster=roster,
        ocr=ocr_backend,
        progress=None if args.quiet else _build_progress_callback(args.progress_every),
        output_prefix=args.output_prefix,
        corrections=corrections,
        stage_progress=None if args.quiet else _build_stage_callback(),
        sampling=_sampling_options_from_args(args),
        export_options=_export_options_from_args(args),
        detection=_detection_config_from_args(args),
        auto_detect_template=not args.no_auto_template,
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
                "next_commands": _next_commands(result.run_dir),
            }
        )
    )
    return 0


def _cmd_run_youtube(args: argparse.Namespace) -> int:
    _apply_config_defaults(args, use_roster=True, use_template=True)
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
        ocr=ocr_backend,
        progress=None if args.quiet else _build_progress_callback(args.progress_every),
        output_prefix=args.output_prefix,
        corrections=corrections,
        stage_progress=None if args.quiet else _build_stage_callback(),
        sampling=_sampling_options_from_args(args),
        export_options=_export_options_from_args(args),
        detection=_detection_config_from_args(args),
        download_options=_download_options_from_args(args),
        auto_detect_template=not args.no_auto_template,
        batting_half_inference_progress=(
            None if args.quiet else _build_batting_half_inference_callback()
        ),
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
                "next_commands": _next_commands(run.run_dir),
            }
        )
    )
    return 0


def _cmd_run_playlist(args: argparse.Namespace) -> int:
    _apply_config_defaults(args, use_roster=True, use_template=True)
    template = load_overlay_template(args.template) if args.template else None
    roster = load_roster(args.roster, team_name=args.team_name) if args.roster else None
    ocr_backend = create_ocr_backend(args.ocr)
    corrections = load_event_corrections(args.corrections) if args.corrections else None
    result = run_playlist_batch(
        playlist_url=args.url,
        video_dir=args.video_dir,
        output_dir=args.output_dir,
        template=template,
        roster=roster,
        ocr=ocr_backend,
        progress=None if args.quiet else _build_progress_callback(args.progress_every),
        output_prefix=args.output_prefix,
        corrections=corrections,
        stage_progress=None if args.quiet else _build_stage_callback(),
        sampling=_sampling_options_from_args(args),
        export_options=_export_options_from_args(args),
        detection=_detection_config_from_args(args),
        download_options=_download_options_from_args(args),
        auto_detect_template=not args.no_auto_template,
        batting_half_inference_progress=(
            None if args.quiet else _build_batting_half_inference_callback()
        ),
        force=args.force,
        limit=args.limit,
        start_index=args.start_index,
        retries=args.retries,
        batch_progress=None if args.quiet else _build_batch_progress_callback(),
    )
    print(_to_json(result))
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
    _apply_config_defaults(args, use_roster=True, use_template=False)
    roster = load_roster(args.roster, team_name=args.team_name) if args.roster else None
    result = detect_events_file(
        input_path,
        output_path=args.output,
        roster=roster,
        config=_detection_config_from_args(args),
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
            include_score=not args.no_inning_score,
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


def _cmd_feedback(args: argparse.Namespace) -> int:
    result = write_feedback_log(
        run_path=args.run_path,
        output_path=args.output,
        note=args.note,
    )
    print(result.output_path)
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    uvicorn = _load_uvicorn_or_report()
    if uvicorn is None:
        return 1
    if _port_in_use(args.host, args.port):
        _print_port_in_use(args.host, args.port)
        return 1
    registration = ServerStateRegistration(args.host, args.port)
    with registration as state:
        _warn_if_unregistered(registration)
        print(
            f"Serving {version_display(state.version, git_short_sha())} on {state.url}",
            file=sys.stderr,
            flush=True,
        )
        uvicorn.run(
            "sidelinehd_extractor.webapp.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    return 0


def _load_uvicorn_or_report():
    try:
        import uvicorn

        from sidelinehd_extractor.webapp.app import create_app  # noqa: F401
    except ImportError as error:
        print(
            "Error: the local web app requires the optional web dependencies "
            f"({error}). Install them with: pip install -e \".[web]\"",
            file=sys.stderr,
        )
        return None
    return uvicorn


def _port_in_use(host: str, port: int) -> bool:
    """Return True when binding host:port fails because it is already taken."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError as error:
            return error.errno in (errno.EADDRINUSE, errno.EACCES)
    return False


def _recorded_server_for_port(host: str, port: int):
    state = read_server_state()
    if state is None or state.host != host or state.port != port:
        return None
    return state


def _print_port_in_use(host: str, port: int) -> None:
    state = _recorded_server_for_port(host, port)
    if state is not None:
        print(
            "A sidelinehd-extractor server is already running here "
            f"(PID {state.pid}, started {state.started_at}). Use `restart` to reload it, "
            "or `stop` to shut it down.",
            file=sys.stderr,
        )
        return
    print(
        f"Error: port {port} on {host} is already in use — is the app "
        f"already running? Pick another port with --port (e.g. --port {port + 1}).",
        file=sys.stderr,
    )


def _print_preflight_report() -> None:
    """Print dependency health; missing deps get their install hint, no abort."""

    for status in preflight_dependencies():
        if status["ok"]:
            print(f"  [ok] {status['name']}: {status['detail']}")
        else:
            print(f"  [missing] {status['name']}: {status['detail']}")
            if status["install_hint"]:
                print(f"            To fix: {status['install_hint']}")


def _cmd_start(args: argparse.Namespace) -> int:
    uvicorn = _load_uvicorn_or_report()
    if uvicorn is None:
        return 1

    print("Checking dependencies...")
    _print_preflight_report()

    if _port_in_use(args.host, args.port):
        _print_port_in_use(args.host, args.port)
        return 1

    url = f"http://{args.host}:{args.port}"
    registration = ServerStateRegistration(args.host, args.port)
    with registration as state:
        _warn_if_unregistered(registration)
        print(
            f"Serving {version_display(state.version, git_short_sha())} on {url} "
            "— press Ctrl+C here to stop.",
            flush=True,
        )
        if not args.no_browser:
            webbrowser.open(url)
        try:
            uvicorn.run(
                "sidelinehd_extractor.webapp.app:create_app",
                factory=True,
                host=args.host,
                port=args.port,
            )
        except KeyboardInterrupt:
            pass
    print("Stopped.")
    return 0


def _warn_if_unregistered(registration: ServerStateRegistration) -> None:
    """Say so when another live server kept the record (item 70a).

    Serving unregistered is survivable here — and only here — because `start`
    and `serve` are foreground commands with a terminal attached, so Ctrl+C is
    always available. Silence would not be: `status` and `stop` would go on
    naming the *other* server with nothing to explain why.
    """

    if registration.registered or registration.conflict is None:
        return
    print(
        f"{unregistered_warning(registration.conflict)} "
        "Press Ctrl+C here to stop this server.",
        file=sys.stderr,
        flush=True,
    )


def _cmd_stop(args: argparse.Namespace) -> int:
    message = stop_recorded_server()
    print(message)
    if message == "No running server recorded." and _port_in_use(args.host, args.port):
        print(
            f"Port {args.port} on {args.host} is in use, but no "
            "sidelinehd-extractor server state was found.",
            file=sys.stderr,
        )
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    print(status_message())
    return 0


def _cmd_restart(args: argparse.Namespace) -> int:
    # Item 70a: the CLI cannot respawn an `.app` it did not start, so a live
    # desktop-app record is declined rather than half-honoured — stopping it
    # and then starting a *CLI* server in its place would be a worse surprise
    # than saying no. A stale app record is not a reason to decline: it blocks
    # nothing, and the stop below clears it.
    state = read_server_state()
    if state is not None and state.origin == ORIGIN_APP and is_pid_alive(state.pid):
        print(restart_decline_message(state), file=sys.stderr)
        return 1
    print(stop_recorded_server())
    return _cmd_start(args)


def _add_run_processing_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", "-o", type=Path, default=Path("runs"))
    parser.add_argument("--template", type=Path, help="Overlay template JSON file.")
    parser.add_argument(
        "--no-auto-template",
        action="store_true",
        help=(
            "Skip the pre-run template probe and use the packaged default "
            "template as-is (only relevant when --template is not given)."
        ),
    )
    parser.add_argument("--roster", type=Path, help="Roster CSV or JSON file.")
    parser.add_argument("--team-name", help="Team name override for roster CSV/JSON.")
    parser.add_argument(
        "--sample-every",
        type=float,
        default=_SAMPLING_DEFAULTS.sample_every_seconds,
        help="Seconds between sampled frames.",
    )
    parser.add_argument(
        "--start",
        # A timestamp string, parsed back to seconds — but its default is the
        # dataclass's, not a literal of its own.
        default=str(_SAMPLING_DEFAULTS.start_seconds),
        help="Start timestamp as seconds, M:SS, or H:MM:SS.",
    )
    parser.add_argument("--end", help="Optional end timestamp as seconds, M:SS, or H:MM:SS.")
    parser.add_argument("--ocr", choices=("none", "tesseract", "tesserocr"), default="tesseract")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Print progress every N sampled timestamps.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output.")
    parser.add_argument(
        "--ocr-workers",
        type=int,
        default=_SAMPLING_DEFAULTS.ocr_workers,
        metavar="N",
        help="OCR worker threads. Defaults to the detected CPU count; use 1 for serial OCR.",
    )
    parser.add_argument(
        "--field",
        action="append",
        default=[],
        help=(
            "Template field to process. Repeatable or comma-separated. Defaults to "
            "inning,count,left_score,right_score,lineup_strip,batter_card_name,"
            "batter_card_number,batter_number."
        ),
    )
    parser.add_argument(
        "--save-crops",
        action="store_true",
        help="Write crop image files for OCR debugging. Disabled by default for runs.",
    )
    parser.add_argument(
        "--no-crops",
        action="store_false",
        dest="save_crops",
        help=argparse.SUPPRESS,
    )
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
        default=_EXPORT_DEFAULTS.chapter_intro_label,
        help="Label for the automatic 0:00 chapter when the first chapter starts later.",
    )
    parser.add_argument(
        "--no-chapter-intro",
        action="store_true",
        help="Do not prepend an automatic 0:00 chapter.",
    )
    parser.add_argument(
        "--no-inning-score",
        action="store_true",
        help="Do not append score snapshots to inning chapter labels.",
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
        default=_DETECTION_DEFAULTS.min_at_bat_spacing_seconds,
        help="Minimum seconds between emitted at-bat starts.",
    )
    parser.add_argument(
        "--min-at-bat-spacing-roster-confirmed",
        type=float,
        default=_DETECTION_DEFAULTS.min_at_bat_spacing_roster_confirmed_seconds,
        dest="min_at_bat_spacing_roster_confirmed",
        metavar="SECONDS",
        help="Minimum seconds between at-bats when the new batter is roster-confirmed.",
    )
    parser.add_argument(
        "--min-game-final-observations",
        type=int,
        default=_DETECTION_DEFAULTS.min_game_final_observations,
        help="Minimum consecutive FINAL scorebug OCR reads before emitting a Final chapter.",
    )
    parser.add_argument(
        "--no-order-validation",
        action="store_true",
        help="Skip batting-order continuity validation after event detection.",
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
        "--format", default=_DOWNLOAD_DEFAULTS.format_selector, help="yt-dlp format selector."
    )
    download.add_argument("--merge-output-format", default=_DOWNLOAD_DEFAULTS.merge_output_format)
    download.add_argument(
        "--youtube-client",
        default=_DOWNLOAD_DEFAULTS.youtube_client,
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
        default=_DOWNLOAD_DEFAULTS.format_selector,
        help="yt-dlp format selector.",
    )
    prepare_youtube.add_argument("--merge-output-format", default=_DOWNLOAD_DEFAULTS.merge_output_format)
    prepare_youtube.add_argument(
        "--youtube-client",
        default=_DOWNLOAD_DEFAULTS.youtube_client,
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
    ocr_image.add_argument("--ocr", choices=("none", "tesseract", "tesserocr"), default="tesseract")
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
        default=_SAMPLING_DEFAULTS.sample_every_seconds,
        help="Seconds between sampled frames.",
    )
    process.add_argument(
        "--start",
        default=str(_SAMPLING_DEFAULTS.start_seconds),
        help="Start timestamp as seconds, M:SS, or H:MM:SS.",
    )
    process.add_argument("--end", help="Optional end timestamp as seconds, M:SS, or H:MM:SS.")
    process.add_argument("--ocr", choices=("none", "tesseract", "tesserocr"), default="none")
    process.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Print progress every N sampled timestamps.",
    )
    process.add_argument("--quiet", action="store_true", help="Suppress progress output.")
    process.add_argument(
        "--ocr-workers",
        type=int,
        default=_SAMPLING_DEFAULTS.ocr_workers,
        metavar="N",
        help="OCR worker threads. Defaults to the detected CPU count; use 1 for serial OCR.",
    )
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

    delete_roster = subparsers.add_parser(
        "delete-roster",
        help="Delete a roster CSV from rosters/ by its slug.",
    )
    delete_roster.add_argument(
        "slug", help="Roster slug — the rosters/<slug>.csv filename stem, not a path."
    )
    delete_roster.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip the confirmation prompt (required to delete non-interactively).",
    )
    delete_roster.set_defaults(func=_cmd_delete_roster)

    set_default_roster = subparsers.add_parser(
        "set-default-roster",
        help="Make a roster in rosters/ the configured default in sidelinehd.cfg.",
    )
    set_default_roster.add_argument(
        "slug", help="Roster slug — the rosters/<slug>.csv filename stem, not a path."
    )
    set_default_roster.set_defaults(func=_cmd_set_default_roster)

    clear_corrections = subparsers.add_parser(
        "clear-corrections",
        help="Clear saved corrections for a run and re-export it.",
    )
    clear_corrections.add_argument(
        "--run", required=True, type=Path, help="Run directory holding corrections.csv."
    )
    clear_corrections.add_argument(
        "--all", action="store_true", help="Clear every saved correction for the run."
    )
    clear_corrections.add_argument(
        "--event-type",
        default="",
        help="Event type of the correction to clear (matches the corrections.csv column).",
    )
    clear_corrections.add_argument(
        "--timestamp",
        help="Timestamp of the correction to clear (seconds, M:SS, or H:MM:SS).",
    )
    clear_corrections.add_argument(
        "--field", help="Field name of the correction to clear (e.g. label, player_name)."
    )
    clear_corrections.set_defaults(func=_cmd_clear_corrections)

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
        default=_DOWNLOAD_DEFAULTS.format_selector,
        help="yt-dlp format selector.",
    )
    run_youtube.add_argument("--merge-output-format", default=_DOWNLOAD_DEFAULTS.merge_output_format)
    run_youtube.add_argument(
        "--youtube-client",
        default=_DOWNLOAD_DEFAULTS.youtube_client,
        help="YouTube player client for yt-dlp extractor args. Use '' to disable.",
    )
    run_youtube.add_argument("--no-info-json", action="store_true")
    run_youtube.add_argument("--playlist", action="store_true", help="Allow playlist downloads.")
    run_youtube.set_defaults(func=_cmd_run_youtube)

    run_playlist = subparsers.add_parser(
        "run-playlist",
        help="Process every game video in a YouTube playlist.",
    )
    run_playlist.add_argument("url")
    run_playlist.add_argument("--video-dir", type=Path, default=Path("videos"))
    _add_run_processing_arguments(run_playlist)
    run_playlist.add_argument(
        "--format",
        default=_DOWNLOAD_DEFAULTS.format_selector,
        help="yt-dlp format selector.",
    )
    run_playlist.add_argument("--merge-output-format", default=_DOWNLOAD_DEFAULTS.merge_output_format)
    run_playlist.add_argument(
        "--youtube-client",
        default=_DOWNLOAD_DEFAULTS.youtube_client,
        help="YouTube player client for yt-dlp extractor args. Use '' to disable.",
    )
    run_playlist.add_argument("--no-info-json", action="store_true")
    run_playlist.add_argument(
        "--force",
        action="store_true",
        help="Reprocess playlist entries already marked done in the batch state.",
    )
    run_playlist.add_argument("--limit", type=int, help="Process at most N playlist entries.")
    run_playlist.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="Skip the first N playlist entries before processing.",
    )
    run_playlist.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Retry each failed playlist entry this many times before marking it failed.",
    )
    run_playlist.set_defaults(func=_cmd_run_playlist)

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
        default=_DETECTION_DEFAULTS.min_at_bat_spacing_seconds,
        help="Minimum seconds between emitted at-bat starts.",
    )
    detect_events.add_argument(
        "--min-at-bat-spacing-roster-confirmed",
        type=float,
        default=_DETECTION_DEFAULTS.min_at_bat_spacing_roster_confirmed_seconds,
        dest="min_at_bat_spacing_roster_confirmed",
        metavar="SECONDS",
        help="Minimum seconds between at-bats when the new batter is roster-confirmed.",
    )
    detect_events.add_argument(
        "--min-game-final-observations",
        type=int,
        default=_DETECTION_DEFAULTS.min_game_final_observations,
        help="Minimum consecutive FINAL scorebug OCR reads before emitting a Final chapter.",
    )
    detect_events.add_argument(
        "--no-order-validation",
        action="store_true",
        help="Skip batting-order continuity validation after event detection.",
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
        default=_EXPORT_DEFAULTS.chapter_intro_label,
        help="Label for the automatic 0:00 chapter when exporting chapters.",
    )
    export.add_argument(
        "--no-chapter-intro",
        action="store_true",
        help="Do not prepend an automatic 0:00 chapter when exporting chapters.",
    )
    export.add_argument(
        "--no-inning-score",
        action="store_true",
        help="Do not append score snapshots to inning chapter labels.",
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

    feedback = subparsers.add_parser(
        "feedback",
        help="Write a sanitized Markdown feedback log for a completed run.",
    )
    feedback.add_argument("run_path", type=Path, help="Run directory.")
    feedback.add_argument("--note", help="Optional user-authored note included verbatim.")
    feedback.add_argument("--output", "-o", type=Path, help="Output Markdown path.")
    feedback.set_defaults(func=_cmd_feedback)

    serve = subparsers.add_parser(
        "serve",
        help="Run the local web UI. Requires the optional web extra: pip install -e '.[web]'.",
    )
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address. Loopback by default; the app has no auth, so do not expose it.",
    )
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument(
        "--reload",
        action="store_true",
        help="Auto-reload on source changes (development only).",
    )
    serve.set_defaults(func=_cmd_serve)

    start = subparsers.add_parser(
        "start",
        help=(
            "Start the local web app: check dependencies, open your browser, "
            "press Ctrl+C to stop."
        ),
    )
    start.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address. Loopback by default; the app has no auth, so do not expose it.",
    )
    start.add_argument("--port", type=int, default=8000)
    start.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the web browser automatically.",
    )
    start.set_defaults(func=_cmd_start)

    stop = subparsers.add_parser("stop", help="Stop the recorded local web app server.")
    stop.add_argument("--host", default="127.0.0.1", help=argparse.SUPPRESS)
    stop.add_argument("--port", type=int, default=8000, help=argparse.SUPPRESS)
    stop.set_defaults(func=_cmd_stop)

    status = subparsers.add_parser(
        "status", help="Show whether the local web app server is running."
    )
    status.set_defaults(func=_cmd_status)

    restart = subparsers.add_parser(
        "restart",
        help="Stop any recorded local web app server, then start a fresh one.",
    )
    restart.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address. Loopback by default; the app has no auth, so do not expose it.",
    )
    restart.add_argument("--port", type=int, default=8000)
    restart.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the web browser automatically.",
    )
    restart.set_defaults(func=_cmd_restart)

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
