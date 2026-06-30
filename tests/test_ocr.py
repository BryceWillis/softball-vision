import unittest
from pathlib import Path
from unittest.mock import patch

from sidelinehd_extractor.ocr import (
    OCRBackendUnavailable,
    OCRFieldConfig,
    _tesseract_install_hint,
    _tesseract_command,
    create_ocr_backend,
    normalize_ocr_text,
    preprocess_for_ocr,
)


class OCRTests(unittest.TestCase):
    def test_normalize_ocr_text_collapses_lines_and_form_feeds(self):
        self.assertEqual(normalize_ocr_text("  0-0\n\x0c  "), "0-0")

    def test_normalize_count_extracts_count_from_artifact_prefix(self):
        self.assertEqual(normalize_ocr_text("4 0-0\n", "count"), "0-0")

    def test_normalize_number_fields_extracts_jersey_number(self):
        self.assertEqual(normalize_ocr_text(" #22\n", "batter_card_number"), "#22")

    def test_create_none_backend(self):
        backend = create_ocr_backend("none")

        result = backend(object(), "count")

        self.assertEqual(result.text, "")
        self.assertEqual(result.backend, "none")

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
