import io
import shutil
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sidelinehd_extractor.ocr import (
    OCR_BUNDLE_DAMAGED_MESSAGE,
    OCRBackendUnavailable,
    OCRBackendResult,
    OCRFieldConfig,
    FIELD_CONFIGS,
    MULTI_PSM_VOTE_FIELDS,
    NUMERIC_CONFIDENCE_FIELDS,
    PREPROCESS_STRATEGIES,
    _extract_highlighted_lineup_crop,
    _GLYPH_PAD_PX,
    _has_dark_batter_card_number_background,
    _isolate_batter_card_number_glyphs,
    _ocr_batter_card_number,
    _optional_tesserocr_backend,
    _parse_tesseract_tsv_output,
    _tesseract_install_hint,
    _tesseract_command,
    _tesseract_ocr_preprocessed_image,
    create_ocr_backend,
    detect_inning_arrow,
    normalize_ocr_text,
    preprocess_for_ocr,
    tesseract_ocr_image,
    tesseract_version,
    tesserocr_engine_version,
)


class OCRTests(unittest.TestCase):
    def test_normalize_ocr_text_collapses_lines_and_form_feeds(self):
        self.assertEqual(normalize_ocr_text("  0-0\n\x0c  "), "0-0")

    def test_normalize_count_extracts_count_from_artifact_prefix(self):
        self.assertEqual(normalize_ocr_text("4 0-0\n", "count"), "0-0")

    def test_normalize_number_fields_extracts_jersey_number(self):
        self.assertEqual(normalize_ocr_text(" #22\n", "batter_card_number"), "#22")

    def test_normalize_scorebug_fields_map_letter_o_to_zero(self):
        # The bold scorebug zero classifies as "o"/"O" under PSM 8.
        self.assertEqual(normalize_ocr_text("o\n", "left_score"), "0")
        self.assertEqual(normalize_ocr_text("O", "right_score"), "0")
        self.assertEqual(normalize_ocr_text("1o", "left_score"), "10")
        self.assertEqual(normalize_ocr_text("o", "inning"), "0")

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

    def test_create_tesserocr_backend_frozen_raises_instead_of_cli_fallback(self):
        # The silent CLI fallback is exactly what masked the broken v0.4.0
        # bundle behind a terminal PATH; frozen apps must fail loudly instead.
        with patch("sidelinehd_extractor.ocr._optional_tesserocr_backend", return_value=None):
            with patch("sidelinehd_extractor.ocr.running_frozen", return_value=True):
                with patch("sidelinehd_extractor.ocr.ensure_tesseract_available") as ensure:
                    with self.assertRaises(OCRBackendUnavailable) as ctx:
                        create_ocr_backend("tesserocr")

        ensure.assert_not_called()
        message = str(ctx.exception)
        self.assertEqual(message, OCR_BUNDLE_DAMAGED_MESSAGE)
        self.assertNotIn("brew", message)
        self.assertNotIn("--ocr", message)

    def test_ensure_tesseract_frozen_error_never_advises_brew(self):
        with patch("sidelinehd_extractor.ocr.shutil.which", return_value=None):
            with patch("sidelinehd_extractor.ocr.running_frozen", return_value=True):
                with self.assertRaises(OCRBackendUnavailable) as ctx:
                    create_ocr_backend("tesseract")

        message = str(ctx.exception)
        self.assertEqual(message, OCR_BUNDLE_DAMAGED_MESSAGE)
        self.assertNotIn("brew", message)

    def test_tesserocr_engine_version_parses_version_line(self):
        fake_tesserocr = SimpleNamespace(
            tesseract_version=lambda: "tesseract 5.5.1\n leptonica-1.85.0\n"
        )
        with patch.dict("sys.modules", {"tesserocr": fake_tesserocr}):
            self.assertEqual(tesserocr_engine_version(), "5.5.1")

    def test_tesserocr_engine_version_none_when_module_missing(self):
        with patch.dict("sys.modules", {"tesserocr": None}):
            self.assertIsNone(tesserocr_engine_version())

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
    """Deterministic scorebug-like crop: bright digits on a dark noisy background.

    Stroke thickness 2 matches the bold SidelineHD scorebug font; the previous
    1px strokes fragmented under the color glyph-isolation mask in ways the
    real overlay (verified on live-fire frames) never does.
    """

    import cv2
    import numpy as np

    rng = np.random.default_rng(sum(ord(character) for character in text))
    background = np.zeros((height, width, 3), dtype=np.float32)
    for row in range(height):
        background[row, :] = np.array([58, 48, 42], dtype=np.float32) * (1.0 + 0.25 * row / height)
    background += rng.normal(0, 6.0, size=background.shape)
    # OpenCV 5's putText requires a CV_8U image, so convert before drawing.
    # No LINE_AA: anti-aliased blending on uint8 rounds differently across
    # OpenCV versions and fragments the thin "11" strokes; plain rasterization
    # is deterministic everywhere.
    image = np.clip(background, 0, 255).astype(np.uint8)
    font_scale = 0.62 if len(text) <= 2 else 0.5
    size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)
    origin = ((width - size[0]) // 2, (height + size[1]) // 2)
    cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, font_scale, (235, 235, 235), 2)
    return image


