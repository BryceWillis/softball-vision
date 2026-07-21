"""YouTube download helpers backed by the in-process ``yt_dlp`` API.

Downloads run through ``yt_dlp.YoutubeDL`` imported into this process rather
than a ``yt-dlp`` executable found on PATH. The frozen ``.app`` bundle has no
PATH worth trusting and no external Python to run ``-m yt_dlp`` with, so the
imported module is the only resolution that works in both worlds — and it
makes source and bundle runs use provably the same yt-dlp version (the one
the package declares), instead of whatever a host happened to have installed.
"""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from sidelinehd_extractor.build_info import running_frozen

DEFAULT_OUTPUT_TEMPLATE = "%(upload_date>%Y%m%d)s_%(id)s_%(title).200B.%(ext)s"
# Sentinel default: builders resolve ffmpeg automatically unless the caller
# passes an explicit location (or None to omit the setting entirely).
_AUTO_FFMPEG = object()
DEFAULT_FORMAT_SELECTOR = "best[ext=mp4]/best"
DEFAULT_YOUTUBE_CLIENT = "android"
YTDLP_REINSTALL_MESSAGE = (
    "yt-dlp is required and ships with this package. Reinstall with "
    "`pip install -e .` so the declared dependency is available."
)
YTDLP_BUNDLE_DAMAGED_MESSAGE = (
    "This app includes its own video downloader, but this copy of the app "
    "failed to load it. Download a fresh copy of the app from the Releases "
    "page and replace this one."
)
# Streams in these live_status values have no processed VOD yet, so download
# failures are expected rather than actionable errors.
LIVE_STATUSES_STILL_PROCESSING = frozenset({"is_live", "post_live"})
# Last yt-dlp release observed to download just-ended (post_live) streams;
# 2026.7.4 fails on every player client for them (CR-55).
KNOWN_GOOD_YTDLP_VERSION = "2025.10.14"


@dataclass(frozen=True)
class DownloadOptions:
    """yt-dlp download knobs — the single source of their defaults.

    The download-layer sibling of ``DetectionConfig`` and ``SamplingOptions``
    (M4 / CR-47): the run entry points forward one of these untouched instead
    of re-declaring five knobs at every hop, and the CLI's ``default=`` values
    reference it.

    ``youtube_client`` is ``None`` when the yt-dlp player-client override is
    disabled; the CLI maps its ``''`` sentinel to ``None`` on the way in, so
    the emptiness convention stays at the CLI boundary.
    """

    format_selector: str = DEFAULT_FORMAT_SELECTOR
    merge_output_format: str = "mp4"
    write_info_json: bool = True
    no_playlist: bool = True
    youtube_client: Optional[str] = DEFAULT_YOUTUBE_CLIENT


@dataclass(frozen=True)
class DownloadResult:
    """Summary of a yt-dlp download."""

    url: str
    output_dir: Path
    video_path: Optional[Path]
    options: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PlaylistEntry:
    """One video entry discovered from a YouTube playlist."""

    video_id: str
    url: str
    title: str
    index: int


class YTDLPError(RuntimeError):
    """Raised when a yt-dlp operation fails."""

    def __init__(self, details: str) -> None:
        details = details.strip() or "yt-dlp did not provide error output"
        super().__init__(f"yt-dlp failed: {details}")


class LiveStreamNotReadyError(YTDLPError):
    """Raised when a download failed because the stream just ended.

    YouTube keeps ``live_status`` at ``post_live`` until the VOD is processed;
    downloads fail during that window even though metadata extraction
    succeeds. The message replaces the raw yt-dlp error with plain-language
    guidance because waiting — not debugging — is the fix.
    """

    def __init__(
        self,
        details: str,
        live_status: str,
        ytdlp_version: Optional[str],
    ) -> None:
        super().__init__(details)
        self.live_status = live_status
        self.ytdlp_version = ytdlp_version
        self.args = (
            "This game just ended and YouTube is still processing the video. "
            "Wait about an hour and try again.\n"
            f"(Installed yt-dlp {ytdlp_version or 'unknown version'} could not "
            f"download the just-ended stream; version {KNOWN_GOOD_YTDLP_VERSION} "
            "is known to handle these.)",
        )


def ytdlp_install_hint() -> str:
    """Actionable fix for a missing yt-dlp module, aware of frozen bundles.

    A frozen app must never advise ``pip`` — there is no environment to
    install into, so the only real fix is a fresh download of the app.
    """

    if running_frozen():
        return YTDLP_BUNDLE_DAMAGED_MESSAGE
    return YTDLP_REINSTALL_MESSAGE


def load_ytdlp_module():
    """Import and return ``yt_dlp``, raising an actionable error if absent.

    Raises ``FileNotFoundError`` (the same contract the old PATH-based
    resolver had) so preflight and callers keep one exception to handle.
    """

    try:
        import yt_dlp
    except ImportError as exc:
        raise FileNotFoundError(ytdlp_install_hint()) from exc
    return yt_dlp


def ytdlp_available() -> bool:
    """True when the ``yt_dlp`` module can be imported."""

    return importlib.util.find_spec("yt_dlp") is not None


def installed_ytdlp_version(ydl_module=None) -> Optional[str]:
    """Return the imported yt-dlp version string, or None when unavailable."""

    if ydl_module is None:
        try:
            ydl_module = load_ytdlp_module()
        except FileNotFoundError:
            return None
    version = getattr(ydl_module, "version", None)
    return getattr(version, "__version__", None)


