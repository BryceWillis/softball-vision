"""YouTube download helpers backed by the external yt-dlp command."""

from __future__ import annotations

import shutil
import subprocess
import sys
import json
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import List, Optional, Sequence


DEFAULT_OUTPUT_TEMPLATE = "%(upload_date>%Y%m%d)s_%(id)s_%(title).200B.%(ext)s"
DEFAULT_FORMAT_SELECTOR = "best[ext=mp4]/best"
DEFAULT_YOUTUBE_CLIENT = "android"


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
) -> List[str]:
    """Build the yt-dlp command used by the CLI."""

    command = list(executable or ["yt-dlp"]) + [
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
    command.append(url)
    return command


def build_ytdlp_playlist_command(
    playlist_url: str,
    youtube_client: Optional[str] = DEFAULT_YOUTUBE_CLIENT,
    executable: Optional[Sequence[str]] = None,
) -> List[str]:
    """Build a cheap flat-playlist enumeration command."""

    command = list(executable or ["yt-dlp"]) + [
        "--flat-playlist",
        "--dump-single-json",
        "--no-warnings",
    ]
    if youtube_client:
        command.extend(["--extractor-args", f"youtube:player_client={youtube_client}"])
    command.append(playlist_url)
    return command


def resolve_ytdlp_executable() -> List[str]:
    """Return a runnable yt-dlp command prefix."""

    executable = shutil.which("yt-dlp")
    if executable is not None:
        return [executable]
    if find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    raise FileNotFoundError(
        "yt-dlp was not found on PATH or as a Python module. Install it first, then rerun the "
        "download command."
    )


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

    executable = resolve_ytdlp_executable()
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
        executable=executable,
    )
    completed = runner(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise YTDLPError(command, completed.returncode, completed.stdout, completed.stderr)

    video_path = parse_downloaded_video_path(completed.stdout)
    return DownloadResult(
        url=url,
        output_dir=destination,
        video_path=video_path,
        command=command,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def list_playlist_videos(
    playlist_url: str,
    youtube_client: Optional[str] = DEFAULT_YOUTUBE_CLIENT,
    runner=subprocess.run,
) -> List[PlaylistEntry]:
    """Return YouTube playlist entries without downloading video media."""

    executable = resolve_ytdlp_executable()
    command = build_ytdlp_playlist_command(
        playlist_url=playlist_url,
        youtube_client=youtube_client,
        executable=executable,
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


def command_as_string(command: Sequence[str]) -> str:
    """Render a command for display without shell-specific quoting cleverness."""

    return " ".join(command)
