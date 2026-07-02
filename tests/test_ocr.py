import unittest
from pathlib import Path
from unittest.mock import patch

from sidelinehd_extractor.ocr import (
    OCRBackendUnavailable,
    OCRBackendResult,
    OCRFieldConfig,
    FIELD_CONFIGS,
    _extract_highlighted_lineup_crop,
    _tesseract_install_hint,
    _tesseract_command,
    create_ocr_backend,
    normalize_ocr_text,
    preprocess_for_ocr,
    tesseract_ocr_image,
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


if __name__ == "__main__":
    unittest.main()
