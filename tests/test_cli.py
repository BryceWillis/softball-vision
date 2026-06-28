import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from pathlib import Path

from sidelinehd_extractor.cli import build_parser, main


class CLITests(unittest.TestCase):
    def test_run_commands_share_processing_arguments(self):
        parser = build_parser()
        run_game = parser.parse_args(
            [
                "run-game",
                "game.mp4",
                "--template",
                "template.json",
                "--roster",
                "roster.csv",
                "--team-name",
                "Smash It",
                "--sample-every",
                "2.5",
                "--start",
                "1:00",
                "--end",
                "2:00",
                "--ocr",
                "none",
                "--progress-every",
                "10",
                "--quiet",
                "--field",
                "inning,count",
                "--no-crops",
                "--hash-video",
                "--output-prefix",
                "scratch/full",
                "--corrections",
                "corrections.csv",
                "--chapter-intro-label",
                "Warmups",
                "--no-chapter-intro",
                "--no-at-bat-inning-headers",
                "--batting-half",
                "top",
                "--min-at-bat-spacing",
                "60",
            ]
        )
        run_youtube = parser.parse_args(
            [
                "run-youtube",
                "https://youtu.be/example",
                "--template",
                "template.json",
                "--roster",
                "roster.csv",
                "--team-name",
                "Smash It",
                "--sample-every",
                "2.5",
                "--start",
                "1:00",
                "--end",
                "2:00",
                "--ocr",
                "none",
                "--progress-every",
                "10",
                "--quiet",
                "--field",
                "inning,count",
                "--no-crops",
                "--hash-video",
                "--output-prefix",
                "scratch/full",
                "--corrections",
                "corrections.csv",
                "--chapter-intro-label",
                "Warmups",
                "--no-chapter-intro",
                "--no-at-bat-inning-headers",
                "--batting-half",
                "top",
                "--min-at-bat-spacing",
                "60",
            ]
        )

        shared_attributes = [
            "output_dir",
            "template",
            "roster",
            "team_name",
            "sample_every",
            "start",
            "end",
            "ocr",
            "progress_every",
            "quiet",
            "field",
            "no_crops",
            "hash_video",
            "output_prefix",
            "corrections",
            "chapter_intro_label",
            "no_chapter_intro",
            "no_at_bat_inning_headers",
            "batting_half",
            "min_at_bat_spacing",
        ]
        for attribute in shared_attributes:
            with self.subTest(attribute=attribute):
                self.assertEqual(getattr(run_game, attribute), getattr(run_youtube, attribute))

        self.assertEqual(run_game.video_path, Path("game.mp4"))
        self.assertEqual(run_youtube.url, "https://youtu.be/example")

    def test_main_prints_clean_error_for_value_error(self):
        stderr = io.StringIO()
        stdout = io.StringIO()

        with redirect_stderr(stderr), redirect_stdout(stdout):
            exit_code = main(
                [
                    "extract-frame",
                    "missing.mp4",
                    "scratch/crop.png",
                    "--timestamp",
                    "0",
                    "--x",
                    "0.9",
                    "--y",
                    "0",
                    "--width",
                    "0.2",
                    "--height",
                    "0.1",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Error: x + width must be <= 1.0", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_main_prints_clean_error_for_missing_file(self):
        stderr = io.StringIO()
        stdout = io.StringIO()

        with redirect_stderr(stderr), redirect_stdout(stdout):
            exit_code = main(["parse-states", "runs/does-not-exist"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Error:", stderr.getvalue())
        self.assertIn("runs/does-not-exist", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
