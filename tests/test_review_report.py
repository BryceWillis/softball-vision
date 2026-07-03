import tempfile
import unittest
from pathlib import Path

from sidelinehd_extractor.processing import write_json
from sidelinehd_extractor.models import (
    Event,
    EventType,
    HalfInning,
    OCRSample,
    OverlayState,
    Roster,
    RosterPlayer,
)
from sidelinehd_extractor.processing import write_jsonl
from sidelinehd_extractor.review_report import render_review_report, write_review_report


class ReviewReportTests(unittest.TestCase):
    def test_render_review_report_includes_only_flagged_events_with_ocr_context(self):
        events = [
            Event(
                event_type=EventType.AT_BAT_START,
                timestamp_seconds=600,
                label="Amelia V. (#26)",
                inning=1,
                half=HalfInning.TOP,
                player_number="26",
                player_name="Amelia V.",
                metadata={"ocr_player_number": "28"},
            ),
            Event(
                event_type=EventType.AT_BAT_START,
                timestamp_seconds=720,
                label="Mia K. (#10)",
                inning=1,
                half=HalfInning.TOP,
                player_number="10",
                player_name="Mia K.",
            ),
        ]
        states = [
            OverlayState(
                timestamp_seconds=600,
                inning=1,
                half=HalfInning.TOP,
                balls=0,
                strikes=0,
                batter_number="28",
                metadata={
                    "batter_name": "Amelia V.",
                    "fields": {
                        "batter_card_name": "Amelia V.",
                        "batter_card_number": "28",
                    },
                },
            )
        ]
        samples = [
            OCRSample(
                timestamp_seconds=600,
                field_name="batter_card_number",
                raw_text="28\n",
                normalized_text="28",
                crop_path=Path("runs/game/crops/000600_batter_card_number.png"),
            )
        ]

        text = render_review_report(
            events=events, states=states, samples=samples, run_path=Path("runs/game")
        )

        self.assertIn("# Review Report", text)
        self.assertIn("Flagged events: 1", text)
        self.assertIn("## 10:00 Amelia V. (#26)", text)
        self.assertIn("ocr-number=28", text)
        self.assertIn("batter_card_number", text)
        self.assertIn("28", text)
        self.assertIn("event_type,timestamp,field,value,match_window_seconds,reason", text)
        self.assertIn("at_bat_start,10:00,delete,true,1,Remove false positive event", text)
        self.assertNotIn("Mia K. (#10)", text)

    def test_render_review_report_skips_roster_name_matched_number_noise(self):
        events = [
            Event(
                event_type=EventType.AT_BAT_START,
                timestamp_seconds=600,
                label="Amelia V. (#26)",
                inning=1,
                half=HalfInning.TOP,
                player_number="26",
                player_name="Amelia V.",
                metadata={"ocr_player_number": "28", "roster_match_source": "name"},
            ),
        ]

        text = render_review_report(
            events=events, states=[], samples=[], run_path=Path("runs/game")
        )

        self.assertIn("Flagged events: 0", text)
        self.assertNotIn("## 10:00 Amelia V. (#26)", text)

    def test_render_review_report_uses_roster_aware_flags(self):
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="26", full_name="Amelia V.", display_name="Amelia V.")],
        )
        events = [
            Event(
                event_type=EventType.AT_BAT_START,
                timestamp_seconds=600,
                label="#7",
                player_number="7",
                metadata={
                    "ocr_player_number": "7",
                    "batter_number_source": "batter_card",
                    "batter_number_disagreement": "batter_card=7 lineup=26",
                },
            ),
        ]

        text = render_review_report(
            events=events,
            states=[],
            samples=[],
            run_path=Path("runs/game"),
            roster=roster,
        )

        self.assertIn("unrostered-card-number=7", text)
        self.assertIn("lineup-had-rostered-candidate=26", text)

    def test_render_review_report_includes_run_warnings(self):
        text = render_review_report(
            events=[],
            states=[],
            samples=[],
            warnings=[
                {
                    "code": "field-never-read",
                    "field": "right_score",
                    "message": "Configured OCR field 'right_score' was empty for every sample.",
                }
            ],
            run_path=Path("runs/game"),
        )

        self.assertIn("## Run Warnings", text)
        self.assertIn("field-never-read", text)
        self.assertIn("right_score", text)
        self.assertIn("No questionable events found.", text)

    def test_write_review_report_uses_run_files(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            run_dir.mkdir()
            write_jsonl(
                run_dir / "events.jsonl",
                [
                    Event(
                        EventType.AT_BAT_START,
                        600,
                        "Amelia V. (#26)",
                        player_number="26",
                        player_name="Amelia V.",
                        metadata={"ocr_player_number": "28"},
                    )
                ],
            )
            write_jsonl(
                run_dir / "states.jsonl",
                [OverlayState(600, inning=1, half=HalfInning.TOP, batter_number="28")],
            )
            write_jsonl(
                run_dir / "samples.jsonl",
                [OCRSample(600, "batter_card_number", "28\n", normalized_text="28")],
            )

            result = write_review_report(run_dir)

            self.assertEqual(result.flagged_count, 1)
            self.assertEqual(result.output_path, run_dir / "review_report.md")
            self.assertTrue(result.output_path.exists())

    def test_write_review_report_reads_manifest_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            run_dir.mkdir()
            write_jsonl(run_dir / "events.jsonl", [])
            write_json(
                run_dir / "manifest.json",
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

            result = write_review_report(run_dir)

            text = result.output_path.read_text(encoding="utf-8")
            self.assertIn("field-never-read", text)
            self.assertIn("right_score", text)


if __name__ == "__main__":
    unittest.main()
