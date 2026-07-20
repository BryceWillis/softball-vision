"""Tests for the dependency preflight report (item 54a, bundle-aware)."""

import unittest
from unittest.mock import patch

from sidelinehd_extractor.ocr import OCR_BUNDLE_DAMAGED_MESSAGE
from sidelinehd_extractor.preflight import (
    FFMPEG_BUNDLE_DAMAGED_MESSAGE,
    FFMPEG_REINSTALL_MESSAGE,
    missing_dependencies,
    preflight_dependencies,
)
from sidelinehd_extractor.youtube import YTDLP_REINSTALL_MESSAGE


def _by_name(statuses):
    return {status["name"]: status for status in statuses}


class _FakeYtdlp:
    pass


def _healthy_patches(**overrides):
    """Patch every probe healthy; override per test."""

    values = {
        "load_ytdlp_module": {"return_value": _FakeYtdlp()},
        "installed_ytdlp_version": {"return_value": "2025.10.14"},
        "resolve_ffmpeg_location": {"return_value": "/usr/local/bin/ffmpeg"},
        "tesserocr_backend_available": {"return_value": True},
        "tesserocr_engine_version": {"return_value": "5.5.1"},
        "running_frozen": {"return_value": False},
    }
    values.update(overrides)
    return [
        patch(f"sidelinehd_extractor.preflight.{name}", **kwargs)
        for name, kwargs in values.items()
    ]


def _preflight_with(**overrides):
    patches = _healthy_patches(**overrides)
    for item in patches:
        item.start()
    try:
        return preflight_dependencies()
    finally:
        for item in patches:
            item.stop()


class PreflightTests(unittest.TestCase):
    def test_all_dependencies_present_via_bundled_modules(self):
        statuses = _preflight_with()

        report = _by_name(statuses)
        self.assertEqual(set(report), {"yt-dlp", "ffmpeg", "tesseract"})
        self.assertTrue(all(status["ok"] for status in statuses))
        self.assertEqual(report["yt-dlp"]["detail"], "yt_dlp module 2025.10.14")
        self.assertEqual(report["ffmpeg"]["detail"], "/usr/local/bin/ffmpeg")
        self.assertEqual(report["tesseract"]["detail"], "tesserocr module (Tesseract 5.5.1)")
        self.assertTrue(all(status["install_hint"] is None for status in statuses))
        self.assertEqual(missing_dependencies(statuses), [])

    def test_missing_ytdlp_reports_reinstall_hint(self):
        statuses = _preflight_with(
            load_ytdlp_module={"side_effect": FileNotFoundError(YTDLP_REINSTALL_MESSAGE)}
        )

        status = _by_name(statuses)["yt-dlp"]
        self.assertFalse(status["ok"])
        self.assertEqual(status["install_hint"], YTDLP_REINSTALL_MESSAGE)
        self.assertEqual(missing_dependencies(statuses), [status])

    def test_missing_ffmpeg_reports_reinstall_hint(self):
        statuses = _preflight_with(resolve_ffmpeg_location={"return_value": None})

        status = _by_name(statuses)["ffmpeg"]
        self.assertFalse(status["ok"])
        self.assertEqual(status["install_hint"], FFMPEG_REINSTALL_MESSAGE)

    def test_missing_ffmpeg_in_frozen_app_never_advises_pip(self):
        statuses = _preflight_with(
            resolve_ffmpeg_location={"return_value": None},
            running_frozen={"return_value": True},
        )

        status = _by_name(statuses)["ffmpeg"]
        self.assertFalse(status["ok"])
        self.assertEqual(status["install_hint"], FFMPEG_BUNDLE_DAMAGED_MESSAGE)
        self.assertNotIn("pip", status["install_hint"])

    def test_tesseract_falls_back_to_cli_for_source_installs(self):
        with patch(
            "sidelinehd_extractor.preflight.shutil.which",
            return_value="/usr/local/bin/tesseract",
        ), patch(
            "sidelinehd_extractor.preflight.tesseract_version",
            return_value="5.3.4",
        ):
            statuses = _preflight_with(
                tesserocr_backend_available={"return_value": False}
            )

        status = _by_name(statuses)["tesseract"]
        self.assertTrue(status["ok"])
        self.assertEqual(status["detail"], "version 5.3.4")

    def test_missing_tesseract_reports_os_install_hint_from_source(self):
        with patch(
            "sidelinehd_extractor.preflight.shutil.which",
            return_value=None,
        ), patch(
            "sidelinehd_extractor.preflight.tesseract_install_hint",
            return_value="Install it with `brew install tesseract`.",
        ):
            statuses = _preflight_with(
                tesserocr_backend_available={"return_value": False}
            )

        status = _by_name(statuses)["tesseract"]
        self.assertFalse(status["ok"])
        self.assertIn("brew install tesseract", status["install_hint"])

    def test_broken_ocr_in_frozen_app_never_advises_brew(self):
        with patch(
            "sidelinehd_extractor.preflight.shutil.which",
            side_effect=AssertionError("a frozen app must not consult PATH"),
        ):
            statuses = _preflight_with(
                tesserocr_backend_available={"return_value": False},
                running_frozen={"return_value": True},
            )

        status = _by_name(statuses)["tesseract"]
        self.assertFalse(status["ok"])
        self.assertEqual(status["install_hint"], OCR_BUNDLE_DAMAGED_MESSAGE)
        self.assertNotIn("brew", status["install_hint"])

    def test_tesserocr_with_unknown_engine_version(self):
        statuses = _preflight_with(tesserocr_engine_version={"return_value": None})

        status = _by_name(statuses)["tesseract"]
        self.assertTrue(status["ok"])
        self.assertIn("version unknown", status["detail"])

    def test_ytdlp_present_with_unknown_version(self):
        statuses = _preflight_with(installed_ytdlp_version={"return_value": None})

        status = _by_name(statuses)["yt-dlp"]
        self.assertTrue(status["ok"])
        self.assertIn("version unknown", status["detail"])


if __name__ == "__main__":
    unittest.main()
