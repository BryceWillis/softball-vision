"""Tests for the dependency preflight report (item 54a)."""

import unittest
from unittest.mock import patch

from sidelinehd_extractor.preflight import (
    FFMPEG_REINSTALL_MESSAGE,
    missing_dependencies,
    preflight_dependencies,
)
from sidelinehd_extractor.youtube import YTDLP_REINSTALL_MESSAGE


def _by_name(statuses):
    return {status["name"]: status for status in statuses}


class PreflightTests(unittest.TestCase):
    def test_all_dependencies_present(self):
        with patch(
            "sidelinehd_extractor.preflight.default_ytdlp_executable",
            return_value=["/usr/local/bin/yt-dlp"],
        ), patch(
            "sidelinehd_extractor.preflight.resolve_ffmpeg_location",
            return_value="/usr/local/bin/ffmpeg",
        ), patch(
            "sidelinehd_extractor.preflight.shutil.which",
            return_value="/usr/local/bin/tesseract",
        ), patch(
            "sidelinehd_extractor.preflight.tesseract_version",
            return_value="5.3.4",
        ):
            statuses = preflight_dependencies()

        report = _by_name(statuses)
        self.assertEqual(set(report), {"yt-dlp", "ffmpeg", "tesseract"})
        self.assertTrue(all(status["ok"] for status in statuses))
        self.assertEqual(report["yt-dlp"]["detail"], "/usr/local/bin/yt-dlp")
        self.assertEqual(report["ffmpeg"]["detail"], "/usr/local/bin/ffmpeg")
        self.assertEqual(report["tesseract"]["detail"], "version 5.3.4")
        self.assertTrue(all(status["install_hint"] is None for status in statuses))
        self.assertEqual(missing_dependencies(statuses), [])

    def test_missing_ytdlp_reports_reinstall_hint(self):
        with patch(
            "sidelinehd_extractor.preflight.default_ytdlp_executable",
            side_effect=FileNotFoundError(YTDLP_REINSTALL_MESSAGE),
        ), patch(
            "sidelinehd_extractor.preflight.resolve_ffmpeg_location",
            return_value="/usr/local/bin/ffmpeg",
        ), patch(
            "sidelinehd_extractor.preflight.shutil.which",
            return_value="/usr/local/bin/tesseract",
        ), patch(
            "sidelinehd_extractor.preflight.tesseract_version",
            return_value="5.3.4",
        ):
            statuses = preflight_dependencies()

        status = _by_name(statuses)["yt-dlp"]
        self.assertFalse(status["ok"])
        self.assertEqual(status["install_hint"], YTDLP_REINSTALL_MESSAGE)
        self.assertEqual(missing_dependencies(statuses), [status])

    def test_missing_ffmpeg_reports_reinstall_hint(self):
        with patch(
            "sidelinehd_extractor.preflight.default_ytdlp_executable",
            return_value=["yt-dlp"],
        ), patch(
            "sidelinehd_extractor.preflight.resolve_ffmpeg_location",
            return_value=None,
        ), patch(
            "sidelinehd_extractor.preflight.shutil.which",
            return_value="/usr/local/bin/tesseract",
        ), patch(
            "sidelinehd_extractor.preflight.tesseract_version",
            return_value="5.3.4",
        ):
            statuses = preflight_dependencies()

        status = _by_name(statuses)["ffmpeg"]
        self.assertFalse(status["ok"])
        self.assertEqual(status["install_hint"], FFMPEG_REINSTALL_MESSAGE)

    def test_missing_tesseract_reports_os_install_hint(self):
        with patch(
            "sidelinehd_extractor.preflight.default_ytdlp_executable",
            return_value=["yt-dlp"],
        ), patch(
            "sidelinehd_extractor.preflight.resolve_ffmpeg_location",
            return_value="/usr/local/bin/ffmpeg",
        ), patch(
            "sidelinehd_extractor.preflight.shutil.which",
            return_value=None,
        ), patch(
            "sidelinehd_extractor.preflight.tesseract_install_hint",
            return_value="Install it with `brew install tesseract`.",
        ):
            statuses = preflight_dependencies()

        status = _by_name(statuses)["tesseract"]
        self.assertFalse(status["ok"])
        self.assertIn("brew install tesseract", status["install_hint"])

    def test_tesseract_present_with_unknown_version(self):
        with patch(
            "sidelinehd_extractor.preflight.default_ytdlp_executable",
            return_value=["yt-dlp"],
        ), patch(
            "sidelinehd_extractor.preflight.resolve_ffmpeg_location",
            return_value="/usr/local/bin/ffmpeg",
        ), patch(
            "sidelinehd_extractor.preflight.shutil.which",
            return_value="/usr/local/bin/tesseract",
        ), patch(
            "sidelinehd_extractor.preflight.tesseract_version",
            return_value=None,
        ):
            statuses = preflight_dependencies()

        status = _by_name(statuses)["tesseract"]
        self.assertTrue(status["ok"])
        self.assertIn("version unknown", status["detail"])


if __name__ == "__main__":
    unittest.main()
