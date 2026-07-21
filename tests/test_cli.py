import dataclasses
import io
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from unittest.mock import patch

from pathlib import Path

from sidelinehd_extractor.cli import (
    _apply_config_defaults,
    _default_run_fields,
    _detection_config_from_args,
    _format_roster_next_command,
    _next_commands,
    _offer_config_update,
    _read_roster_lines_interactive,
    build_parser,
    main,
)
from sidelinehd_extractor.config import load_project_config, load_roster
from sidelinehd_extractor.events import DetectionConfig
from sidelinehd_extractor.models import HalfInning


@contextmanager
def _working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


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
                "--ocr-workers",
                "2",
                "--quiet",
                "--field",
                "inning,count",
                "--save-crops",
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
                "--min-game-final-observations",
                "4",
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
                "--ocr-workers",
                "2",
                "--quiet",
                "--field",
                "inning,count",
                "--save-crops",
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
                "--min-game-final-observations",
                "4",
                "--no-order-validation",
            ]
        )
        run_playlist = parser.parse_args(
            [
                "run-playlist",
                "https://youtube.com/playlist?list=example",
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
                "--ocr-workers",
                "2",
                "--quiet",
                "--field",
                "inning,count",
                "--save-crops",
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
                "--min-game-final-observations",
                "4",
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
            "ocr_workers",
            "quiet",
            "field",
            "save_crops",
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
            "min_game_final_observations",
            "no_order_validation",
        ]
        for attribute in shared_attributes:
            with self.subTest(attribute=attribute):
                self.assertEqual(getattr(run_game, attribute), getattr(run_youtube, attribute))
                self.assertEqual(getattr(run_game, attribute), getattr(run_playlist, attribute))

        self.assertEqual(run_game.video_path, Path("game.mp4"))
        self.assertEqual(run_youtube.url, "https://youtu.be/example")
        self.assertEqual(run_playlist.url, "https://youtube.com/playlist?list=example")
        self.assertTrue(run_game.save_crops)
        self.assertEqual(run_game.ocr_workers, 2)

    def test_run_commands_default_batting_half_to_auto(self):
        parser = build_parser()
        run_game = parser.parse_args(["run-game", "game.mp4"])
        run_youtube = parser.parse_args(["run-youtube", "https://youtu.be/example"])
        run_playlist = parser.parse_args(["run-playlist", "https://youtube.com/playlist"])
        detect_events = parser.parse_args(["detect-events", "runs/game"])

        self.assertEqual(run_game.batting_half, "auto")
        self.assertEqual(run_youtube.batting_half, "auto")
        self.assertEqual(run_playlist.batting_half, "auto")
        self.assertEqual(detect_events.batting_half, "both")
        self.assertFalse(run_game.no_order_validation)
        self.assertFalse(run_youtube.no_order_validation)
        self.assertFalse(run_playlist.no_order_validation)
        self.assertFalse(detect_events.no_order_validation)
        self.assertEqual(run_game.min_game_final_observations, 3)
        self.assertEqual(run_youtube.min_game_final_observations, 3)
        self.assertEqual(run_playlist.min_game_final_observations, 3)
        self.assertEqual(detect_events.min_game_final_observations, 3)
        self.assertFalse(run_game.save_crops)
        self.assertFalse(run_youtube.save_crops)
        self.assertFalse(run_playlist.save_crops)
        self.assertIsNone(run_game.ocr_workers)

    def test_detection_config_from_argv_matches_the_dataclass_defaults(self):
        # M4: the parsers advertise DetectionConfig's defaults rather than
        # their own literals, so a tuning change lands in one place. The run
        # commands' only difference is --batting-half auto (the CLI surface,
        # unchanged); detect-events has no auto choice because inference runs
        # a layer above it.
        parser = build_parser()
        run_argvs = (
            ["run-game", "game.mp4"],
            ["run-youtube", "https://youtu.be/example"],
            ["run-playlist", "https://youtube.com/playlist"],
        )

        for argv in run_argvs:
            with self.subTest(command=argv[0]):
                config = _detection_config_from_args(parser.parse_args(argv))
                self.assertEqual(config, DetectionConfig(auto_detect_batting_half=True))
                # Everything but the half is straight off the dataclass.
                self.assertEqual(
                    dataclasses.replace(config, auto_detect_batting_half=False),
                    DetectionConfig(),
                )

        for argv in run_argvs:
            with self.subTest(command=argv[0], batting_half="both"):
                config = _detection_config_from_args(
                    parser.parse_args([*argv, "--batting-half", "both"])
                )
                self.assertEqual(config, DetectionConfig())

        detect_events = _detection_config_from_args(parser.parse_args(["detect-events", "runs/g"]))
        self.assertEqual(detect_events, DetectionConfig())

    def test_detection_config_from_argv_carries_explicit_flags(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "run-game",
                "game.mp4",
                "--batting-half",
                "top",
                "--min-at-bat-spacing",
                "30",
                "--min-at-bat-spacing-roster-confirmed",
                "15",
                "--min-game-final-observations",
                "5",
                "--no-order-validation",
            ]
        )

        self.assertEqual(
            _detection_config_from_args(args),
            DetectionConfig(
                batting_half=HalfInning.TOP,
                min_at_bat_spacing_seconds=30.0,
                min_at_bat_spacing_roster_confirmed_seconds=15.0,
                min_game_final_observations=5,
                order_validation=False,
            ),
        )

    def test_negative_spacing_is_rejected_with_an_error_not_a_disabled_gate(self):
        # Before M4 this ran and silently disabled the spacing gate.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with _working_directory(root):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    with redirect_stdout(io.StringIO()):
                        exit_code = main(
                            ["detect-events", "states.jsonl", "--min-at-bat-spacing", "-5"]
                        )

        self.assertEqual(exit_code, 1)
        self.assertIn("min_at_bat_spacing_seconds must be >= 0", stderr.getvalue())

    def test_run_commands_accept_legacy_no_crops_flag(self):
        parser = build_parser()
        run_game = parser.parse_args(["run-game", "game.mp4", "--no-crops"])

        self.assertFalse(run_game.save_crops)

    def test_run_playlist_accepts_batch_controls(self):
        parser = build_parser()
        run_playlist = parser.parse_args(
            [
                "run-playlist",
                "https://youtube.com/playlist",
                "--force",
                "--limit",
                "3",
                "--start-index",
                "2",
                "--retries",
                "4",
            ]
        )

        self.assertTrue(run_playlist.force)
        self.assertEqual(run_playlist.limit, 3)
        self.assertEqual(run_playlist.start_index, 2)
        self.assertEqual(run_playlist.retries, 4)

    def test_detect_events_accepts_min_game_final_observations(self):
        parser = build_parser()
        detect_events = parser.parse_args(
            [
                "detect-events",
                "runs/game",
                "--min-game-final-observations",
                "2",
            ]
        )

        self.assertEqual(detect_events.min_game_final_observations, 2)

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
                "game_status",
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

    def test_feedback_command_accepts_note_and_output(self):
        parser = build_parser()
        feedback = parser.parse_args(
            ["feedback", "runs/game", "--note", "look here", "--output", "feedback.md"]
        )

        self.assertEqual(feedback.run_path, Path("runs/game"))
        self.assertEqual(feedback.note, "look here")
        self.assertEqual(feedback.output, Path("feedback.md"))

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
            input_values = ["#22 Maya R.", "", "#26 Amelia V.", "", "", "y", "n"]

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

    def test_offer_config_update_creates_config_with_roster_and_template(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            roster = root / "stars.csv"
            roster.write_text("number,full_name\n22,Maya R.\n", encoding="utf-8")
            template = root / "template.json"
            template.write_text('{"regions":{"inning":{"x":0,"y":0,"width":1,"height":1}}}', encoding="utf-8")
            stdout = io.StringIO()

            with (
                patch("builtins.input", side_effect=["y", "template.json"]),
                redirect_stdout(stdout),
            ):
                _offer_config_update(Path("stars.csv"), team_name="Stars", cwd=root)

            config = load_project_config(cwd=root)

        self.assertEqual(config.roster, Path("stars.csv"))
        self.assertEqual(config.template, Path("template.json"))
        self.assertEqual(config.team_name, "Stars")
        self.assertIn("Wrote", stdout.getvalue())

    def test_offer_config_update_preserves_missing_template_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sidelinehd.cfg").write_text(
                "[defaults]\n"
                "roster = old-roster.csv\n"
                "template = missing-template.json\n"
                "team_name = Stars\n",
                encoding="utf-8",
            )

            with patch("builtins.input", side_effect=["y"]):
                _offer_config_update(Path("new-roster.csv"), team_name="New Stars", cwd=root)

            text = (root / "sidelinehd.cfg").read_text(encoding="utf-8")

        self.assertIn("roster = new-roster.csv", text)
        self.assertIn("template = missing-template.json", text)
        self.assertIn("team_name = Stars", text)

    def test_offer_config_update_skips_prompt_when_raw_roster_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sidelinehd.cfg").write_text(
                "[defaults]\n"
                "roster = stars.csv\n"
                "template = missing-template.json\n",
                encoding="utf-8",
            )

            with patch("builtins.input") as input_mock:
                _offer_config_update(Path("stars.csv"), team_name="Stars", cwd=root)

        input_mock.assert_not_called()

    def test_apply_config_defaults_uses_config_without_overriding_cli_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_roster = root / "config-roster.csv"
            config_template = root / "config-template.json"
            config_roster.write_text("number,full_name\n22,Maya R.\n", encoding="utf-8")
            config_template.write_text(
                '{"regions":{"inning":{"x":0,"y":0,"width":1,"height":1}}}',
                encoding="utf-8",
            )
            (root / "sidelinehd.cfg").write_text(
                "[defaults]\n"
                "roster = config-roster.csv\n"
                "template = config-template.json\n"
                "team_name = Config Stars\n",
                encoding="utf-8",
            )
            args = build_parser().parse_args(
                ["run-youtube", "https://youtu.be/example", "--roster", "cli-roster.csv"]
            )

            with _working_directory(root):
                _apply_config_defaults(args, use_roster=True, use_template=True)

        self.assertEqual(args.roster, Path("cli-roster.csv"))
        self.assertEqual(args.template, Path("config-template.json"))
        self.assertEqual(args.team_name, "Config Stars")

    def test_apply_config_defaults_ignores_args_without_attribute(self):
        args = build_parser().parse_args(["export", "runs/game"])

        _apply_config_defaults(args, use_roster=True, use_template=True)

        self.assertFalse(hasattr(args, "roster"))
        self.assertFalse(hasattr(args, "template"))

    def test_run_youtube_uses_project_config_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            roster = root / "roster.csv"
            template = root / "template.json"
            roster.write_text("number,full_name\n22,Maya R.\n", encoding="utf-8")
            template.write_text(
                '{"regions":{"inning":{"x":0,"y":0,"width":1,"height":1}}}',
                encoding="utf-8",
            )
            (root / "sidelinehd.cfg").write_text(
                "[defaults]\n"
                "roster = roster.csv\n"
                "template = template.json\n"
                "team_name = Stars\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                _working_directory(root),
                patch("sidelinehd_extractor.cli.run_youtube_game") as run_youtube,
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                run_youtube.return_value.run.run_dir = Path("runs/game")
                run_youtube.return_value.run.manifest_path = Path("runs/game/manifest.json")
                run_youtube.return_value.run.samples_path = Path("runs/game/samples.jsonl")
                run_youtube.return_value.run.states_path = Path("runs/game/states.jsonl")
                run_youtube.return_value.run.events_path = Path("runs/game/events.jsonl")
                run_youtube.return_value.run.chapters_path = Path("runs/game/chapters.txt")
                run_youtube.return_value.run.at_bats_path = Path("runs/game/at_bats.txt")
                run_youtube.return_value.run.sample_count = 0
                run_youtube.return_value.run.state_count = 0
                run_youtube.return_value.run.event_count = 0
                run_youtube.return_value.run.batting_half_inference = None
                run_youtube.return_value.download = {}
                # --ocr none: the default tesseract backend probes PATH and
                # exits main() before run_youtube_game on hosts without
                # Tesseract (e.g. CI); this test is about config defaults.
                exit_code = main(
                    ["run-youtube", "https://youtu.be/example", "--quiet", "--ocr", "none"]
                )

            kwargs = run_youtube.call_args.kwargs

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(kwargs["roster"].name_for_number("22"), "Maya R.")
        self.assertIn("inning", kwargs["template"].regions)

    def test_format_roster_next_command_mentions_roster_and_template(self):
        # str(roster_path) keeps the platform's separators (backslashes on
        # Windows), so build the expectation the same way.
        roster_path = Path("rosters/stars.csv")
        command = _format_roster_next_command(roster_path)

        self.assertIn(f"--roster {roster_path}", command)
        self.assertIn("--template YOUR_TEMPLATE", command)

    def test_next_commands_use_installed_cli_and_double_quotes(self):
        # Item 19: follow-up commands must paste cleanly on Windows shells —
        # installed console script, no PYTHONPATH env-var syntax, double quotes
        # (single quotes are literal characters in cmd.exe).
        run_dir = Path("runs/game-20260706")
        commands = _next_commands(run_dir)

        # str(run_dir) keeps the platform's separators, so build expectations
        # the same way instead of hard-coding forward slashes.
        self.assertEqual(
            commands,
            [
                f'sidelinehd-extractor review-events "{run_dir}" --kind at-bats',
                f'sidelinehd-extractor review-events "{run_dir}" --kind chapters',
            ],
        )
        for command in commands:
            self.assertNotIn("PYTHONPATH", command)
            self.assertNotIn("'", command)

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
        # str(OSError) quotes the filename with repr(), which escapes the
        # backslashes in a Windows path, so build the expectation the same way.
        self.assertIn(repr(str(Path("runs/does-not-exist"))), stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_main_prints_clean_error_when_ytdlp_dependency_is_unavailable(self):
        stderr = io.StringIO()
        stdout = io.StringIO()

        with (
            # A None entry makes `import yt_dlp` raise ImportError, which
            # load_ytdlp_module converts to the actionable FileNotFoundError.
            patch.dict(sys.modules, {"yt_dlp": None}),
            redirect_stderr(stderr),
            redirect_stdout(stdout),
        ):
            exit_code = main(
                [
                    "download",
                    "https://youtu.be/example",
                    "--output-dir",
                    "videos",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Error: yt-dlp is required", stderr.getvalue())
        self.assertIn("pip install -e .", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
