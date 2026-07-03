import io
import shutil
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
    MULTI_PSM_VOTE_FIELDS,
    NUMERIC_CONFIDENCE_FIELDS,
    PREPROCESS_STRATEGIES,
    _extract_highlighted_lineup_crop,
    _GLYPH_PAD_PX,
    _optional_tesserocr_backend,
    _parse_tesseract_tsv_output,
    _tesseract_install_hint,
    _tesseract_command,
    _tesseract_ocr_preprocessed_image,
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


def _make_numeric_crop(text, width=32, height=23):
    """Deterministic scorebug-like crop: bright digits on a dark noisy background."""

    import cv2
    import numpy as np

    rng = np.random.default_rng(sum(ord(character) for character in text))
    image = np.zeros((height, width, 3), dtype=np.float32)
    for row in range(height):
        image[row, :] = np.array([58, 48, 42], dtype=np.float32) * (1.0 + 0.25 * row / height)
    image += rng.normal(0, 6.0, size=image.shape)
    font_scale = 0.62 if len(text) <= 2 else 0.5
    size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
    origin = ((width - size[0]) // 2, (height + size[1]) // 2)
    cv2.putText(
        image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, (235, 235, 235), 1, cv2.LINE_AA
    )
    return np.clip(image, 0, 255).astype(np.uint8)


class PreprocessStrategyTests(unittest.TestCase):
    def test_isolated_glyph_fields_use_pad_and_other_fields_default(self):
        for field in MULTI_PSM_VOTE_FIELDS - {"count"}:
            self.assertEqual(FIELD_CONFIGS[field].preprocess, "numeric_glyph_pad", field)
        # count is multi-glyph ("1-2"): measured worse under the pad, stays default.
        for field in ("count", "left_team", "right_team", "batter_card_name", "lineup_strip"):
            self.assertEqual(FIELD_CONFIGS[field].preprocess, "default", field)
        self.assertEqual(OCRFieldConfig().preprocess, "default")

    def test_vote_fields_match_numeric_confidence_fields(self):
        self.assertEqual(MULTI_PSM_VOTE_FIELDS, frozenset(NUMERIC_CONFIDENCE_FIELDS))

    def test_unknown_preprocess_strategy_raises_with_known_names(self):
        bogus = OCRFieldConfig(preprocess="hologram")
        with patch.dict(FIELD_CONFIGS, {"left_score": bogus}):
            with self.assertRaises(ValueError) as caught:
                preprocess_for_ocr(_make_numeric_crop("4"), "left_score")
        self.assertIn("hologram", str(caught.exception))
        self.assertIn("numeric_glyph_pad", str(caught.exception))

    def test_numeric_glyph_pad_adds_white_border_around_default_output(self):
        crop = _make_numeric_crop("4")
        padded = preprocess_for_ocr(crop, "left_score")
        with patch.dict(
            FIELD_CONFIGS, {"left_score": OCRFieldConfig(psm=10, scale=6, preprocess="default")}
        ):
            plain = preprocess_for_ocr(crop, "left_score")

        self.assertEqual(padded.shape[0], plain.shape[0] + 2 * _GLYPH_PAD_PX)
        self.assertEqual(padded.shape[1], plain.shape[1] + 2 * _GLYPH_PAD_PX)
        # Border is white (Tesseract-friendly background); interior is the default output.
        self.assertTrue((padded[:_GLYPH_PAD_PX, :] == 255).all())
        self.assertTrue((padded[:, :_GLYPH_PAD_PX] == 255).all())
        self.assertTrue(
            (padded[_GLYPH_PAD_PX:-_GLYPH_PAD_PX, _GLYPH_PAD_PX:-_GLYPH_PAD_PX] == plain).all()
        )

    def test_every_registered_strategy_produces_binary_output(self):
        import numpy as np

        crop = _make_numeric_crop("26")
        for name in PREPROCESS_STRATEGIES:
            config = OCRFieldConfig(psm=7, scale=4, preprocess=name)
            with patch.dict(FIELD_CONFIGS, {"left_team": config}):
                processed = preprocess_for_ocr(crop, "left_team")
            self.assertEqual(processed.dtype, np.uint8, name)
            self.assertTrue(set(np.unique(processed)) <= {0, 255}, name)


class MultiPsmVotingTests(unittest.TestCase):
    def _run_field(self, field_name, results_by_psm, recorded_configs):
        def fake_run(processed_image, config, name):
            recorded_configs.append(config)
            return results_by_psm[config.psm]

        with patch("sidelinehd_extractor.ocr.ensure_tesseract_available"):
            with patch("sidelinehd_extractor.ocr.preprocess_for_ocr", return_value=object()):
                with patch(
                    "sidelinehd_extractor.ocr._tesseract_ocr_preprocessed_image",
                    side_effect=fake_run,
                ):
                    return tesseract_ocr_image(object(), field_name)

    def test_numeric_field_runs_both_psms_and_higher_confidence_wins(self):
        configs = []
        result = self._run_field(
            "left_score",
            {
                10: OCRBackendResult("8\n", "8", confidence=0.41, backend="tesseract"),
                7: OCRBackendResult("3\n", "3", confidence=0.93, backend="tesseract"),
            },
            configs,
        )

        # Configured PSM (10) first, then the other vote PSM; preprocessing ran once.
        self.assertEqual([config.psm for config in configs], [10, 7])
        self.assertEqual(result.normalized_text, "3")
        self.assertEqual(result.confidence, 0.93)

    def test_confidence_tie_prefers_whitelist_valid_candidate(self):
        configs = []
        result = self._run_field(
            "batter_number",
            {
                10: OCRBackendResult("1 z\n", "1 z", confidence=0.6, backend="tesseract"),
                7: OCRBackendResult("12\n", "12", confidence=0.6, backend="tesseract"),
            },
            configs,
        )
        self.assertEqual(result.normalized_text, "12")

    def test_tie_between_valid_candidates_keeps_configured_psm(self):
        configs = []
        result = self._run_field(
            "right_score",
            {
                10: OCRBackendResult("4\n", "4", confidence=0.7, backend="tesseract"),
                7: OCRBackendResult("9\n", "9", confidence=0.7, backend="tesseract"),
            },
            configs,
        )
        self.assertEqual(result.normalized_text, "4")

    def test_missing_confidence_loses_to_scored_candidate(self):
        configs = []
        result = self._run_field(
            "count",
            {
                7: OCRBackendResult("1-2\n", "1-2", confidence=None, backend="tesseract"),
                10: OCRBackendResult("3-1\n", "3-1", confidence=0.2, backend="tesseract"),
            },
            configs,
        )
        self.assertEqual([config.psm for config in configs], [7, 10])
        self.assertEqual(result.normalized_text, "3-1")

    def test_text_field_is_never_double_run(self):
        configs = []
        result = self._run_field(
            "left_team",
            {7: OCRBackendResult("VIPERS\n", "VIPERS", confidence=0.5, backend="tesseract")},
            configs,
        )
        self.assertEqual([config.psm for config in configs], [7])
        self.assertEqual(result.normalized_text, "VIPERS")


@unittest.skipUnless(shutil.which("tesseract"), "requires the Tesseract CLI")
class NumericConfidenceRegressionTests(unittest.TestCase):
    """Item 43's measurement gate as a test: the shipped numeric pipeline
    (glyph-pad preprocessing + PSM voting) must not regress accuracy or
    confidence against the pre-item-43 pipeline (default Otsu, single PSM)
    on scorebug-like digit fixtures."""

    CASES = [
        ("left_score", "2"),
        ("left_score", "4"),
        ("right_score", "11"),
        ("batter_number", "26"),
        ("on_deck_number", "7"),
        ("count", "1-2"),
    ]

    def _old_pipeline(self, crop, field_name):
        config = FIELD_CONFIGS[field_name]
        old_config = OCRFieldConfig(
            psm=config.psm, whitelist=config.whitelist, scale=config.scale, preprocess="default"
        )
        with patch.dict(FIELD_CONFIGS, {field_name: old_config}):
            processed = preprocess_for_ocr(crop, field_name)
        return _tesseract_ocr_preprocessed_image(processed, old_config, field_name)

    def test_shipped_numeric_pipeline_does_not_regress(self):
        old_correct = new_correct = 0
        paired_deltas = []
        for field_name, truth in self.CASES:
            crop = _make_numeric_crop(truth)
            old = self._old_pipeline(crop, field_name)
            new = tesseract_ocr_image(crop, field_name)
            old_correct += old.normalized_text == truth
            new_correct += new.normalized_text == truth
            # Confidence is only comparable where both pipelines read the same
            # text; comparing raw means would reward a pipeline for failing to
            # read hard crops at all (a miss records no confidence).
            if (
                old.confidence is not None
                and new.confidence is not None
                and old.normalized_text == new.normalized_text
            ):
                paired_deltas.append(new.confidence - old.confidence)

        self.assertGreaterEqual(new_correct, old_correct)
        self.assertGreaterEqual(new_correct, len(self.CASES) - 1)
        self.assertTrue(paired_deltas)
        mean_delta = sum(paired_deltas) / len(paired_deltas)
        self.assertGreaterEqual(mean_delta, -0.05)

    def test_empty_crop_still_reads_empty(self):
        import numpy as np

        rng = np.random.default_rng(7)
        empty = np.clip(
            rng.normal(0, 6.0, (23, 32, 3)) + np.array([58, 48, 42])[None, None, :], 0, 255
        ).astype(np.uint8)
        result = tesseract_ocr_image(empty, "right_score")
        self.assertEqual(result.normalized_text, "")


if __name__ == "__main__":
    unittest.main()