def build_ytdlp_options(
    output_dir: Path,
    download_options: DownloadOptions = DownloadOptions(),
    output_template: str = DEFAULT_OUTPUT_TEMPLATE,
    ffmpeg_location: object = _AUTO_FFMPEG,
) -> Dict[str, object]:
    """Build the ``YoutubeDL`` download options used by the CLI and web app.

    Mirrors the flag set the tool historically passed to the ``yt-dlp``
    command line, translated to API parameter names.
    """

    options: Dict[str, object] = {
        "paths": {"home": str(output_dir.expanduser())},
        "outtmpl": output_template,
        "format": download_options.format_selector,
        "merge_output_format": download_options.merge_output_format,
        "restrictfilenames": True,
        "overwrites": False,
        "noplaylist": download_options.no_playlist,
        "writeinfojson": download_options.write_info_json,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    if download_options.youtube_client:
        options["extractor_args"] = {
            "youtube": {"player_client": [download_options.youtube_client]}
        }
    if ffmpeg_location is _AUTO_FFMPEG:
        ffmpeg_location = resolve_ffmpeg_location()
    if ffmpeg_location:
        options["ffmpeg_location"] = str(ffmpeg_location)
    return options


def _probe_options(youtube_client: Optional[str]) -> Dict[str, object]:
    options: Dict[str, object] = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    if youtube_client:
        options["extractor_args"] = {"youtube": {"player_client": [youtube_client]}}
    return options


def resolve_ffmpeg_location() -> Optional[str]:
    """Return a usable ffmpeg path: system binary, else the pip-bundled build.

    Prefers an ``ffmpeg`` already on PATH; otherwise falls back to the static
    build shipped by the ``imageio-ffmpeg`` dependency. Returns ``None`` when
    neither is available so callers can degrade to guidance instead of failing.
    Safe to call with the module absent.
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


def downloaded_video_path(info: object) -> Optional[Path]:
    """Return the final downloaded file path from an ``extract_info`` result.

    ``requested_downloads`` carries the post-move, post-merge ``filepath`` —
    the API equivalent of the old ``--print after_move:filepath``.
    """

    if not isinstance(info, dict):
        return None
    downloads = info.get("requested_downloads")
    if isinstance(downloads, list):
        for download in downloads:
            if isinstance(download, dict) and download.get("filepath"):
                return Path(str(download["filepath"])).expanduser()
    filepath = info.get("filepath")
    if filepath:
        return Path(str(filepath)).expanduser()
    return None


def download_youtube_video(
    url: str,
    output_dir: Path,
    download_options: DownloadOptions = DownloadOptions(),
    output_template: str = DEFAULT_OUTPUT_TEMPLATE,
    ydl_module=None,
) -> DownloadResult:
    """Download a YouTube URL in-process and return the resulting local path."""

    destination = output_dir.expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    options = build_ytdlp_options(
        output_dir=destination,
        download_options=download_options,
        output_template=output_template,
    )
    module = ydl_module if ydl_module is not None else load_ytdlp_module()
    try:
        with module.YoutubeDL(dict(options)) as ydl:
            info = ydl.extract_info(url, download=True)
    except module.utils.DownloadError as exc:
        raise _download_failure_error(
            url,
            exc,
            youtube_client=download_options.youtube_client,
            ydl_module=module,
        ) from exc

    return DownloadResult(
        url=url,
        output_dir=destination,
        video_path=downloaded_video_path(info),
        options=options,
    )


def _download_failure_error(
    url: str,
    exc: Exception,
    youtube_client: Optional[str],
    ydl_module,
) -> YTDLPError:
    """Build the error for a failed download, probing only after failure.

    The metadata probe costs nothing on the happy path and turns the raw
    "This live event has ended" failure into wait-and-retry guidance when the
    stream's VOD simply is not processed yet (CR-55).
    """

    live_status = probe_live_status(url, youtube_client=youtube_client, ydl_module=ydl_module)
    if live_status in LIVE_STATUSES_STILL_PROCESSING:
        return LiveStreamNotReadyError(
            str(exc),
            live_status=live_status,
            ytdlp_version=installed_ytdlp_version(ydl_module),
        )
    return YTDLPError(str(exc))


def probe_live_status(
    url: str,
    youtube_client: Optional[str] = DEFAULT_YOUTUBE_CLIENT,
    ydl_module=None,
) -> Optional[str]:
    """Return a URL's yt-dlp ``live_status``, or None when the probe fails."""

    try:
        module = ydl_module if ydl_module is not None else load_ytdlp_module()
        with module.YoutubeDL(_probe_options(youtube_client)) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return None
    if not isinstance(info, dict):
        return None
    live_status = info.get("live_status")
    return str(live_status) if live_status else None


def list_playlist_videos(
    playlist_url: str,
    youtube_client: Optional[str] = DEFAULT_YOUTUBE_CLIENT,
    ydl_module=None,
) -> List[PlaylistEntry]:
    """Return YouTube playlist entries without downloading video media."""

    options = _probe_options(youtube_client)
    options["extract_flat"] = "in_playlist"
    module = ydl_module if ydl_module is not None else load_ytdlp_module()
    try:
        with module.YoutubeDL(options) as ydl:
            data = ydl.extract_info(playlist_url, download=False)
    except module.utils.DownloadError as exc:
        raise YTDLPError(str(exc)) from exc

    if not isinstance(data, dict):
        return []
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
