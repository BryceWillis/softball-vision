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
    YTDLP_BUNDLE_DAMAGED_MESSAGE,
    YTDLP_REINSTALL_MESSAGE,
    LiveStreamNotReadyError,
    YTDLPError,
    build_ytdlp_options,
    download_youtube_video,
    downloaded_video_path,
    extract_video_id,
    installed_ytdlp_version,
    list_playlist_videos,
    load_ytdlp_module,
    probe_live_status,
    resolve_ffmpeg_location,
    youtube_watch_url,
    ytdlp_install_hint,
)


class _FakeDownloadError(Exception):
    pass


class _FakeYoutubeDL:
    def __init__(self, module, options):
        self._module = module
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def extract_info(self, url, download=False):
        self._module.calls.append(
            {"url": url, "download": download, "options": self.options}
        )
        return self._module.extract(url, download, self.options)


class _FakeYtdlpModule:
    """Stands in for the imported ``yt_dlp`` module.

    ``extract`` is called as ``extract(url, download, options)`` and may raise
    ``self.utils.DownloadError`` to simulate a failure.
    """

    def __init__(self, extract, version="2026.7.4"):
        self.extract = extract
        self.calls = []
        self.utils = types.SimpleNamespace(DownloadError=_FakeDownloadError)
        if version is not None:
            self.version = types.SimpleNamespace(__version__=version)

    def YoutubeDL(self, options):
        return _FakeYoutubeDL(self, options)


def _failing_download_module(live_status_info, version="2026.7.4"):
    """Module stub: download fails; the metadata probe answers as configured."""

    def extract(url, download, options):
        if download:
            raise _FakeDownloadError("ERROR: This live event has ended.")
        if isinstance(live_status_info, Exception):
            raise live_status_info
        return live_status_info

    return _FakeYtdlpModule(extract, version=version)


