import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sidelinehd_extractor.events import EventDetectionResult
from sidelinehd_extractor.exports import PROJECT_CREDIT
from sidelinehd_extractor.models import Event, EventType, HalfInning
from sidelinehd_extractor.processing import ProcessResult, write_json, write_jsonl
from sidelinehd_extractor.state import StateParseResult
from sidelinehd_extractor.workflow import (
    RunGameResult,
    export_paths,
    finalize_run_exports,
    run_game,
    run_youtube_game,
)
from sidelinehd_extractor.youtube import DownloadResult


class WorkflowTests(unittest.TestCase):
    def test_export_paths_uses_prefix(self):
        chapters_path, at_bats_path = export_paths(Path("runs/game"), Path("scratch/full"))

        self.assertEqual(chapters_path, Path("scratch/full_chapters.txt"))
        self.assertEqual(at_bats_path, Path("scratch/full_at_bats.txt"))

    def test_export_paths_default_uses_game_named_folder(self):
        chapters_path, at_bats_path = export_paths(Path("runs/game-20260627-142836"))

        self.assertEqual(
            chapters_path, Path("runs/game-20260627-142836/exports/game/game_chapters.txt")
        )
        self.assertEqual(
            at_bats_path, Path("runs/game-20260627-142836/exports/game/game_at_bats.txt")
        )

    def test_run_game_chains_pipeline_and_writes_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "runs" / "game-run"
            output_prefix = root / "scratch" / "full"
            process_result = ProcessResult(
                run_dir=run_dir,
                manifest_path=run_dir / "manifest.json",
                samples_path=run_dir / "samples.jsonl",
                sample_count=4,
                crop_count=4,
                warnings=[
                    {
                        "code": "field-never-read",
                        "field": "right_score",
                        "message": "Configured OCR field 'right_score' was empty.",
                    }
                ],
            )
            state_result = StateParseResult(
                input_path=run_dir / "samples.jsonl",
                output_path=run_dir / "states.jsonl",
                state_count=1,
            )
            event_result = EventDetectionResult(
                input_path=run_dir / "states.jsonl",
                output_path=run_dir / "events.jsonl",
                event_count=2,
            )
            run_dir.mkdir(parents=True)
            write_json(
                process_result.manifest_path,
                {
                    "warnings": [
                        {
                            "code": "field-never-read",
                            "field": "right_score",
                            "message": "Configured OCR field 'right_score' was empty.",
                        }
                    ]
                },
            )
            events = [
                Event(EventType.HALF_INNING_START, 600, "Top 1", inning=1, half=HalfInning.TOP),
                Event(
                    EventType.AT_BAT_START,
                    605,
                    "Maya R. (#22)",
                    inning=1,
                    player_number="22",
                    player_name="Maya R.",
                    metadata={"ocr_player_number": "28"},
                ),
            ]
            write_jsonl(event_result.output_path, events)
            stages = []

            with patch(
                "sidelinehd_extractor.workflow.process_video", return_value=process_result
            ) as process:
                with patch(
                    "sidelinehd_extractor.workflow.parse_samples_file", return_value=state_result
                ) as parse:
                    with patch(
                        "sidelinehd_extractor.workflow.detect_events_file",
                        return_value=event_result,
                    ) as detect:
                        with patch(
                            "sidelinehd_extractor.workflow.load_events", return_value=events
                        ):
                            result = run_game(
                                video_path=Path("game.mp4"),
                                output_dir=root / "runs",
                                output_prefix=output_prefix,
                                compute_video_hash=True,
                                stage_progress=stages.append,
                            )

            process.assert_called_once()
            self.assertTrue(process.call_args.kwargs["compute_video_hash"])
            parse.assert_called_once_with(process_result.samples_path)
            detect.assert_called_once_with(
                state_result.output_path,
                roster=None,
                batting_half=None,
                min_at_bat_spacing_seconds=45.0,
                min_at_bat_spacing_roster_confirmed_seconds=20.0,
                min_game_final_observations=3,
                order_validation=True,
            )
            self.assertEqual(
                stages,
                [
                    "process",
                    "warning field-never-read: right_score",
                    "parse-states",
                    "detect-events",
                    "export",
                    "review-report",
                ],
            )
            self.assertEqual(result.event_count, 2)
            # Item 48: the review report is now a standard run artifact.
            report_text = (run_dir / "review_report.md").read_text(encoding="utf-8")
            self.assertIn("Flagged events: 1", report_text)
            self.assertIn("## Run Warnings", report_text)
            self.assertIn("right_score", report_text)
            self.assertEqual(
                (root / "scratch" / "full_chapters.txt").read_text(),
                f"0:00 Pregame\n10:00 Top 1\n\n{PROJECT_CREDIT}\n",
            )
            self.assertEqual(
                (root / "scratch" / "full_at_bats.txt").read_text(),
                f"1st Inning\n10:05 Maya R. (#22)\n\n{PROJECT_CREDIT}\n",
            )
            self.assertIn(
                '"min_at_bat_spacing_roster_confirmed_seconds": 20.0',
                process_result.manifest_path.read_text(encoding="utf-8"),
            )
            self.assertIn(
                '"min_game_final_observations": 3',
                process_result.manifest_path.read_text(encoding="utf-8"),
            )
            self.assertIn(
                '"order_validation_requested": true',
                process_result.manifest_path.read_text(encoding="utf-8"),
            )
            self.assertIn(
                '"order_validation_ran": false',
                process_result.manifest_path.read_text(encoding="utf-8"),
            )

    def _run_game_with_stubbed_pipeline(self, root, stages, **run_game_kwargs):
        """Drive run_game with the processing layers stubbed, as the chain test does."""

        run_dir = root / "runs" / "game-run"
        process_result = ProcessResult(
            run_dir=run_dir,
            manifest_path=run_dir / "manifest.json",
            samples_path=run_dir / "samples.jsonl",
            sample_count=1,
            crop_count=1,
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

        with patch("sidelinehd_extractor.workflow.process_video", return_value=process_result):
            with patch(
                "sidelinehd_extractor.workflow.parse_samples_file", return_value=state_result
            ):
                with patch(
                    "sidelinehd_extractor.workflow.detect_events_file", return_value=event_result
                ):
                    with patch("sidelinehd_extractor.workflow.load_events", return_value=events):
                        result = run_game(
                            video_path=Path("game.mp4"),
                            output_dir=root / "runs",
                            output_prefix=root / "scratch" / "full",
                            stage_progress=stages.append,
                            **run_game_kwargs,
                        )
        return result, run_dir

    def test_run_game_review_report_failure_degrades_without_failing_the_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stages = []

            with patch(
                "sidelinehd_extractor.workflow.write_review_report",
                side_effect=RuntimeError("report exploded"),
            ):
                result, run_dir = self._run_game_with_stubbed_pipeline(root, stages)

            self.assertEqual(result.event_count, 1)
            self.assertIn("warning review-report-failed: report exploded", stages)
            self.assertFalse((run_dir / "review_report.md").exists())

    def test_run_game_can_opt_out_of_review_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stages = []

            result, run_dir = self._run_game_with_stubbed_pipeline(
                root, stages, generate_review_report=False
            )

            self.assertEqual(result.event_count, 1)
            self.assertNotIn("review-report", stages)
            self.assertFalse((run_dir / "review_report.md").exists())

    def test_run_game_persists_export_options_in_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            _, run_dir = self._run_game_with_stubbed_pipeline(root, [])

            manifest = (run_dir / "manifest.json").read_text(encoding="utf-8")
            self.assertIn('"include_chapter_intro": true', manifest)
            self.assertIn('"chapter_intro_label": "Pregame"', manifest)
            self.assertIn('"include_at_bat_inning_headers": true', manifest)
            self.assertIn('"output_prefix"', manifest)

    def test_finalize_run_exports_reuses_manifest_persisted_options(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "runs" / "game-run"
            run_dir.mkdir(parents=True)
            prefix = root / "scratch" / "redo"
            write_json(
                run_dir / "manifest.json",
                {
                    "export": {
                        "include_chapter_intro": False,
                        "chapter_intro_label": "Pregame",
                        "include_inning_score": True,
                        "include_at_bat_inning_headers": False,
                        "output_prefix": str(prefix),
                    }
                },
            )
            write_jsonl(
                run_dir / "events.jsonl",
                [
                    Event(
                        EventType.HALF_INNING_START, 600, "Top 1", inning=1, half=HalfInning.TOP
                    ),
                    Event(
                        EventType.AT_BAT_START,
                        605,
                        "Maya R. (#22)",
                        inning=1,
                        player_number="22",
                        player_name="Maya R.",
                    ),
                ],
            )

            chapters_path, at_bats_path = finalize_run_exports(run_dir)

            # Persisted options honored: no intro line, no inning headers, and
            # the persisted output prefix decided the file locations.
            self.assertEqual(chapters_path, prefix.with_name("redo_chapters.txt"))
            chapters_text = chapters_path.read_text(encoding="utf-8")
            self.assertNotIn("Pregame", chapters_text)
            self.assertIn("10:00 Top 1", chapters_text)
            at_bats_text = at_bats_path.read_text(encoding="utf-8")
            self.assertNotIn("1st Inning", at_bats_text)
            self.assertIn("10:05 Maya R. (#22)", at_bats_text)
            # The item 48 review report is refreshed as part of finalize.
            self.assertTrue((run_dir / "review_report.md").exists())

    def test_run_youtube_game_downloads_then_runs_pipeline(self):
        download = DownloadResult(
            url="https://youtu.be/example",
            output_dir=Path("videos"),
            video_path=Path("videos/game.mp4"),
            command=["yt-dlp", "https://youtu.be/example"],
            stdout="videos/game.mp4\n",
            stderr="",
        )
        run_result = RunGameResult(
            run_dir=Path("runs/game"),
            manifest_path=Path("runs/game/manifest.json"),
            samples_path=Path("runs/game/samples.jsonl"),
            states_path=Path("runs/game/states.jsonl"),
            events_path=Path("runs/game/events.jsonl"),
            chapters_path=Path("scratch/full_chapters.txt"),
            at_bats_path=Path("scratch/full_at_bats.txt"),
            sample_count=4,
            state_count=1,
            event_count=2,
        )
        stages = []

        with patch(
            "sidelinehd_extractor.workflow.download_youtube_video", return_value=download
        ) as dl:
            with patch("sidelinehd_extractor.workflow.run_game", return_value=run_result) as run:
                result = run_youtube_game(
                    url="https://youtu.be/example",
                    video_dir=Path("videos"),
                    output_dir=Path("runs"),
                    output_prefix=Path("scratch/full"),
                    compute_video_hash=True,
                    stage_progress=stages.append,
                )

        dl.assert_called_once()
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["video_path"], Path("videos/game.mp4"))
        self.assertEqual(run.call_args.kwargs["output_prefix"], Path("scratch/full"))
        self.assertTrue(run.call_args.kwargs["compute_video_hash"])
        self.assertEqual(run.call_args.kwargs["min_game_final_observations"], 3)
        self.assertTrue(run.call_args.kwargs["generate_review_report"])
        self.assertEqual(result.download, download)
        self.assertEqual(result.run, run_result)
        self.assertEqual(stages, ["download"])


if __name__ == "__main__":
    unittest.main()