class MockOCRPreprocessed:
    def __init__(self, *results):
        self._results = list(results)
        self.images = []

    def __call__(self, image, _config, _field_name):
        self.images.append(image)
        if self._results:
            return self._results.pop(0)
        return OCRBackendResult("", "", confidence=None, backend="tesseract")


class PreprocessStrategyTests(unittest.TestCase):
    def test_isolated_glyph_fields_use_pad_and_other_fields_default(self):
        scorebug_fields = {"left_score", "right_score", "inning"}
        for field in scorebug_fields:
            self.assertEqual(FIELD_CONFIGS[field].preprocess, "scorebug_glyph_isolate", field)
        for field in MULTI_PSM_VOTE_FIELDS - {"count"} - scorebug_fields:
            self.assertEqual(FIELD_CONFIGS[field].preprocess, "numeric_glyph_pad", field)
        # count is multi-glyph ("1-2"): measured worse under the pad, stays default.
        for field in ("count", "left_team", "right_team", "batter_card_name", "lineup_strip"):
            self.assertEqual(FIELD_CONFIGS[field].preprocess, "default", field)
        self.assertEqual(OCRFieldConfig().preprocess, "default")

    def test_vote_fields_are_numeric_fields_minus_isolated_scorebug_trio(self):
        from sidelinehd_extractor.ocr import SCOREBUG_ISOLATED_FIELDS

        self.assertEqual(
            MULTI_PSM_VOTE_FIELDS,
            frozenset(NUMERIC_CONFIDENCE_FIELDS) - SCOREBUG_ISOLATED_FIELDS,
        )
        self.assertEqual(SCOREBUG_ISOLATED_FIELDS, {"left_score", "right_score", "inning"})

    def test_unknown_preprocess_strategy_raises_with_known_names(self):
        bogus = OCRFieldConfig(preprocess="hologram")
        with patch.dict(FIELD_CONFIGS, {"left_score": bogus}):
            with self.assertRaises(ValueError) as caught:
                preprocess_for_ocr(_make_numeric_crop("4"), "left_score")
        self.assertIn("hologram", str(caught.exception))
        self.assertIn("numeric_glyph_pad", str(caught.exception))

    def test_numeric_glyph_pad_adds_white_border_around_default_output(self):
        crop = _make_numeric_crop("4")
        padded = preprocess_for_ocr(crop, "batter_number")
        with patch.dict(
            FIELD_CONFIGS, {"batter_number": OCRFieldConfig(psm=10, scale=6, preprocess="default")}
        ):
            plain = preprocess_for_ocr(crop, "batter_number")

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


