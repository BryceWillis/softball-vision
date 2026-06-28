import unittest
from pathlib import Path
from unittest.mock import patch

from sidelinehd_extractor.youtube import (
    DEFAULT_FORMAT_SELECTOR,
    DEFAULT_YOUTUBE_CLIENT,
    YTDLPError,
    build_ytdlp_command,
    parse_downloaded_video_path,
    resolve_ytdlp_executable,
)


class YoutubeTests(unittest.TestCase):
    def test_build_ytdlp_command_uses_local_output_dir_and_prints_final_path(self):
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
        command = build_ytdlp_command(
            "https://www.youtube.com/watch?v=abc123",
            Path("videos"),
            executable=["python3", "-m", "yt_dlp"],
        )

        self.assertEqual(command[:3], ["python3", "-m", "yt_dlp"])
        self.assertIn("--paths", command)

    def test_resolve_ytdlp_executable_falls_back_to_python_module(self):
        with patch("sidelinehd_extractor.youtube.shutil.which", return_value=None):
            with patch("sidelinehd_extractor.youtube.find_spec", return_value=object()):
                command = resolve_ytdlp_executable()

        self.assertIn("-m", command)
        self.assertEqual(command[-1], "yt_dlp")

    def test_parse_downloaded_video_path_uses_last_video_path(self):
        stdout = "noise\nvideos/first.webm\nmore noise\nvideos/final.mp4\n"

        self.assertEqual(parse_downloaded_video_path(stdout), Path("videos/final.mp4"))

    def test_parse_downloaded_video_path_returns_none_without_video(self):
        self.assertIsNone(parse_downloaded_video_path("nothing useful\n"))

    def test_ytdlp_error_includes_stderr(self):
        error = YTDLPError(["yt-dlp", "url"], 1, "", "actual yt-dlp problem")

        self.assertIn("actual yt-dlp problem", str(error))
        self.assertIn("yt-dlp url", str(error))


if __name__ == "__main__":
    unittest.main()
