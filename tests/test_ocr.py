import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sidelinehd_extractor.ocr import (
    OCRBackendUnavailable,
    OCRBackendResult,
    OCRFieldConfig,
    FIELD_CONFIGS,
    _extract_highlighted_lineup_crop,
    _optional_tesserocr_backend,
    _parse_tesseract_tsv_output,
    _tesseract_install_hint,
    _tesseract_command,
    create_ocr_backend,
    normalize_ocr_text,
    preprocess_for_ocr,
    tesseract_ocr_image,
    tesseract_version,
)


class OCRTests(unittest.TestCase):
    def test_normalize_ocr_text_collapses_lines_and_form_feeds(self):
        self.assertEqual(normalize_ocr_text("  0-0\n\x0c  "), "0-0")

    def test_normalize_count_extracts_count_from_artifact_prefix(self):
        self.assertEqual(normalize_ocr_text("4 0-0\n", "count"), "0-0")

    def test_normalize_number_fields_extracts_jersey_number(self):
        self.assertEqual(normalize_ocr_text(" #22\n", "batter_card_number"), "#22")

    def test_game_status_field_config_is_optional(self):
        self.assertTrue(FIELD_CONFIGS["game_status"].optional)

    def test_create_none_backend(self):
        backend = create_ocr_backend("none")

        result = backend(object(), "count")

        self.assertEqual(result.text, "")
        self.assertEqual(result.backend, "none")
        self.assertIsNone(result.source_detail)

    def test_create_tesseract_backend_requires_binary(self):
        with patch("sidelinehd_extractor.ocr.shutil.which", return_value=None):
            with self.assertRaises(OCRBackendUnavailable):
                create_ocr_backend("tesseract")

    def test_create_tesserocr_backend_falls_back_to_subprocess_when_unavailable(self):
        with patch("sidelinehd_extractor.ocr._optional_tesserocr_backend", return_value=None):
            with patch("sidelinehd_extractor.ocr.ensure_tesseract_available") as ensure:
                with patch("sidelinehd_extractor.ocr.tesseract_version", return_value="5.3.0"):
                    backend = create_ocr_backend("tesserocr")

        ensure.assert_called_once()
        self.assertIs(backend, tesseract_ocr_image)

    def test_create_tesserocr_backend_uses_optional_backend_when_available(self):
        def sentinel(_image, _field_name):
            return OCRBackendResult("x", "x")

        with patch("sidelinehd_extractor.ocr._optional_tesserocr_backend", return_value=sentinel):
            with patch("sidelinehd_extractor.ocr.ensure_tesseract_available") as ensure:
                with patch("sidelinehd_extractor.ocr.tesseract_version", return_value="5.3.0"):
                    backend = create_ocr_backend("tesserocr")

        ensure.assert_not_called()
        self.assertIs(backend, sentinel)

    def test_optional_tesserocr_backend_returns_none_when_dependency_missing(self):
        def fake_import(name, *args, **kwargs):
            if name == "tesserocr":
                raise ImportError("missing")
            return original_import(name, *args, **kwargs)

        original_import = __import__
        with patch("builtins.__import__", side_effect=fake_import):
            backend = _optional_tesserocr_backend()

        self.assertIsNone(backend)

    def test_tesseract_version_parses_first_line(self):
        with patch(
            "sidelinehd_extractor.ocr.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0,
                stdout="tesseract 5.3.0\n leptonica-1.83.1\n",
                stderr="",
            ),
        ):
            version = tesseract_version()

        self.assertEqual(version, "5.3.0")

    def test_tesseract_version_returns_none_for_unrecognized_output(self):
        with patch(
            "sidelinehd_extractor.ocr.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="unexpected\n", stderr=""),
        ):
            version = tesseract_version()

        self.assertIsNone(version)

    def test_create_tesseract_backend_warns_for_old_version_without_failing(self):
        stderr = io.StringIO()

        with patch("sidelinehd_extractor.ocr.shutil.which", return_value="/usr/bin/tesseract"):
            with patch("sidelinehd_extractor.ocr.tesseract_version", return_value="3.05.02"):
                with redirect_stderr(stderr):
                    backend = create_ocr_backend("tesseract")

        self.assertIs(backend, tesseract_ocr_image)
        self.assertIn("below the supported minimum", stderr.getvalue())

    def test_tesseract_install_hint_is_platform_specific(self):
        with patch("sidelinehd_extractor.ocr.sys.platform", "darwin"):
            self.assertIn("brew install tesseract", _tesseract_install_hint())
        with patch("sidelinehd_extractor.ocr.sys.platform", "linux"):
            self.assertIn("sudo apt install tesseract-ocr", _tesseract_install_hint())
        with patch("sidelinehd_extractor.ocr.sys.platform", "win32"):
            self.assertIn("UB Mannheim", _tesseract_install_hint())

    def test_preprocess_for_ocr_rejects_none_image(self):
        with self.assertRaisesRegex(ValueError, "OpenCV image array"):
            preprocess_for_ocr(None, "count")

    def test_preprocess_for_ocr_rejects_non_image_object(self):
        with self.assertRaisesRegex(ValueError, "OpenCV image array"):
            preprocess_for_ocr(object(), "count")

    def test_extract_highlighted_lineup_crop_finds_green_chip(self):
        import cv2
        import numpy as np

        image = np.zeros((30, 120, 3), dtype=np.uint8)
        image[:] = (35, 55, 65)
        cv2.rectangle(image, (45, 7), (62, 24), (40, 220, 185), thickness=-1)

        crop = _extract_highlighted_lineup_crop(image)

        self.assertIsNotNone(crop)
        self.assertGreaterEqual(crop.shape[0], 18)
        self.assertGreaterEqual(crop.shape[1], 18)

    def test_tesseract_lineup_strip_marks_highlight_source_detail(self):
        with patch("sidelinehd_extractor.ocr.ensure_tesseract_available"):
            with patch(
                "sidelinehd_extractor.ocr._extract_highlighted_lineup_crop",
                return_value=object(),
            ):
                with patch("sidelinehd_extractor.ocr.preprocess_for_ocr", return_value=object()):
                    with patch(
                        "sidelinehd_extractor.ocr._tesseract_ocr_preprocessed_image",
                        return_value=OCRBackendResult(
                            text="26\n",
                            normalized_text="26",
                            backend="tesseract",
                        ),
                    ):
                        result = tesseract_ocr_image(object(), "lineup_strip")

        self.assertEqual(result.source_detail, "lineup_highlight")

    def test_tesseract_lineup_strip_marks_full_strip_source_detail(self):
        with patch("sidelinehd_extractor.ocr.ensure_tesseract_available"):
            with patch(
                "sidelinehd_extractor.ocr._extract_highlighted_lineup_crop",
                return_value=None,
            ):
                with patch("sidelinehd_extractor.ocr.preprocess_for_ocr", return_value=object()):
                    with patch(
                        "sidelinehd_extractor.ocr._tesseract_ocr_preprocessed_image",
                        return_value=OCRBackendResult(
                            text="15\n",
                            normalized_text="15",
                            backend="tesseract",
                        ),
                    ):
                        result = tesseract_ocr_image(object(), "lineup_strip")

        self.assertEqual(result.source_detail, "lineup_full_strip")

    def test_tesseract_command_includes_psm_and_whitelist(self):
        command = _tesseract_command(
            Path("crop.png"),
            OCRFieldConfig(psm=10, whitelist="0123456789"),
        )

        self.assertIn("--psm", command)
        self.assertIn("10", command)
        self.assertIn("tessedit_char_whitelist=0123456789", command)
        self.assertEqual(command[-1], "tsv")

    def test_parse_tesseract_tsv_uses_min_confidence_for_numeric_fields(self):
        text, confidence = _parse_tesseract_tsv_output(
            "\t".join(["level", "page_num", "conf", "text"])
            + "\n"
            + "\t".join(["5", "1", "91.0", "12"])
            + "\n"
            + "\t".join(["5", "1", "74.0", "3"])
            + "\n",
            "batter_card_number",
        )

        self.assertEqual(text, "12 3")
        self.assertAlmostEqual(confidence, 0.74)

    def test_parse_tesseract_tsv_uses_weighted_mean_for_text_fields(self):
        text, confidence = _parse_tesseract_tsv_output(
            "\t".join(["level", "page_num", "conf", "text"])
            + "\n"
            + "\t".join(["5", "1", "80.0", "Maya"])
            + "\n"
            + "\t".join(["5", "1", "50.0", "R."])
            + "\n",
            "batter_card_name",
        )

        self.assertEqual(text, "Maya R.")
        self.assertAlmostEqual(confidence, ((4 * 0.8) + (2 * 0.5)) / 6)

    def test_parse_tesseract_tsv_degrades_to_text_without_confidence_when_malformed(self):
        text, confidence = _parse_tesseract_tsv_output("plain text\n", "batter_card_name")

        self.assertEqual(text, "plain text\n")
        self.assertIsNone(confidence)


if __name__ == "__main__":
    unittest.main()