class ScorebugGlyphIsolationTests(unittest.TestCase):
    def test_isolation_extracts_digit_glyphs_as_dark_on_light(self):
        import numpy as np

        processed = preprocess_for_ocr(_make_numeric_crop("4"), "left_score")

        self.assertEqual(processed.dtype, np.uint8)
        self.assertTrue(set(np.unique(processed)) <= set(range(256)))
        # Glyph present: some dark pixels surrounded by a white border.
        self.assertTrue((processed < 128).any())
        self.assertTrue((processed[0, :] == 255).all())
        self.assertTrue((processed[:, 0] == 255).all())

    def test_isolation_returns_blank_when_no_digit_glyph_exists(self):
        import numpy as np

        # A flat dark crop (no bright glyph): must yield a blank canvas so
        # OCR reports an empty read instead of binarization noise.
        crop = np.full((23, 32, 3), 40, dtype=np.uint8)
        processed = preprocess_for_ocr(crop, "right_score")

        self.assertTrue((processed == 255).all())

    def test_isolation_rejects_banner_text_spanning_the_crop(self):
        import cv2
        import numpy as np

        # Scrolling-banner mode: a run of letter-sized glyphs crossing the
        # region, clipped at both edges. Must refuse rather than misread.
        # Drawn twice at a 2px offset so the letters bridge into one
        # crop-spanning component regardless of the OpenCV version's exact
        # Hershey rasterization (OpenCV 5 renders tighter glyphs whose
        # unclipped middle letters would otherwise pass isolation).
        crop = np.full((23, 32, 3), 60, dtype=np.uint8)
        cv2.putText(crop, "MASH", (-4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (235, 235, 235), 2)
        cv2.putText(crop, "MASH", (-2, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (235, 235, 235), 2)
        processed = preprocess_for_ocr(crop, "left_score")

        self.assertTrue((processed == 255).all())

    def test_dimmed_final_score_recovered_by_relaxed_pass_for_scores_only(self):
        import cv2
        import numpy as np

        # FINAL view dims the losing score to desaturated blue-gray
        # (V≈165, S≈110) — below the strict mask.
        crop = np.full((23, 32, 3), 45, dtype=np.uint8)
        cv2.putText(crop, "16", (7, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (170, 150, 120), 2)
        # Soften like compressed video; razor-sharp synthetic edges overshoot
        # past the strict-mask floor under cubic upscaling, which real dimmed
        # footage (measured V≈165 peak) does not.
        crop = cv2.GaussianBlur(crop, (3, 3), 0)
        score_processed = preprocess_for_ocr(crop, "left_score")
        inning_processed = preprocess_for_ocr(crop, "inning")

        # Score fields get the relaxed retry; inning must stay blank (its
        # relaxed bounds would admit banner letters instead).
        self.assertTrue((score_processed < 128).any())
        self.assertTrue((inning_processed == 255).all())

    def test_grayscale_input_degrades_to_numeric_pad(self):
        import cv2
        import numpy as np

        crop = cv2.cvtColor(_make_numeric_crop("4"), cv2.COLOR_BGR2GRAY)
        processed = preprocess_for_ocr(crop, "left_score")

        self.assertEqual(processed.dtype, np.uint8)
        self.assertTrue((processed < 128).any())


class BatterCardNumberOCRTests(unittest.TestCase):
    def _card_number_crop(self, text="#24"):
        import cv2
        import numpy as np

        crop = np.full((19, 33, 3), (42, 35, 28), dtype=np.uint8)
        cv2.putText(crop, text, (1, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (235, 235, 235), 1)
        return crop

    def test_batter_card_number_background_gate_rejects_bright_absent_card(self):
        import numpy as np

        crop = np.full((19, 33, 3), (220, 230, 240), dtype=np.uint8)

        result = _ocr_batter_card_number(crop, "tesseract", MockOCRPreprocessed())

        self.assertEqual(result.normalized_text, "")
        self.assertEqual(result.backend, "tesseract")

    def test_batter_card_number_background_gate_accepts_dark_card(self):
        self.assertTrue(_has_dark_batter_card_number_background(self._card_number_crop()))

    def test_batter_card_number_isolation_extracts_hash_number_glyphs(self):
        processed = _isolate_batter_card_number_glyphs(self._card_number_crop(), scale=6)

        self.assertIsNotNone(processed)
        self.assertTrue((processed < 128).any())

    def test_batter_card_number_keeps_existing_nonempty_read(self):
        calls = []
        ocr = MockOCRPreprocessed(
            OCRBackendResult("#24", "#24", confidence=0.8, backend="tesseract")
        )

        with patch(
            "sidelinehd_extractor.ocr._isolate_batter_card_number_glyphs",
            side_effect=lambda *_args: calls.append("fallback"),
        ):
            result = _ocr_batter_card_number(self._card_number_crop(), "tesseract", ocr)

        self.assertEqual(result.normalized_text, "#24")
        self.assertEqual(calls, [])

    def test_batter_card_number_uses_isolated_fallback_after_empty_read(self):
        processed_fallback = object()
        ocr = MockOCRPreprocessed(
            OCRBackendResult("", "", confidence=None, backend="tesseract"),
            OCRBackendResult("", "", confidence=None, backend="tesseract"),
            OCRBackendResult("#24", "#24", confidence=0.9, backend="tesseract"),
        )

        with patch(
            "sidelinehd_extractor.ocr._isolate_batter_card_number_glyphs",
            return_value=processed_fallback,
        ):
            result = _ocr_batter_card_number(self._card_number_crop(), "tesseract", ocr)

        self.assertEqual(result.normalized_text, "#24")
        self.assertIs(ocr.images[-1], processed_fallback)

    def test_batter_card_number_rejects_overlong_isolated_fallback(self):
        ocr = MockOCRPreprocessed(
            OCRBackendResult("", "", confidence=None, backend="tesseract"),
            OCRBackendResult("", "", confidence=None, backend="tesseract"),
            OCRBackendResult("#103", "#103", confidence=0.9, backend="tesseract"),
            OCRBackendResult("#103", "#103", confidence=0.9, backend="tesseract"),
        )

        with patch(
            "sidelinehd_extractor.ocr._isolate_batter_card_number_glyphs",
            return_value=object(),
        ):
            result = _ocr_batter_card_number(self._card_number_crop(), "tesseract", ocr)

        self.assertEqual(result.normalized_text, "")


class InningArrowDetectionTests(unittest.TestCase):
    def _arrow_crop(self, pointing_up: bool):
        import cv2
        import numpy as np

        crop = np.full((21, 28, 3), 50, dtype=np.uint8)
        # SidelineHD's arrow is a green-yellow triangle left of the digit.
        if pointing_up:
            points = np.array([[3, 15], [13, 15], [8, 5]])
        else:
            points = np.array([[3, 5], [13, 5], [8, 15]])
        cv2.fillPoly(crop, [points], (80, 220, 180))  # BGR green-yellow
        return crop

    def test_detects_up_arrow(self):
        from sidelinehd_extractor.constants import INNING_ARROW_UP

        self.assertEqual(detect_inning_arrow(self._arrow_crop(True)), INNING_ARROW_UP)

    def test_detects_down_arrow(self):
        from sidelinehd_extractor.constants import INNING_ARROW_DOWN

        self.assertEqual(detect_inning_arrow(self._arrow_crop(False)), INNING_ARROW_DOWN)

    def test_returns_none_without_arrow(self):
        import numpy as np

        self.assertIsNone(detect_inning_arrow(np.full((21, 28, 3), 50, dtype=np.uint8)))
        self.assertIsNone(detect_inning_arrow(None))
        self.assertIsNone(detect_inning_arrow(np.full((21, 28), 50, dtype=np.uint8)))


class RealFrameInningArrowTests(unittest.TestCase):
    """Arrow direction on real captured frames, not drawn triangles.

    The synthetic triangles above passed throughout the period when the shipped
    detector was reading real footage at 62% accuracy — a coin flip that flipped
    the half-inning 21% of samples and, through the batting-half filter, silently
    deleted 24 of one game's 46 at-bats. A clean isoceles triangle on a flat
    background is not the thing being classified: the real glyph is about ten
    pixels tall, anti-aliased, h.264-compressed, and carries a shadow stub under
    its base that inverted the old width comparison.

    Fixtures are 28x21 scoreboard crops from two games — no player names appear
    in the inning region. Six of the ten arrows below were misread by the
    shipped heuristic; those are marked, and they are the point of this class.
    """

    FIXTURES = Path(__file__).parent / "fixtures" / "inning_arrows"

    UP_FIXTURES = (
        "up_hailstorm_t900",  # old heuristic: DOWN
        "up_hailstorm_t1200",  # old heuristic: DOWN
        "up_hailstorm_t4800",  # old heuristic: DOWN
        "up_rochester_t600",
        "up_rochester_t3750",
    )
    DOWN_FIXTURES = (
        "down_hailstorm_t1500",  # old heuristic: no direction at all
        "down_hailstorm_t1600",  # old heuristic: UP
        "down_hailstorm_t5150",
        "down_rochester_t1200",  # old heuristic: UP
        "down_rochester_t2850",  # old heuristic: UP
    )
    NO_ARROW_FIXTURES = (
        "none_final_banner_t5500",  # FINAL banner: green lettering, no arrow
        "none_pregame_t60",  # pregame overlay: green "GAME..." text
        "none_thin_read_t4930",  # compression thinned the arrow to one column
    )

    def _load(self, name):
        import cv2

        path = self.FIXTURES / f"{name}.png"
        self.assertTrue(path.exists(), f"missing fixture {path}")
        image = cv2.imread(str(path))
        self.assertIsNotNone(image, f"unreadable fixture {path}")
        return image

    def test_up_arrows(self):
        from sidelinehd_extractor.constants import INNING_ARROW_UP

        for name in self.UP_FIXTURES:
            with self.subTest(fixture=name):
                self.assertEqual(detect_inning_arrow(self._load(name)), INNING_ARROW_UP)

    def test_down_arrows(self):
        from sidelinehd_extractor.constants import INNING_ARROW_DOWN

        for name in self.DOWN_FIXTURES:
            with self.subTest(fixture=name):
                self.assertEqual(detect_inning_arrow(self._load(name)), INNING_ARROW_DOWN)

    def test_overlay_states_without_an_arrow_report_no_direction(self):
        """Green that is not an arrow must not become a half-inning.

        The FINAL banner and the pregame overlay both put green in the inning
        region; reporting a direction there invents a half-inning out of
        lettering. The third fixture is a real arrow that compression thinned
        to a single column — too degraded to read, and reported as unknown
        rather than guessed, which is the one case where the shipped detector
        returned a confidently wrong direction.
        """

        for name in self.NO_ARROW_FIXTURES:
            with self.subTest(fixture=name):
                self.assertIsNone(detect_inning_arrow(self._load(name)))


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
            "batter_number",
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

    def test_scorebug_field_keeps_first_nonempty_psm_read(self):
        # No confidence voting for isolated-glyph fields: a mis-segmented
        # PSM 7/10 read must not outscore the correct PSM 8 read.
        configs = []
        result = self._run_field(
            "left_score",
            {
                8: OCRBackendResult("o\n", "0", confidence=0.5, backend="tesseract"),
                10: OCRBackendResult("8\n", "8", confidence=0.99, backend="tesseract"),
                7: OCRBackendResult("3\n", "3", confidence=0.99, backend="tesseract"),
            },
            configs,
        )
        self.assertEqual([config.psm for config in configs], [8])
        self.assertEqual(result.normalized_text, "0")

    def test_scorebug_field_falls_back_when_psm_read_is_empty(self):
        configs = []
        result = self._run_field(
            "right_score",
            {
                8: OCRBackendResult("", "", confidence=None, backend="tesseract"),
                7: OCRBackendResult("21\n", "21", confidence=0.6, backend="tesseract"),
                10: OCRBackendResult("2\n", "2", confidence=0.9, backend="tesseract"),
            },
            configs,
        )
        self.assertEqual([config.psm for config in configs], [8, 7])
        self.assertEqual(result.normalized_text, "21")

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
            "on_deck_number",
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

        # Accuracy is asserted only relative to the old pipeline: an absolute
        # floor tracks the local Tesseract build rather than this code, and
        # fails on builds that misread these synthetic crops on an untouched
        # main while the relative guard correctly shows no regression.
        self.assertGreaterEqual(new_correct, old_correct)
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


class ScorebugDigitMatchTests(unittest.TestCase):
    """Template classification of isolated scorebug glyphs (pre-Tesseract)."""

    @staticmethod
    def _reference_glyph(digit: str):
        import cv2

        from importlib import resources

        digits_dir = resources.files("sidelinehd_extractor") / "data" / "scorebug_digits"
        with resources.as_file(digits_dir / f"{digit}.png") as path:
            image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        assert image is not None, f"missing bundled template {digit}.png"
        return image

    @staticmethod
    def _on_canvas(*glyphs, gap: int = 12, pad: int = 16):
        import cv2
        import numpy as np

        height = max(glyph.shape[0] for glyph in glyphs)
        tiles = []
        for index, glyph in enumerate(glyphs):
            if index:
                tiles.append(np.full((height, gap), 255, dtype=np.uint8))
            tiles.append(cv2.resize(glyph, (glyph.shape[1], height)))
        row = np.hstack(tiles)
        return cv2.copyMakeBorder(row, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)

    def test_each_bundled_digit_matches_itself(self):
        from sidelinehd_extractor.ocr import SCOREBUG_DIGIT_MATCH_SOURCE, match_scorebug_digits

        for digit in "0123456789":
            result = match_scorebug_digits(self._on_canvas(self._reference_glyph(digit)), "test")
            self.assertIsNotNone(result, f"digit {digit} did not match")
            self.assertEqual(result.normalized_text, digit)
            self.assertGreaterEqual(result.confidence, 0.9)
            self.assertEqual(result.source_detail, SCOREBUG_DIGIT_MATCH_SOURCE)

    def test_two_digit_score_reads_left_to_right(self):
        from sidelinehd_extractor.ocr import match_scorebug_digits

        canvas = self._on_canvas(self._reference_glyph("1"), self._reference_glyph("2"))
        result = match_scorebug_digits(canvas, "test")
        self.assertIsNotNone(result)
        self.assertEqual(result.normalized_text, "12")

    def test_blank_canvas_returns_none_for_fallback(self):
        import numpy as np

        from sidelinehd_extractor.ocr import match_scorebug_digits

        self.assertIsNone(match_scorebug_digits(np.full((64, 64), 255, dtype=np.uint8), "test"))

    def test_non_digit_blob_returns_none_for_fallback(self):
        import numpy as np

        from sidelinehd_extractor.ocr import match_scorebug_digits

        canvas = np.full((96, 96), 255, dtype=np.uint8)
        canvas[16:80, 24:72] = 0  # solid block: digit-height but matches nothing well
        self.assertIsNone(match_scorebug_digits(canvas, "test"))

    def test_three_glyphs_returns_none_for_fallback(self):
        from sidelinehd_extractor.ocr import match_scorebug_digits

        canvas = self._on_canvas(*(self._reference_glyph(d) for d in "123"))
        self.assertIsNone(match_scorebug_digits(canvas, "test"))


if __name__ == "__main__":
    unittest.main()
