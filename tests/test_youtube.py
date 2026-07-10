import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from sidelinehd_extractor.youtube import (
    DEFAULT_FORMAT_SELECTOR,
    DEFAULT_YOUTUBE_CLIENT,
    KNOWN_GOOD_YTDLP_VERSION,
    LiveStreamNotReadyError,
    YTDLPError,
    build_ytdlp_playlist_command,
    build_ytdlp_command,
    default_ytdlp_executable,
    download_youtube_video,
    extract_video_id,
    list_playlist_videos,
    parse_downloaded_video_path,
    probe_live_status,
    resolve_ffmpeg_location,
    resolve_ytdlp_executable,
    youtube_watch_url,
)


class _Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _failing_download_runner(live_status_result, version_result=None):
    """Runner stub: download fails; probe/version answer as configured."""

    def runner(command, check=False, capture_output=True, text=True):
        if "--version" in command:
            return version_result or _Completed(stdout="2026.7.4\n")
        if "live_status" in command:
            return live_status_result
        return _Completed(returncode=1, stderr="ERROR: This live event has ended.")

    return runner


class YoutubeTests(unittest.TestCase):
    def test_build_ytdlp_command_uses_local_output_dir_and_prints_final_path(self):
        with patch(
            "sidelinehd_extractor.youtube.default_ytdlp_executable",
            return_value=["yt-dlp"],
        ):
            command = build_ytdlp_command(
                "https://www.youtube.com/watch?v=abc123",
                Path("videos"),
                write_info_json=False,
            )

        self.assertEqual(command[0], "yt-dlp")
        self.assertIn("--paths", command)
        self.assertIn("videos", command)
        self.assertIn("--print", command)
        self.assertIn("after_move:filepath", command)
        self.assertIn(DEFAULT_FORMAT_SELECTOR, command)
        self.assertIn("--extractor-args", command)
        self.assertIn(f"youtube:player_client={DEFAULT_YOUTUBE_CLIENT}", command)
        self.assertIn("--no-playlist", command)
        self.assertNotIn("--write-info-json", command)
        self.assertEqual(command[-1], "https://www.youtube.com/watch?v=abc123")

    def test_build_ytdlp_command_accepts_python_module_prefix(self):
        with patch(
            "sidelinehd_extractor.youtube.default_ytdlp_executable",
            side_effect=AssertionError("explicit executable should be preserved"),
        ):
            command = build_ytdlp_command(
                "https://www.youtube.com/watch?v=abc123",
                Path("videos"),
                executable=["python3", "-m", "yt_dlp"],
            )

        self.assertEqual(command[:3], ["python3", "-m", "yt_dlp"])
        self.assertIn("--paths", command)

    def test_build_ytdlp_command_uses_resolved_default(self):
        with patch(
            "sidelinehd_extractor.youtube.default_ytdlp_executable",
            return_value=["python3", "-m", "yt_dlp"],
        ):
            command = build_ytdlp_command(
                "https://www.youtube.com/watch?v=abc123",
                Path("videos"),
            )

        self.assertEqual(command[:3], ["python3", "-m", "yt_dlp"])

    def test_build_ytdlp_playlist_command_uses_flat_playlist(self):
        command = build_ytdlp_playlist_command(
            "https://youtube.com/playlist?list=abc",
            executable=["python3", "-m", "yt_dlp"],
        )

        self.assertEqual(command[:3], ["python3", "-m", "yt_dlp"])
        self.assertIn("--flat-playlist", command)
        self.assertIn("--dump-single-json", command)
        self.assertEqual(command[-1], "https://youtube.com/playlist?list=abc")

    def test_build_ytdlp_playlist_command_uses_resolved_default(self):
        with patch(
            "sidelinehd_extractor.youtube.default_ytdlp_executable",
            return_value=["python3", "-m", "yt_dlp"],
        ):
            command = build_ytdlp_playlist_command("https://youtube.com/playlist?list=abc")

        self.assertEqual(command[:3], ["python3", "-m", "yt_dlp"])
        self.assertIn("--flat-playlist", command)

    def test_list_playlist_videos_parses_flat_playlist_json(self):
        class Completed:
            returncode = 0
            stdout = (
                '{"entries": ['
                '{"id": "abc123", "title": "Game One", "playlist_index": 2},'
                '{"id": "def456", "title": "Game Two", "url": "https://youtu.be/def456"}'
                "]}"
            )
            stderr = ""

        with patch(
            "sidelinehd_extractor.youtube.default_ytdlp_executable",
            return_value=["yt-dlp"],
        ):
            entries = list_playlist_videos(
                "https://youtube.com/playlist?list=abc",
                runner=lambda *_args, **_kwargs: Completed(),
            )

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].video_id, "abc123")
        self.assertEqual(entries[0].url, "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(entries[0].index, 2)
        self.assertEqual(entries[1].url, "https://youtu.be/def456")

    def test_default_ytdlp_executable_uses_console_script_when_present(self):
        with patch(
            "sidelinehd_extractor.youtube.shutil.which",
            return_value="/usr/local/bin/yt-dlp",
        ):
            with patch(
                "sidelinehd_extractor.youtube.importlib.util.find_spec",
                side_effect=AssertionError("module fallback should not run"),
            ):
                command = default_ytdlp_executable()

        self.assertEqual(command, ["/usr/local/bin/yt-dlp"])

    def test_default_ytdlp_executable_falls_back_to_python_module(self):
        with patch("sidelinehd_extractor.youtube.shutil.which", return_value=None):
            with patch(
                "sidelinehd_extractor.youtube.importlib.util.find_spec",
                return_value=object(),
            ):
                command = default_ytdlp_executable()

        self.assertIn("-m", command)
        self.assertEqual(command[-1], "yt_dlp")

    def test_resolve_ytdlp_executable_aliases_default_helper(self):
        with patch(
            "sidelinehd_extractor.youtube.default_ytdlp_executable",
            return_value=["yt-dlp"],
        ):
            self.assertEqual(resolve_ytdlp_executable(), ["yt-dlp"])

    def test_default_ytdlp_executable_raises_actionable_error_when_absent(self):
        with patch("sidelinehd_extractor.youtube.shutil.which", return_value=None):
            with patch(
                "sidelinehd_extractor.youtube.importlib.util.find_spec",
                return_value=None,
            ):
                with self.assertRaises(FileNotFoundError) as context:
                    default_ytdlp_executable()

        self.assertIn("yt-dlp is required", str(context.exception))
        self.assertIn("pip install -e .", str(context.exception))

    def test_parse_downloaded_video_path_uses_last_video_path(self):
        stdout = "noise\nvideos/first.webm\nmore noise\nvideos/final.mp4\n"

        self.assertEqual(parse_downloaded_video_path(stdout), Path("videos/final.mp4"))

    def test_parse_downloaded_video_path_returns_none_without_video(self):
        self.assertIsNone(parse_downloaded_video_path("nothing useful\n"))

    def test_ytdlp_error_includes_stderr(self):
        error = YTDLPError(["yt-dlp", "url"], 1, "", "actual yt-dlp problem")

        self.assertIn("actual yt-dlp problem", str(error))
        self.assertIn("yt-dlp url", str(error))

    def test_resolve_ffmpeg_location_prefers_system_binary(self):
        with patch(
            "sidelinehd_extractor.youtube.shutil.which",
            return_value="/usr/local/bin/ffmpeg",
        ):
            with patch(
                "sidelinehd_extractor.youtube.importlib.util.find_spec",
                side_effect=AssertionError("bundled fallback should not run"),
            ):
                self.assertEqual(resolve_ffmpeg_location(), "/usr/local/bin/ffmpeg")

    def test_resolve_ffmpeg_location_falls_back_to_bundled_build(self):
        fake_module = types.SimpleNamespace(
            get_ffmpeg_exe=lambda: "/site-packages/imageio_ffmpeg/binaries/ffmpeg-osx64"
        )
        with patch("sidelinehd_extractor.youtube.shutil.which", return_value=None):
            with patch(
                "sidelinehd_extractor.youtube.importlib.util.find_spec",
                return_value=object(),
            ):
                with patch.dict(sys.modules, {"imageio_ffmpeg": fake_module}):
                    self.assertEqual(
                        resolve_ffmpeg_location(),
                        "/site-packages/imageio_ffmpeg/binaries/ffmpeg-osx64",
                    )

    def test_resolve_ffmpeg_location_returns_none_when_absent(self):
        with patch("sidelinehd_extractor.youtube.shutil.which", return_value=None):
            with patch(
                "sidelinehd_extractor.youtube.importlib.util.find_spec",
                return_value=None,
            ):
                self.assertIsNone(resolve_ffmpeg_location())

    def test_resolve_ffmpeg_location_returns_none_when_bundled_build_errors(self):
        def broken_exe():
            raise RuntimeError("no binary for this platform")

        fake_module = types.SimpleNamespace(get_ffmpeg_exe=broken_exe)
        with patch("sidelinehd_extractor.youtube.shutil.which", return_value=None):
            with patch(
                "sidelinehd_extractor.youtube.importlib.util.find_spec",
                return_value=object(),
            ):
                with patch.dict(sys.modules, {"imageio_ffmpeg": fake_module}):
                    self.assertIsNone(resolve_ffmpeg_location())

    def test_build_ytdlp_command_includes_ffmpeg_location_when_resolved(self):
        with patch(
            "sidelinehd_extractor.youtube.resolve_ffmpeg_location",
            return_value="/opt/ffmpeg/ffmpeg",
        ):
            command = build_ytdlp_command(
                "https://www.youtube.com/watch?v=abc123",
                Path("videos"),
                executable=["yt-dlp"],
            )

        index = command.index("--ffmpeg-location")
        self.assertEqual(command[index + 1], "/opt/ffmpeg/ffmpeg")

    def test_build_ytdlp_command_omits_ffmpeg_location_when_unresolved(self):
        with patch(
            "sidelinehd_extractor.youtube.resolve_ffmpeg_location",
            return_value=None,
        ):
            command = build_ytdlp_command(
                "https://www.youtube.com/watch?v=abc123",
                Path("videos"),
                executable=["yt-dlp"],
            )

        self.assertNotIn("--ffmpeg-location", command)

    def test_build_ytdlp_command_explicit_none_skips_resolution(self):
        with patch(
            "sidelinehd_extractor.youtube.resolve_ffmpeg_location",
            side_effect=AssertionError("explicit None must not trigger resolution"),
        ):
            command = build_ytdlp_command(
                "https://www.youtube.com/watch?v=abc123",
                Path("videos"),
                executable=["yt-dlp"],
                ffmpeg_location=None,
            )

        self.assertNotIn("--ffmpeg-location", command)

    def test_build_ytdlp_playlist_command_includes_ffmpeg_location_when_resolved(self):
        with patch(
            "sidelinehd_extractor.youtube.resolve_ffmpeg_location",
            return_value="/opt/ffmpeg/ffmpeg",
        ):
            command = build_ytdlp_playlist_command(
                "https://youtube.com/playlist?list=abc",
                executable=["yt-dlp"],
            )

        index = command.index("--ffmpeg-location")
        self.assertEqual(command[index + 1], "/opt/ffmpeg/ffmpeg")

    def test_youtube_watch_url_builds_timestamped_link(self):
        self.assertEqual(
            youtube_watch_url("abc123", 2375),
            "https://www.youtube.com/watch?v=abc123&t=2375s",
        )

    def test_youtube_watch_url_floors_fractional_seconds(self):
        self.assertEqual(
            youtube_watch_url("abc123", 2375.9),
            "https://www.youtube.com/watch?v=abc123&t=2375s",
        )

    def test_youtube_watch_url_zero_seconds_is_valid(self):
        self.assertEqual(
            youtube_watch_url("abc123", 0),
            "https://www.youtube.com/watch?v=abc123&t=0s",
        )

    def test_extract_video_id_from_watch_url(self):
        self.assertEqual(
            extract_video_id("https://www.youtube.com/watch?v=abc123def45&list=PL1"),
            "abc123def45",
        )

    def test_extract_video_id_from_short_link(self):
        self.assertEqual(
            extract_video_id("https://youtu.be/abc123def45?t=12"),
            "abc123def45",
        )

    def test_extract_video_id_from_path_forms(self):
        self.assertEqual(
            extract_video_id("https://www.youtube.com/live/abc123def45"),
            "abc123def45",
        )
        self.assertEqual(
            extract_video_id("https://youtube.com/shorts/abc123def45"),
            "abc123def45",
        )
        self.assertEqual(
            extract_video_id("https://www.youtube.com/embed/abc123def45"),
            "abc123def45",
        )

    def test_extract_video_id_unrecognizable_returns_none(self):
        self.assertIsNone(extract_video_id("https://example.com/watch?v=abc123"))
        self.assertIsNone(extract_video_id("https://www.youtube.com/playlist?list=PL1"))
        self.assertIsNone(extract_video_id("not a url"))

    def _download_with_runner(self, runner):
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "sidelinehd_extractor.youtube.default_ytdlp_executable",
                return_value=["yt-dlp"],
            ):
                download_youtube_video(
                    "https://www.youtube.com/live/abc123def45",
                    output_dir=Path(tmp),
                    runner=runner,
                )

    def test_download_failure_on_post_live_stream_gives_wait_guidance(self):
        runner = _failing_download_runner(_Completed(stdout="post_live\n"))

        with self.assertRaises(LiveStreamNotReadyError) as ctx:
            self._download_with_runner(runner)

        message = str(ctx.exception)
        self.assertIn("still processing", message)
        self.assertIn("Wait about an hour", message)
        self.assertIn("2026.7.4", message)
        self.assertIn(KNOWN_GOOD_YTDLP_VERSION, message)
        self.assertNotIn("This live event has ended", message)
        self.assertEqual(ctx.exception.live_status, "post_live")

    def test_download_failure_on_normal_video_keeps_original_error(self):
        runner = _failing_download_runner(_Completed(stdout="not_live\n"))

        with self.assertRaises(YTDLPError) as ctx:
            self._download_with_runner(runner)

        self.assertNotIsInstance(ctx.exception, LiveStreamNotReadyError)
        self.assertIn("This live event has ended", str(ctx.exception))

    def test_download_failure_with_failing_probe_keeps_original_error(self):
        runner = _failing_download_runner(_Completed(returncode=1, stderr="probe boom"))

        with self.assertRaises(YTDLPError) as ctx:
            self._download_with_runner(runner)

        self.assertNotIsInstance(ctx.exception, LiveStreamNotReadyError)
        self.assertIn("This live event has ended", str(ctx.exception))

    def test_download_failure_message_handles_unknown_ytdlp_version(self):
        runner = _failing_download_runner(
            _Completed(stdout="post_live\n"),
            version_result=_Completed(returncode=1),
        )

        with self.assertRaises(LiveStreamNotReadyError) as ctx:
            self._download_with_runner(runner)

        self.assertIn("unknown version", str(ctx.exception))

    def test_probe_live_status_returns_status_line(self):
        def runner(command, check=False, capture_output=True, text=True):
            self.assertIn("--skip-download", command)
            self.assertIn("live_status", command)
            return _Completed(stdout="post_live\n")

        with patch(
            "sidelinehd_extractor.youtube.default_ytdlp_executable",
            return_value=["yt-dlp"],
        ):
            status = probe_live_status(
                "https://www.youtube.com/live/abc123def45", runner=runner
            )

        self.assertEqual(status, "post_live")

    def test_probe_live_status_returns_none_when_probe_raises(self):
        def runner(command, check=False, capture_output=True, text=True):
            raise OSError("no yt-dlp")

        with patch(
            "sidelinehd_extractor.youtube.default_ytdlp_executable",
            return_value=["yt-dlp"],
        ):
            status = probe_live_status(
                "https://www.youtube.com/live/abc123def45", runner=runner
            )

        self.assertIsNone(status)


if __name__ == "__main__":
    unittest.main()
