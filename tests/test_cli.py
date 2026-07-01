import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from pathlib import Path

from sidelinehd_extractor.cli import (
    _default_run_fields,
    _format_roster_next_command,
    _read_roster_lines_interactive,
    build_parser,
    main,
)
from sidelinehd_extractor.config import load_roster


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
                "--no-inning-score",
                "--no-at-bat-inning-headers",
                "--batting-half",
                "top",
                "--min-at-bat-spacing",
                "60",
                "--min-at-bat-spacing-roster-confirmed",
                "25",
                "--no-order-validation",
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
                "--no-inning-score",
                "--no-at-bat-inning-headers",
                "--batting-half",
                "top",
                "--min-at-bat-spacing",
                "60",
                "--min-at-bat-spacing-roster-confirmed",
                "25",
                "--no-order-validation",
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
            "no_inning_score",
            "no_at_bat_inning_headers",
            "batting_half",
            "min_at_bat_spacing",
            "min_at_bat_spacing_roster_confirmed",
            "no_order_validation",
        ]
        for attribute in shared_attributes:
            with self.subTest(attribute=attribute):
                self.assertEqual(getattr(run_game, attribute), getattr(run_youtube, attribute))

        self.assertEqual(run_game.video_path, Path("game.mp4"))
        self.assertEqual(run_youtube.url, "https://youtu.be/example")

    def test_run_commands_default_batting_half_to_auto(self):
        parser = build_parser()
        run_game = parser.parse_args(["run-game", "game.mp4"])
        run_youtube = parser.parse_args(["run-youtube", "https://youtu.be/example"])
        detect_events = parser.parse_args(["detect-events", "runs/game"])

        self.assertEqual(run_game.batting_half, "auto")
        self.assertEqual(run_youtube.batting_half, "auto")
        self.assertEqual(detect_events.batting_half, "both")
        self.assertFalse(run_game.no_order_validation)
        self.assertFalse(run_youtube.no_order_validation)
        self.assertFalse(detect_events.no_order_validation)

    def test_default_run_fields_include_lineup_batter_number(self):
        parser = build_parser()
        run_game = parser.parse_args(["run-game", "game.mp4"])

        self.assertEqual(
            _default_run_fields(run_game),
            [
                "inning",
                "count",
                "left_score",
                "right_score",
                "lineup_strip",
                "batter_card_name",
                "batter_card_number",
                "batter_number",
            ],
        )

    def test_publish_helper_defaults_to_run_export_directory(self):
        parser = build_parser()
        publish_helper = parser.parse_args(["publish-helper", "runs/game"])

        self.assertIsNone(publish_helper.output_dir)
        self.assertFalse(publish_helper.no_html)

    def test_publish_helper_can_disable_html(self):
        parser = build_parser()
        publish_helper = parser.parse_args(["publish-helper", "runs/game", "--no-html"])

        self.assertTrue(publish_helper.no_html)

    def test_setup_roster_writes_piped_roster(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "stars.csv"
            stdin = io.StringIO("#22 Maya R.\n#26 Amelia V.\n")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "setup-roster",
                        "--team-name",
                        "Stars",
                        "--output",
                        str(output_path),
                    ]
                )

            loaded = load_roster(output_path, team_name="Stars")

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("Wrote 2 players", stdout.getvalue())
        self.assertEqual(loaded.name_for_number("22"), "Maya R.")
        self.assertEqual(loaded.number_for_name("Amelia"), "26")

    def test_setup_roster_requires_team_name_for_piped_input(self):
        stdin = io.StringIO("#22 Maya R.\n")
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["setup-roster"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("--team-name is required", stderr.getvalue())

    def test_setup_roster_rejects_duplicate_numbers_without_writing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "stars.csv"
            stdin = io.StringIO("#22 Maya R.\n#22 Other Player\n")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "setup-roster",
                        "--team-name",
                        "Stars",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertFalse(output_path.exists())

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("duplicate jersey number", stderr.getvalue())

    def test_setup_roster_rejects_invalid_line_without_writing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "stars.csv"
            stdin = io.StringIO("Maya R.\n")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "setup-roster",
                        "--team-name",
                        "Stars",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertFalse(output_path.exists())

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("could not parse roster line 1", stderr.getvalue())

    def test_setup_roster_rejects_empty_input(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "stars.csv"
            stdin = io.StringIO("\n\n")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "setup-roster",
                        "--team-name",
                        "Stars",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertFalse(output_path.exists())

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("no roster lines entered", stderr.getvalue())

    def test_setup_roster_tty_confirmation_uses_resolved_output_path(self):
        class FakeTTY:
            def isatty(self):
                return True

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "stars.csv"
            stdout = io.StringIO()
            stderr = io.StringIO()
            input_values = ["#22 Maya R.", "", "#26 Amelia V.", "", "", "y"]

            with (
                patch("sys.stdin", FakeTTY()),
                patch("builtins.input", side_effect=input_values) as input_mock,
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main(
                    [
                        "setup-roster",
                        "--team-name",
                        "Stars",
                        "--output",
                        str(output_path),
                    ]
                )

            prompts = [call.args[0] for call in input_mock.call_args_list if call.args]

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertTrue(any(str(output_path.resolve()) in prompt for prompt in prompts))

    def test_format_roster_next_command_mentions_roster_and_template(self):
        command = _format_roster_next_command(Path("rosters/stars.csv"))

        self.assertIn("--roster rosters/stars.csv", command)
        self.assertIn("--template YOUR_TEMPLATE", command)

    def test_read_roster_lines_interactive_stops_after_two_blank_lines(self):
        values = iter(["#22 Maya R.", "", "#26 Amelia V.", "", ""])

        with patch("builtins.input", side_effect=lambda: next(values)):
            lines = _read_roster_lines_interactive()

        self.assertEqual(lines, ["#22 Maya R.", "", "#26 Amelia V.", ""])

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
