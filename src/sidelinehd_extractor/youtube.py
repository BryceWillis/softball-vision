"""YouTube download helpers backed by the external yt-dlp command."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence
from urllib.parse import parse_qs, urlparse


DEFAULT_OUTPUT_TEMPLATE = "%(upload_date>%Y%m%d)s_%(id)s_%(title).200B.%(ext)s"
# Sentinel default: builders resolve ffmpeg automatically unless the caller
# passes an explicit location (or None to omit the flag entirely).
_AUTO_FFMPEG = object()
DEFAULT_FORMAT_SELECTOR = "best[ext=mp4]/best"
DEFAULT_YOUTUBE_CLIENT = "android"
YTDLP_REINSTALL_MESSAGE = (
    "yt-dlp is required and ships with this package. Reinstall with "
    "`pip install -e .` so the declared dependency is available."
)
# Streams in these live_status values have no processed VOD yet, so download
# failures are expected rather than actionable errors.
LIVE_STATUSES_STILL_PROCESSING = frozenset({"is_live", "post_live"})
# Last yt-dlp release observed to download just-ended (post_live) streams;
# 2026.7.4 fails on every player client for them (CR-55).
KNOWN_GOOD_YTDLP_VERSION = "2025.10.14"


@dataclass(frozen=True)
class DownloadResult:
    """Summary of a yt-dlp download."""

    url: str
    output_dir: Path
    video_path: Optional[Path]
    command: List[str]
    stdout: str
    stderr: str


@dataclass(frozen=True)
class PlaylistEntry:
    """One video entry discovered from a YouTube playlist."""

    video_id: str
    url: str
    title: str
    index: int


class YTDLPError(RuntimeError):
    """Raised when yt-dlp exits unsuccessfully."""

    def __init__(self, command: Sequence[str], returncode: int, stdout: str, stderr: str) -> None:
        self.command = list(command)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        details = stderr.strip() or stdout.strip() or "yt-dlp did not provide error output"
        super().__init__(
            f"yt-dlp failed with exit code {returncode}\n"
            f"Command: {command_as_string(command)}\n"
            f"{details}"
        )


class LiveStreamNotReadyError(YTDLPError):
    """Raised when a download failed because the stream just ended.

    YouTube keeps ``live_status`` at ``post_live`` until the VOD is processed;
    downloads fail during that window even though ``-F`` format listing
    succeeds. The message replaces the raw yt-dlp error with plain-language
    guidance because waiting — not debugging — is the fix.
    """

    def __init__(
        self,
        command: Sequence[str],
        returncode: int,
        stdout: str,
        stderr: str,
        live_status: str,
        ytdlp_version: Optional[str],
    ) -> None:
        super().__init__(command, returncode, stdout, stderr)
        self.live_status = live_status
        self.ytdlp_version = ytdlp_version
        self.args = (
            "This game just ended and YouTube is still processing the video. "
            "Wait about an hour and try again.\n"
            f"(Installed yt-dlp {ytdlp_version or 'unknown version'} could not "
            f"download the just-ended stream; version {KNOWN_GOOD_YTDLP_VERSION} "
            "is known to handle these.)",
        )


def build_ytdlp_command(
    url: str,
    output_dir: Path,
    format_selector: str = DEFAULT_FORMAT_SELECTOR,
    output_template: str = DEFAULT_OUTPUT_TEMPLATE,
    merge_output_format: str = "mp4",
    write_info_json: bool = True,
    no_playlist: bool = True,
    youtube_client: Optional[str] = DEFAULT_YOUTUBE_CLIENT,
    executable: Optional[Sequence[str]] = None,
    ffmpeg_location: object = _AUTO_FFMPEG,
) -> List[str]:
    """Build the yt-dlp command used by the CLI."""

    command_prefix = list(executable) if executable is not None else default_ytdlp_executable()
    command = command_prefix + [
        "--paths",
        str(output_dir.expanduser()),
        "--output",
        output_template,
        "--format",
        format_selector,
        "--merge-output-format",
        merge_output_format,
        "--restrict-filenames",
        "--no-overwrites",
        "--print",
        "after_move:filepath",
    ]
    if no_playlist:
        command.append("--no-playlist")
    if write_info_json:
        command.append("--write-info-json")
    if youtube_client:
        command.extend(["--extractor-args", f"youtube:player_client={youtube_client}"])
    _extend_with_ffmpeg_location(command, ffmpeg_location)
    command.append(url)
    return command


def build_ytdlp_playlist_command(
    playlist_url: str,
    youtube_client: Optional[str] = DEFAULT_YOUTUBE_CLIENT,
    executable: Optional[Sequence[str]] = None,
    ffmpeg_location: object = _AUTO_FFMPEG,
) -> List[str]:
    """Build a cheap flat-playlist enumeration command."""

    command_prefix = list(executable) if executable is not None else default_ytdlp_executable()
    command = command_prefix + [
        "--flat-playlist",
        "--dump-single-json",
        "--no-warnings",
    ]
    if youtube_client:
        command.extend(["--extractor-args", f"youtube:player_client={youtube_client}"])
    _extend_with_ffmpeg_location(command, ffmpeg_location)
    command.append(playlist_url)
    return command


def _extend_with_ffmpeg_location(command: List[str], ffmpeg_location: object) -> None:
    if ffmpeg_location is _AUTO_FFMPEG:
        ffmpeg_location = resolve_ffmpeg_location()
    if ffmpeg_location:
        command.extend(["--ffmpeg-location", str(ffmpeg_location)])


def resolve_ffmpeg_location() -> Optional[str]:
    """Return a usable ffmpeg path: system binary, else the pip-bundled build.

    Prefers an ``ffmpeg`` already on PATH; otherwise falls back to the static
    build shipped by the ``imageio-ffmpeg`` dependency. Returns ``None`` when
    neither is available so callers can degrade to guidance instead of failing.
    Mirrors the item-53 yt-dlp resolver: safe to call with the module absent.
    """

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg is not None:
        return system_ffmpeg
    if importlib.util.find_spec("imageio_ffmpeg") is None:
        return None
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, OSError, RuntimeError):
        return None


def default_ytdlp_executable() -> List[str]:
    """Return the default runnable yt-dlp command prefix."""

    executable = shutil.which("yt-dlp")
    if executable is not None:
        return [executable]
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    raise FileNotFoundError(YTDLP_REINSTALL_MESSAGE)


def resolve_ytdlp_executable() -> List[str]:
    """Return a runnable yt-dlp command prefix."""

    return default_ytdlp_executable()


def parse_downloaded_video_path(stdout: str) -> Optional[Path]:
    """Return the last likely video path printed by yt-dlp."""

    video_extensions = {".mp4", ".mkv", ".mov", ".webm", ".m4v"}
    for line in reversed(stdout.splitlines()):
        value = line.strip()
        if not value:
            continue
        path = Path(value).expanduser()
        if path.suffix.lower() in video_extensions:
            return path
    return None


def download_youtube_video(
    url: str,
    output_dir: Path,
    format_selector: str = DEFAULT_FORMAT_SELECTOR,
    output_template: str = DEFAULT_OUTPUT_TEMPLATE,
    merge_output_format: str = "mp4",
    write_info_json: bool = True,
    no_playlist: bool = True,
    youtube_client: Optional[str] = DEFAULT_YOUTUBE_CLIENT,
    runner=subprocess.run,
) -> DownloadResult:
    """Download a YouTube URL with yt-dlp and return the resulting local path."""

    destination = output_dir.expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    command = build_ytdlp_command(
        url=url,
        output_dir=destination,
        format_selector=format_selector,
        output_template=output_template,
        merge_output_format=merge_output_format,
        write_info_json=write_info_json,
        no_playlist=no_playlist,
        youtube_client=youtube_client,
    )
    completed = runner(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise _download_failure_error(
            command,
            completed,
            url=url,
            youtube_client=youtube_client,
            runner=runner,
        )

    video_path = parse_downloaded_video_path(completed.stdout)
    return DownloadResult(
        url=url,
        output_dir=destination,
        video_path=video_path,
        command=command,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _download_failure_error(
    command: Sequence[str],
    completed,
    url: str,
    youtube_client: Optional[str],
    runner,
) -> YTDLPError:
    """Build the error for a failed download, probing only after failure.

    The metadata probe costs nothing on the happy path and turns the raw
    "This live event has ended" failure into wait-and-retry guidance when the
    stream's VOD simply is not processed yet (CR-55).
    """

    live_status = probe_live_status(url, youtube_client=youtube_client, runner=runner)
    if live_status in LIVE_STATUSES_STILL_PROCESSING:
        return LiveStreamNotReadyError(
            command,
            completed.returncode,
            completed.stdout,
            completed.stderr,
            live_status=live_status,
            ytdlp_version=installed_ytdlp_version(runner=runner),
        )
    return YTDLPError(command, completed.returncode, completed.stdout, completed.stderr)


def probe_live_status(
    url: str,
    youtube_client: Optional[str] = DEFAULT_YOUTUBE_CLIENT,
    runner=subprocess.run,
) -> Optional[str]:
    """Return a URL's yt-dlp ``live_status``, or None when the probe fails."""

    try:
        command = default_ytdlp_executable() + [
            "--skip-download",
            "--no-warnings",
            "--print",
            "live_status",
        ]
        if youtube_client:
            command.extend(["--extractor-args", f"youtube:player_client={youtube_client}"])
        command.append(url)
        completed = runner(command, check=False, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else None


def installed_ytdlp_version(runner=subprocess.run) -> Optional[str]:
    """Return the installed yt-dlp version string, or None when unavailable."""

    try:
        command = default_ytdlp_executable() + ["--version"]
        completed = runner(command, check=False, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def list_playlist_videos(
    playlist_url: str,
    youtube_client: Optional[str] = DEFAULT_YOUTUBE_CLIENT,
    runner=subprocess.run,
) -> List[PlaylistEntry]:
    """Return YouTube playlist entries without downloading video media."""

    command = build_ytdlp_playlist_command(
        playlist_url=playlist_url,
        youtube_client=youtube_client,
    )
    completed = runner(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise YTDLPError(command, completed.returncode, completed.stdout, completed.stderr)

    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("yt-dlp returned invalid playlist JSON") from exc

    entries = data.get("entries")
    if not isinstance(entries, list):
        return []
    result = []
    for fallback_index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue
        video_id = str(entry.get("id") or "").strip()
        url = _playlist_entry_url(entry, video_id)
        if not video_id and not url:
            continue
        title = str(entry.get("title") or video_id or url).strip()
        index = _playlist_entry_index(entry, fallback_index)
        result.append(
            PlaylistEntry(
                video_id=video_id or url,
                url=url,
                title=title,
                index=index,
            )
        )
    return result


def _playlist_entry_url(entry: dict, video_id: str) -> str:
    url = str(entry.get("webpage_url") or entry.get("url") or "").strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return url


def _playlist_entry_index(entry: dict, fallback: int) -> int:
    value = entry.get("playlist_index")
    if value is None:
        value = entry.get("playlist_autonumber")
    if value is None:
        value = fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def youtube_watch_url(video_id: str, seconds: float) -> str:
    """Watch URL that opens ``video_id`` at ``seconds``, floored to whole seconds.

    YouTube's ``t`` parameter is integer seconds; timestamps are non-negative,
    so truncation is a floor.
    """

    return f"https://www.youtube.com/watch?v={video_id}&t={int(seconds)}s"


def extract_video_id(url: str) -> Optional[str]:
    """Best-effort video id from a YouTube URL, or None when unrecognizable.

    Handles ``watch?v=``, ``youtu.be/<id>`` short links, and the ``shorts``/
    ``live``/``embed`` path forms.
    """

    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if host == "youtu.be":
        return path_segments[0] if path_segments else None
    if host == "youtube.com" or host.endswith(".youtube.com"):
        query_id = parse_qs(parsed.query).get("v", [""])[0]
        if query_id:
            return query_id
        if len(path_segments) >= 2 and path_segments[0] in {"shorts", "live", "embed"}:
            return path_segments[1]
    return None


def command_as_string(command: Sequence[str]) -> str:
    """Render a command for display without shell-specific quoting cleverness."""

    return " ".join(command)
