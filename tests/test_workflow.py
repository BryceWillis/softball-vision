import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sidelinehd_extractor.events import EventDetectionResult
from sidelinehd_extractor.exports import PROJECT_CREDIT
from sidelinehd_extractor.models import Event, EventType, HalfInning
from sidelinehd_extractor.processing import ProcessResult
from sidelinehd_extractor.state import StateParseResult
from sidelinehd_extractor.workflow import RunGameResult, export_paths, run_game, run_youtube_game
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
            process_result.manifest_path.write_text("{}\n", encoding="utf-8")
            events = [
                Event(EventType.HALF_INNING_START, 600, "Top 1", inning=1, half=HalfInning.TOP),
                Event(
                    EventType.AT_BAT_START,
                    605,
                    "Maya R. (#22)",
                    inning=1,
                    player_number="22",
                    player_name="Maya R.",
                ),
            ]
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
            self.assertEqual(stages, ["process", "parse-states", "detect-events", "export"])
            self.assertEqual(result.event_count, 2)
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
        self.assertEqual(result.download, download)
        self.assertEqual(result.run, run_result)
        self.assertEqual(stages, ["download"])


if __name__ == "__main__":
    unittest.main()