class YoutubeTests(unittest.TestCase):
    def test_build_ytdlp_options_maps_download_settings(self):
        with patch(
            "sidelinehd_extractor.youtube.resolve_ffmpeg_location",
            return_value=None,
        ):
            options = build_ytdlp_options(Path("videos"), write_info_json=False)

        self.assertEqual(options["paths"], {"home": "videos"})
        self.assertEqual(options["format"], DEFAULT_FORMAT_SELECTOR)
        self.assertEqual(options["merge_output_format"], "mp4")
        self.assertTrue(options["restrictfilenames"])
        self.assertFalse(options["overwrites"])
        self.assertTrue(options["noplaylist"])
        self.assertFalse(options["writeinfojson"])
        self.assertTrue(options["quiet"])
        self.assertEqual(
            options["extractor_args"],
            {"youtube": {"player_client": [DEFAULT_YOUTUBE_CLIENT]}},
        )

    def test_build_ytdlp_options_omits_client_when_disabled(self):
        with patch(
            "sidelinehd_extractor.youtube.resolve_ffmpeg_location",
            return_value=None,
        ):
            options = build_ytdlp_options(Path("videos"), youtube_client=None)

        self.assertNotIn("extractor_args", options)

    def test_build_ytdlp_options_includes_ffmpeg_location_when_resolved(self):
        with patch(
            "sidelinehd_extractor.youtube.resolve_ffmpeg_location",
            return_value="/opt/ffmpeg/ffmpeg",
        ):
            options = build_ytdlp_options(Path("videos"))

        self.assertEqual(options["ffmpeg_location"], "/opt/ffmpeg/ffmpeg")

    def test_build_ytdlp_options_omits_ffmpeg_location_when_unresolved(self):
        with patch(
            "sidelinehd_extractor.youtube.resolve_ffmpeg_location",
            return_value=None,
        ):
            options = build_ytdlp_options(Path("videos"))

        self.assertNotIn("ffmpeg_location", options)

    def test_build_ytdlp_options_explicit_none_skips_resolution(self):
        with patch(
            "sidelinehd_extractor.youtube.resolve_ffmpeg_location",
            side_effect=AssertionError("explicit None must not trigger resolution"),
        ):
            options = build_ytdlp_options(Path("videos"), ffmpeg_location=None)

        self.assertNotIn("ffmpeg_location", options)

    def test_download_runs_in_process_and_returns_final_path(self):
        def extract(url, download, options):
            self.assertTrue(download)
            return {"requested_downloads": [{"filepath": "videos/final.mp4"}]}

        module = _FakeYtdlpModule(extract)
        with tempfile.TemporaryDirectory() as tmp:
            result = download_youtube_video(
                "https://www.youtube.com/watch?v=abc123",
                output_dir=Path(tmp),
                ydl_module=module,
            )

            self.assertEqual(result.video_path, Path("videos/final.mp4"))
            self.assertEqual(result.output_dir, Path(tmp))
            self.assertEqual(len(module.calls), 1)
            self.assertEqual(module.calls[0]["options"]["paths"], {"home": tmp})
            self.assertEqual(result.options["paths"], {"home": tmp})

    def test_download_returns_none_path_when_ytdlp_reports_none(self):
        module = _FakeYtdlpModule(lambda url, download, options: {"id": "abc123"})
        with tempfile.TemporaryDirectory() as tmp:
            result = download_youtube_video(
                "https://www.youtube.com/watch?v=abc123",
                output_dir=Path(tmp),
                ydl_module=module,
            )

        self.assertIsNone(result.video_path)

    def _download_with_module(self, module):
        with tempfile.TemporaryDirectory() as tmp:
            download_youtube_video(
                "https://www.youtube.com/live/abc123def45",
                output_dir=Path(tmp),
                ydl_module=module,
            )

    def test_download_failure_on_post_live_stream_gives_wait_guidance(self):
        module = _failing_download_module({"live_status": "post_live"})

        with self.assertRaises(LiveStreamNotReadyError) as ctx:
            self._download_with_module(module)

        message = str(ctx.exception)
        self.assertIn("still processing", message)
        self.assertIn("Wait about an hour", message)
        self.assertIn("2026.7.4", message)
        self.assertIn(KNOWN_GOOD_YTDLP_VERSION, message)
        self.assertNotIn("This live event has ended", message)
        self.assertEqual(ctx.exception.live_status, "post_live")

    def test_download_failure_on_normal_video_keeps_original_error(self):
        module = _failing_download_module({"live_status": "not_live"})

        with self.assertRaises(YTDLPError) as ctx:
            self._download_with_module(module)

        self.assertNotIsInstance(ctx.exception, LiveStreamNotReadyError)
        self.assertIn("This live event has ended", str(ctx.exception))

    def test_download_failure_with_failing_probe_keeps_original_error(self):
        module = _failing_download_module(_FakeDownloadError("probe boom"))

        with self.assertRaises(YTDLPError) as ctx:
            self._download_with_module(module)

        self.assertNotIsInstance(ctx.exception, LiveStreamNotReadyError)
        self.assertIn("This live event has ended", str(ctx.exception))

    def test_download_failure_message_handles_unknown_ytdlp_version(self):
        module = _failing_download_module({"live_status": "post_live"}, version=None)

        with self.assertRaises(LiveStreamNotReadyError) as ctx:
            self._download_with_module(module)

        self.assertIn("unknown version", str(ctx.exception))

    def test_probe_live_status_returns_status(self):
        module = _FakeYtdlpModule(
            lambda url, download, options: {"live_status": "post_live"}
        )

        status = probe_live_status(
            "https://www.youtube.com/live/abc123def45", ydl_module=module
        )

        self.assertEqual(status, "post_live")
        self.assertFalse(module.calls[0]["download"])
        self.assertTrue(module.calls[0]["options"]["skip_download"])

    def test_probe_live_status_returns_none_when_probe_raises(self):
        def extract(url, download, options):
            raise OSError("no network")

        status = probe_live_status(
            "https://www.youtube.com/live/abc123def45",
            ydl_module=_FakeYtdlpModule(extract),
        )

        self.assertIsNone(status)

    def test_list_playlist_videos_parses_flat_playlist_entries(self):
        entries = {
            "entries": [
                {"id": "abc123", "title": "Game One", "playlist_index": 2},
                {"id": "def456", "title": "Game Two", "url": "https://youtu.be/def456"},
            ]
        }
        module = _FakeYtdlpModule(lambda url, download, options: entries)

        result = list_playlist_videos(
            "https://youtube.com/playlist?list=abc", ydl_module=module
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].video_id, "abc123")
        self.assertEqual(result[0].url, "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(result[0].index, 2)
        self.assertEqual(result[1].url, "https://youtu.be/def456")
        self.assertEqual(module.calls[0]["options"]["extract_flat"], "in_playlist")
        self.assertFalse(module.calls[0]["download"])

    def test_list_playlist_videos_raises_ytdlp_error_on_failure(self):
        def extract(url, download, options):
            raise _FakeDownloadError("ERROR: playlist does not exist")

        with self.assertRaises(YTDLPError) as ctx:
            list_playlist_videos(
                "https://youtube.com/playlist?list=abc",
                ydl_module=_FakeYtdlpModule(extract),
            )

        self.assertIn("playlist does not exist", str(ctx.exception))

    def test_load_ytdlp_module_raises_actionable_error_when_absent(self):
        with patch.dict(sys.modules, {"yt_dlp": None}):
            with self.assertRaises(FileNotFoundError) as context:
                load_ytdlp_module()

        self.assertIn("yt-dlp is required", str(context.exception))
        self.assertIn("pip install -e .", str(context.exception))

    def test_ytdlp_install_hint_never_mentions_pip_when_frozen(self):
        with patch(
            "sidelinehd_extractor.youtube.running_frozen", return_value=True
        ):
            hint = ytdlp_install_hint()

        self.assertEqual(hint, YTDLP_BUNDLE_DAMAGED_MESSAGE)
        self.assertNotIn("pip", hint)
        self.assertNotIn("brew", hint)

    def test_ytdlp_install_hint_advises_reinstall_from_source(self):
        with patch(
            "sidelinehd_extractor.youtube.running_frozen", return_value=False
        ):
            self.assertEqual(ytdlp_install_hint(), YTDLP_REINSTALL_MESSAGE)

    def test_installed_ytdlp_version_reads_module_version(self):
        module = _FakeYtdlpModule(lambda url, download, options: {})

        self.assertEqual(installed_ytdlp_version(module), "2026.7.4")

    def test_installed_ytdlp_version_none_when_module_missing(self):
        with patch.dict(sys.modules, {"yt_dlp": None}):
            self.assertIsNone(installed_ytdlp_version())

    def test_downloaded_video_path_prefers_requested_downloads(self):
        info = {
            "filepath": "videos/other.mp4",
            "requested_downloads": [{"filepath": "videos/final.mp4"}],
        }

        self.assertEqual(downloaded_video_path(info), Path("videos/final.mp4"))

    def test_downloaded_video_path_falls_back_to_filepath(self):
        self.assertEqual(
            downloaded_video_path({"filepath": "videos/final.mp4"}),
            Path("videos/final.mp4"),
        )

    def test_downloaded_video_path_returns_none_without_path(self):
        self.assertIsNone(downloaded_video_path({"id": "abc123"}))
        self.assertIsNone(downloaded_video_path(None))

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

    def test_ytdlp_error_includes_details(self):
        error = YTDLPError("actual yt-dlp problem")

        self.assertIn("actual yt-dlp problem", str(error))

    def test_ytdlp_error_empty_details_gets_placeholder(self):
        self.assertIn("did not provide error output", str(YTDLPError("  ")))

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


if __name__ == "__main__":
    unittest.main()
