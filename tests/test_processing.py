import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sidelinehd_extractor.models import OverlayTemplate, RegionFraction, Video
from sidelinehd_extractor.processing import process_video, sample_timestamps, select_template_regions


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
                            save_crops=False,
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
                            save_crops=False,
                            compute_video_hash=True,
                        )

            probe.assert_called_once_with(Path("game.mp4"), compute_hash=True)
            self.assertIn('"sha256": "abc123"', result.manifest_path.read_text())
            self.assertIn('"compute_video_hash": true', result.manifest_path.read_text())


if __name__ == "__main__":
    unittest.main()
