import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from sidelinehd_extractor.models import OCRSample, OverlayTemplate, RegionFraction, Video
from sidelinehd_extractor.ocr import OCRBackendResult
from sidelinehd_extractor.processing import (
    SamplingOptions,
    field_read_warnings,
    process_video,
    sample_timestamps,
    select_template_regions,
    summarize_field_reads,
)


class ProcessingTests(unittest.TestCase):
    def test_sample_timestamps_uses_interval_and_bounds(self):
        self.assertEqual(sample_timestamps(12.0, 5.0), [0.0, 5.0, 10.0])

    def test_sample_timestamps_respects_start_and_end(self):
        self.assertEqual(
            sample_timestamps(60.0, 2.5, start_seconds=10.0, end_seconds=15.0),
            [10.0, 12.5, 15.0],
        )

    def test_sample_timestamps_rejects_bad_interval(self):
        with self.assertRaises(ValueError):
            sample_timestamps(60.0, 0)

    def test_select_template_regions_filters_fields(self):
        template = OverlayTemplate(
            name="test",
            regions={
                "count": RegionFraction(0, 0, 0.1, 0.1),
                "inning": RegionFraction(0.1, 0, 0.1, 0.1),
            },
        )

        selected = select_template_regions(template, ["inning"])

        self.assertEqual(list(selected.keys()), ["inning"])

    def test_select_template_regions_rejects_unknown_field(self):
        template = OverlayTemplate(
            name="test",
            regions={"count": RegionFraction(0, 0, 0.1, 0.1)},
        )

        with self.assertRaises(ValueError):
            select_template_regions(template, ["missing"])

    def test_select_template_regions_skips_missing_optional_game_status(self):
        template = OverlayTemplate(
            name="test",
            regions={"inning": RegionFraction(0.1, 0, 0.1, 0.1)},
        )

        selected = select_template_regions(template, ["inning", "game_status"])

        self.assertEqual(list(selected.keys()), ["inning"])

    def test_progress_callback_shape_for_process_video(self):
        # The callback contract is intentionally plain so the CLI can print status
        # without coupling process_video to terminal output.
        calls = []

        def progress(timestamp_index, total_timestamps, timestamp_seconds, sample_count, total_samples):
            calls.append(
                (timestamp_index, total_timestamps, timestamp_seconds, sample_count, total_samples)
            )

        progress(1, 3, 10.0, 4, 12)

        self.assertEqual(calls, [(1, 3, 10.0, 4, 12)])

    def test_process_video_does_not_hash_video_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            template = OverlayTemplate(
                name="test",
                regions={"count": RegionFraction(0, 0, 0.1, 0.1)},
            )
            with patch(
                "sidelinehd_extractor.processing.probe_video",
                return_value=Video(Path("game.mp4"), duration_seconds=0.0, width=10, height=10, fps=30),
            ) as probe:
                with patch("sidelinehd_extractor.processing.read_frames_at", return_value=[(0.0, object())]):
                    with patch("sidelinehd_extractor.processing.crop_frame", return_value=object()):
                        process_video(
                            video_path=Path("game.mp4"),
                            output_dir=Path(directory),
                            template=template,
                            sampling=SamplingOptions(),
                        )

            probe.assert_called_once_with(Path("game.mp4"), compute_hash=False)

    def test_process_video_can_hash_video_when_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            template = OverlayTemplate(
                name="test",
                regions={"count": RegionFraction(0, 0, 0.1, 0.1)},
            )
            with patch(
                "sidelinehd_extractor.processing.probe_video",
                return_value=Video(
                    Path("game.mp4"),
                    sha256="abc123",
                    duration_seconds=0.0,
                    width=10,
                    height=10,
                    fps=30,
                ),
            ) as probe:
                with patch("sidelinehd_extractor.processing.read_frames_at", return_value=[(0.0, object())]):
                    with patch("sidelinehd_extractor.processing.crop_frame", return_value=object()):
                        result = process_video(
                            video_path=Path("game.mp4"),
                            output_dir=Path(directory),
                            template=template,
                            sampling=SamplingOptions(compute_video_hash=True),
                        )

            probe.assert_called_once_with(Path("game.mp4"), compute_hash=True)
            self.assertIn('"sha256": "abc123"', result.manifest_path.read_text())
            self.assertIn('"compute_video_hash": true', result.manifest_path.read_text())

    def test_process_video_honors_the_sampling_field_selection(self):
        # 22b: ``fields`` travels inside SamplingOptions. If process_video read
        # its own default instead, every region would be OCR'd — slower, and a
        # different samples file than the caller asked for.
        with tempfile.TemporaryDirectory() as directory:
            template = OverlayTemplate(
                name="test",
                regions={
                    "count": RegionFraction(0, 0, 0.1, 0.1),
                    "inning": RegionFraction(0.1, 0, 0.1, 0.1),
                },
            )

            with patch(
                "sidelinehd_extractor.processing.probe_video",
                return_value=Video(Path("game.mp4"), duration_seconds=0.0, width=10, height=10, fps=30),
            ):
                with patch("sidelinehd_extractor.processing.read_frames_at", return_value=[(0.0, object())]):
                    with patch("sidelinehd_extractor.processing.crop_frame", return_value=object()):
                        result = process_video(
                            video_path=Path("game.mp4"),
                            output_dir=Path(directory),
                            template=template,
                            sampling=SamplingOptions(fields=["inning"]),
                        )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["fields"], ["inning"])
            self.assertEqual(result.sample_count, 1)

    def test_process_video_persists_ocr_source_detail(self):
        with tempfile.TemporaryDirectory() as directory:
            template = OverlayTemplate(
                name="test",
                regions={"lineup_strip": RegionFraction(0, 0, 0.1, 0.1)},
            )

            def ocr(_image, _field_name):
                return OCRBackendResult(
                    text="26\n",
                    normalized_text="26",
                    confidence=0.82,
                    backend="test",
                    source_detail="lineup_highlight",
                )

            with patch(
                "sidelinehd_extractor.processing.probe_video",
                return_value=Video(Path("game.mp4"), duration_seconds=0.0, width=10, height=10, fps=30),
            ):
                with patch("sidelinehd_extractor.processing.read_frames_at", return_value=[(0.0, object())]):
                    with patch("sidelinehd_extractor.processing.crop_frame", return_value=object()):
                        result = process_video(
                            video_path=Path("game.mp4"),
                            output_dir=Path(directory),
                            template=template,
                            ocr=ocr,
                            sampling=SamplingOptions(),
                        )

            self.assertIn(
                '"source_detail": "lineup_highlight"',
                result.samples_path.read_text(encoding="utf-8"),
            )
            self.assertIn('"confidence": 0.82', result.samples_path.read_text(encoding="utf-8"))

    def test_field_read_warnings_flags_configured_field_that_never_reads(self):
        samples = [
            OCRSample(0, "left_score", "1", normalized_text="1"),
            OCRSample(0, "right_score", "", normalized_text=""),
            OCRSample(5, "left_score", "1", normalized_text="1"),
            OCRSample(5, "right_score", "", normalized_text=""),
        ]

        stats = summarize_field_reads(samples, ["left_score", "right_score"])
        warnings = field_read_warnings(stats)

        self.assertEqual(stats["left_score"], {"sample_count": 2, "non_empty_count": 2})
        self.assertEqual(stats["right_score"], {"sample_count": 2, "non_empty_count": 0})
        self.assertEqual(warnings[0]["code"], "field-never-read")
        self.assertEqual(warnings[0]["field"], "right_score")

    def test_process_video_records_field_read_stats_and_warnings_in_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            template = OverlayTemplate(
                name="test",
                regions={
                    "left_score": RegionFraction(0, 0, 0.1, 0.1),
                    "right_score": RegionFraction(0.1, 0, 0.1, 0.1),
                },
            )

            def ocr(_image, field_name):
                text = "1" if field_name == "left_score" else ""
                return OCRBackendResult(text=text, normalized_text=text, backend="test")

            ocr.tesseract_version = "5.3.0"

            with patch(
                "sidelinehd_extractor.processing.probe_video",
                return_value=Video(Path("game.mp4"), duration_seconds=0.0, width=10, height=10, fps=30),
            ):
                with patch("sidelinehd_extractor.processing.read_frames_at", return_value=[(0.0, object())]):
                    with patch("sidelinehd_extractor.processing.crop_frame", return_value=object()):
                        result = process_video(
                            video_path=Path("game.mp4"),
                            output_dir=Path(directory),
                            template=template,
                            ocr=ocr,
                            sampling=SamplingOptions(),
                        )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["field_read_stats"]["right_score"],
                {"sample_count": 1, "non_empty_count": 0},
            )
            self.assertEqual(manifest["warnings"][0]["code"], "field-never-read")
            self.assertEqual(manifest["warnings"][0]["field"], "right_score")
            self.assertEqual(manifest["tesseract_version"], "5.3.0")
            self.assertEqual(result.warnings, manifest["warnings"])

    def test_process_video_parallel_ocr_matches_serial_sample_order(self):
        with tempfile.TemporaryDirectory() as directory:
            template = OverlayTemplate(
                name="test",
                regions={
                    "slow": RegionFraction(0, 0, 0.1, 0.1),
                    "fast": RegionFraction(0.1, 0, 0.1, 0.1),
                },
            )

            def ocr(_image, field_name):
                if field_name == "slow":
                    time.sleep(0.01)
                return OCRBackendResult(
                    text=f"{field_name}\n",
                    normalized_text=field_name,
                    backend="test",
                )

            def run(workers):
                with patch(
                    "sidelinehd_extractor.processing.probe_video",
                    return_value=Video(
                        Path("game.mp4"), duration_seconds=5.0, width=10, height=10, fps=30
                    ),
                ):
                    with patch(
                        "sidelinehd_extractor.processing.read_frames_at",
                        return_value=[(0.0, object()), (5.0, object())],
                    ):
                        with patch(
                            "sidelinehd_extractor.processing.crop_frame", return_value=object()
                        ):
                            result = process_video(
                                video_path=Path("game.mp4"),
                                output_dir=Path(directory),
                                template=template,
                                ocr=ocr,
                                sampling=SamplingOptions(ocr_workers=workers),
                            )
                rows = [
                    json.loads(line)
                    for line in result.samples_path.read_text(encoding="utf-8").splitlines()
                ]
                return [
                    (
                        row["timestamp_seconds"],
                        row["field_name"],
                        row["raw_text"],
                        row["normalized_text"],
                        row.get("crop_path"),
                    )
                    for row in rows
                ]

            serial_rows = run(1)
            parallel_rows = run(2)

        self.assertEqual(serial_rows, parallel_rows)
        self.assertEqual(
            [row[1] for row in parallel_rows],
            ["slow", "fast", "slow", "fast"],
        )

    def test_process_video_rejects_invalid_ocr_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            template = OverlayTemplate(
                name="test",
                regions={"count": RegionFraction(0, 0, 0.1, 0.1)},
            )

            # M4 22b: an impossible worker count is now rejected when the
            # options are built, before a video is ever opened.
            with self.assertRaises(ValueError):
                process_video(
                    video_path=Path("game.mp4"),
                    output_dir=Path(directory),
                    template=template,
                    sampling=SamplingOptions(ocr_workers=0),
                )

    def test_process_video_does_not_warn_for_no_ocr_debug_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            template = OverlayTemplate(
                name="test",
                regions={"right_score": RegionFraction(0, 0, 0.1, 0.1)},
            )

            with patch(
                "sidelinehd_extractor.processing.probe_video",
                return_value=Video(Path("game.mp4"), duration_seconds=0.0, width=10, height=10, fps=30),
            ):
                with patch("sidelinehd_extractor.processing.read_frames_at", return_value=[(0.0, object())]):
                    with patch("sidelinehd_extractor.processing.crop_frame", return_value=object()):
                        result = process_video(
                            video_path=Path("game.mp4"),
                            output_dir=Path(directory),
                            template=template,
                            sampling=SamplingOptions(),
                        )

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["warnings"], [])
            self.assertEqual(result.warnings, [])


if __name__ == "__main__":
    unittest.main()
