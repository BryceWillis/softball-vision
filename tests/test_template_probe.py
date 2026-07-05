"""Tests for the item 55 pre-run template probe. All OCR is stubbed."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from sidelinehd_extractor.config import candidate_overlay_templates
from sidelinehd_extractor.models import OverlayTemplate, RegionFraction
from sidelinehd_extractor.ocr import OCRBackendResult
from sidelinehd_extractor.template_probe import (
    LOW_SCORE_FLOOR,
    field_read_is_valid,
    probe_template,
    probe_timestamps_for_duration,
    score_template,
)


def _result(text: str) -> OCRBackendResult:
    return OCRBackendResult(text=text, normalized_text=text, backend="stub")


def _template(name: str, x: float) -> OverlayTemplate:
    """A candidate whose probe regions sit in one horizontal band at ``x``."""

    regions = {
        field: RegionFraction(x=x, y=0.1 * index, width=0.1, height=0.05)
        for index, field in enumerate(("left_score", "right_score", "count", "inning"))
    }
    return OverlayTemplate(name=name, regions=regions)


def _frames(count: int = 3, lit_x_range: tuple = (0, 64)):
    """Frames that are dark except a lit vertical band (the "overlay")."""

    frames = []
    for index in range(count):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        frame[:, lit_x_range[0] : lit_x_range[1], :] = 255
        frames.append((float(index * 10), frame))
    return frames


def _lit_crop_ocr(crop, field_name):
    """Stub OCR: a lit crop reads a valid value for its field, dark reads noise."""

    if crop.size and crop.mean() > 128:
        valid = {"left_score": "3", "right_score": "12", "count": "1-2", "inning": "T3"}
        return _result(valid.get(field_name, "ok"))
    return _result("")


class FieldValidityTests(unittest.TestCase):
    def test_scores_must_parse_as_small_ints(self):
        self.assertTrue(field_read_is_valid("left_score", "3"))
        self.assertTrue(field_read_is_valid("right_score", "#12"))
        self.assertFalse(field_read_is_valid("left_score", ""))
        self.assertFalse(field_read_is_valid("left_score", "abc"))
        self.assertFalse(field_read_is_valid("right_score", "720"))  # implausible

    def test_count_must_match_balls_strikes(self):
        self.assertTrue(field_read_is_valid("count", "2-1"))
        self.assertFalse(field_read_is_valid("count", "21"))
        self.assertFalse(field_read_is_valid("count", ""))

    def test_inning_uses_pipeline_parser(self):
        self.assertTrue(field_read_is_valid("inning", "T3"))
        self.assertTrue(field_read_is_valid("inning", "3"))
        self.assertFalse(field_read_is_valid("inning", ""))

    def test_batter_card_name_needs_letters(self):
        self.assertTrue(field_read_is_valid("batter_card_name", "Emma B."))
        self.assertFalse(field_read_is_valid("batter_card_name", "12"))


class ScoringTests(unittest.TestCase):
    def test_matching_template_scores_high_and_mismatched_scores_zero(self):
        frames = _frames(lit_x_range=(0, 64))  # overlay in the left 10%
        aligned = _template("aligned", x=0.0)
        misaligned = _template("misaligned", x=0.5)

        self.assertGreaterEqual(score_template(aligned, frames, _lit_crop_ocr), 0.9)
        self.assertEqual(score_template(misaligned, frames, _lit_crop_ocr), 0.0)

    def test_inning_is_deweighted_not_a_gate(self):
        # OCR that reads the three primary fields but always garbles inning
        # (the real 640x360 failure mode) must still score near the top.
        def garbled_inning_ocr(crop, field_name):
            if field_name == "inning":
                return _result("720")
            return _lit_crop_ocr(crop, field_name)

        frames = _frames(lit_x_range=(0, 64))
        aligned = _template("aligned", x=0.0)
        score = score_template(aligned, frames, garbled_inning_ocr)
        # 3 primary reads valid (weight 1.0 each), inning invalid (weight 0.25):
        # 3.0 / 3.25 ≈ 0.92 — comfortably above the floor.
        self.assertGreater(score, 0.9)

    def test_ocr_exception_counts_as_invalid_read(self):
        def exploding_ocr(crop, field_name):
            raise RuntimeError("backend crashed")

        frames = _frames()
        self.assertEqual(score_template(_template("t", x=0.0), frames, exploding_ocr), 0.0)


class SelectionTests(unittest.TestCase):
    def test_picks_highest_scoring_candidate(self):
        frames = _frames(lit_x_range=(320, 384))  # overlay in the middle band
        default = _template("default", x=0.0)
        matching = _template("matching", x=0.5)

        with patch(
            "sidelinehd_extractor.template_probe.read_frames_at",
            side_effect=lambda path, stamps: iter(
                [(stamp, frames[0][1]) for stamp in stamps]
            ),
        ):
            result = probe_template(
                Path("video.mp4"),
                [default, matching],
                _lit_crop_ocr,
                probe_timestamps=[10.0, 20.0],
            )

        self.assertEqual(result.template.name, "matching")
        self.assertFalse(result.low_score)
        self.assertEqual(result.frames_probed, 2)
        self.assertEqual(set(result.scores), {"default", "matching"})

    def test_tie_breaks_toward_first_candidate_the_default(self):
        frames = _frames(lit_x_range=(0, 640))  # everything lit: all tie
        default = _template("default", x=0.0)
        other = _template("other", x=0.5)

        with patch(
            "sidelinehd_extractor.template_probe.read_frames_at",
            side_effect=lambda path, stamps: iter(
                [(stamp, frames[0][1]) for stamp in stamps]
            ),
        ):
            result = probe_template(
                Path("video.mp4"), [default, other], _lit_crop_ocr, probe_timestamps=[10.0]
            )

        self.assertEqual(result.template.name, "default")

    def test_below_floor_keeps_default_and_flags_low_score(self):
        default = _template("default", x=0.0)
        other = _template("other", x=0.5)

        def garbage_ocr(crop, field_name):
            return _result("~~~")

        with patch(
            "sidelinehd_extractor.template_probe.read_frames_at",
            side_effect=lambda path, stamps: iter(
                [(stamp, np.zeros((360, 640, 3), dtype=np.uint8)) for stamp in stamps]
            ),
        ):
            result = probe_template(
                Path("video.mp4"), [default, other], garbage_ocr, probe_timestamps=[10.0]
            )

        self.assertTrue(result.low_score)
        self.assertEqual(result.template.name, "default")
        self.assertLess(max(result.scores.values()), LOW_SCORE_FLOOR)

    def test_unreadable_timestamps_are_skipped(self):
        default = _template("default", x=0.0)

        def read_or_raise(path, stamps):
            for stamp in stamps:
                if stamp > 100:
                    raise ValueError("past end of video")
                yield stamp, _frames(count=1)[0][1]

        with patch(
            "sidelinehd_extractor.template_probe.read_frames_at",
            side_effect=read_or_raise,
        ):
            result = probe_template(
                Path("video.mp4"), [default], _lit_crop_ocr,
                probe_timestamps=[10.0, 500.0, 20.0],
            )

        self.assertEqual(result.frames_probed, 2)
        self.assertFalse(result.low_score)

    def test_requires_at_least_one_candidate(self):
        with self.assertRaises(ValueError):
            probe_template(Path("video.mp4"), [], _lit_crop_ocr, probe_timestamps=[1.0])


class TimestampTests(unittest.TestCase):
    def test_long_video_probes_first_third_percentages(self):
        stamps = probe_timestamps_for_duration(8640.0)  # 2.4h
        self.assertEqual(len(stamps), 5)
        self.assertAlmostEqual(stamps[0], 864.0)
        self.assertAlmostEqual(stamps[-1], 2592.0)

    def test_short_video_uses_fixed_30s_steps(self):
        stamps = probe_timestamps_for_duration(120.0)
        self.assertEqual(stamps, (30.0, 60.0, 90.0))

    def test_very_short_video_probes_midpoint(self):
        self.assertEqual(probe_timestamps_for_duration(20.0), (10.0,))

    def test_unknown_duration_uses_fixed_early_offsets(self):
        stamps = probe_timestamps_for_duration(None)
        self.assertEqual(len(stamps), 5)
        self.assertTrue(all(stamp <= 150.0 for stamp in stamps))


class RegistryTests(unittest.TestCase):
    def test_registry_has_packaged_default_first(self):
        candidates = candidate_overlay_templates()
        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual(candidates[0].name, "sidelinehd_640x360_active")
        for field in ("left_score", "right_score", "count"):
            self.assertIn(field, candidates[0].regions)

    def test_probe_with_single_packaged_candidate_selects_it(self):
        # Acceptance: one candidate, unconfigured run still selects it and
        # records scores/manifest data.
        candidates = candidate_overlay_templates()
        frame = np.full((360, 640, 3), 255, dtype=np.uint8)

        with patch(
            "sidelinehd_extractor.template_probe.read_frames_at",
            side_effect=lambda path, stamps: iter([(stamp, frame) for stamp in stamps]),
        ):
            result = probe_template(
                Path("video.mp4"), candidates, _lit_crop_ocr, probe_timestamps=[10.0]
            )

        self.assertEqual(result.template.name, "sidelinehd_640x360_active")
        manifest_entry = result.to_manifest()
        self.assertEqual(manifest_entry["selected"], "sidelinehd_640x360_active")
        self.assertIn("sidelinehd_640x360_active", manifest_entry["scores"])
        self.assertEqual(manifest_entry["floor"], LOW_SCORE_FLOOR)


class WorkflowIntegrationTests(unittest.TestCase):
    """run_game wiring: probe only when template is None + real OCR."""

    def _run(self, tmp_root, stages, probe_side_effect=None, **kwargs):
        from sidelinehd_extractor.events import EventDetectionResult
        from sidelinehd_extractor.models import Event, EventType, HalfInning
        from sidelinehd_extractor.processing import ProcessResult, write_jsonl
        from sidelinehd_extractor.state import StateParseResult
        from sidelinehd_extractor.workflow import run_game

        run_dir = tmp_root / "runs" / "game-run"
        process_result = ProcessResult(
            run_dir=run_dir,
            manifest_path=run_dir / "manifest.json",
            samples_path=run_dir / "samples.jsonl",
            sample_count=1,
            crop_count=1,
            field_read_stats={"left_score": {"sample_count": 1, "non_empty_count": 1}},
            warnings=[],
        )
        state_result = StateParseResult(
            input_path=run_dir / "samples.jsonl",
            output_path=run_dir / "states.jsonl",
            state_count=1,
        )
        event_result = EventDetectionResult(
            input_path=run_dir / "states.jsonl",
            output_path=run_dir / "events.jsonl",
            event_count=1,
        )
        run_dir.mkdir(parents=True)
        process_result.manifest_path.write_text("{}\n", encoding="utf-8")
        events = [
            Event(EventType.HALF_INNING_START, 600, "Top 1", inning=1, half=HalfInning.TOP)
        ]
        write_jsonl(event_result.output_path, events)

        with patch(
            "sidelinehd_extractor.workflow.probe_template",
            side_effect=probe_side_effect,
        ) as probe_mock, patch(
            "sidelinehd_extractor.workflow.process_video", return_value=process_result
        ), patch(
            "sidelinehd_extractor.workflow.parse_samples_file", return_value=state_result
        ), patch(
            "sidelinehd_extractor.workflow.detect_events_file", return_value=event_result
        ), patch(
            "sidelinehd_extractor.workflow.load_events", return_value=events
        ):
            result = run_game(
                video_path=Path("game.mp4"),
                output_dir=tmp_root / "runs",
                output_prefix=tmp_root / "scratch" / "full",
                stage_progress=stages.append,
                **kwargs,
            )
        return result, run_dir, probe_mock

    def test_probe_runs_for_unconfigured_ocr_run_and_records_manifest(self):
        from sidelinehd_extractor.template_probe import TemplateProbeResult

        probe_result = TemplateProbeResult(
            template=candidate_overlay_templates()[0],
            scores={"sidelinehd_640x360_active": 0.9},
            low_score=False,
            probe_timestamps=(10.0,),
            frames_probed=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stages = []
            _, run_dir, probe_mock = self._run(
                root,
                stages,
                probe_side_effect=lambda *args, **kwargs: probe_result,
                ocr=lambda crop, field: None,
            )
            probe_mock.assert_called_once()
            self.assertIn("probe", stages)
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            section = manifest["template_autodetect"]
            self.assertEqual(section["selected"], "sidelinehd_640x360_active")
            self.assertFalse(section["low_score"])

    def test_low_score_emits_warning_but_run_proceeds(self):
        from sidelinehd_extractor.template_probe import TemplateProbeResult
        from sidelinehd_extractor.workflow import TEMPLATE_LOW_SCORE_WARNING

        probe_result = TemplateProbeResult(
            template=candidate_overlay_templates()[0],
            scores={"sidelinehd_640x360_active": 0.05},
            low_score=True,
            probe_timestamps=(10.0,),
            frames_probed=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stages = []
            result, run_dir, _ = self._run(
                root,
                stages,
                probe_side_effect=lambda *args, **kwargs: probe_result,
                ocr=lambda crop, field: None,
            )
            self.assertEqual(result.event_count, 1)  # run completed
            self.assertIn(
                f"warning template-autodetect-low-score: {TEMPLATE_LOW_SCORE_WARNING}",
                stages,
            )
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["template_autodetect"]["low_score"])

    def test_probe_failure_degrades_to_default_with_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stages = []
            result, run_dir, _ = self._run(
                root,
                stages,
                probe_side_effect=RuntimeError("no frames"),
                ocr=lambda crop, field: None,
            )
            self.assertEqual(result.event_count, 1)
            self.assertIn("warning template-probe-failed: no frames", stages)
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertNotIn("template_autodetect", manifest)

    def test_no_probe_when_template_given_or_ocr_disabled_or_opted_out(self):
        from sidelinehd_extractor.template_probe import TemplateProbeResult

        cases = [
            {"template": candidate_overlay_templates()[0], "ocr": lambda c, f: None},
            {},  # default no_ocr
            {"ocr": lambda c, f: None, "auto_detect_template": False},
        ]
        for kwargs in cases:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                stages = []
                _, _, probe_mock = self._run(
                    root,
                    stages,
                    probe_side_effect=lambda *a, **k: TemplateProbeResult(
                        template=candidate_overlay_templates()[0],
                        scores={},
                        low_score=False,
                        probe_timestamps=(),
                        frames_probed=0,
                    ),
                    **kwargs,
                )
                probe_mock.assert_not_called()
                self.assertNotIn("probe", stages)


if __name__ == "__main__":
    unittest.main()
