import tempfile
import unittest
from pathlib import Path

from sidelinehd_extractor.feedback import write_feedback_log
from sidelinehd_extractor.models import Event, EventType, OCRSample
from sidelinehd_extractor.processing import write_json, write_jsonl


class FeedbackLogTests(unittest.TestCase):
    def test_write_feedback_log_redacts_names_and_keeps_diagnostic_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            _write_feedback_fixture(run_dir)

            result = write_feedback_log(run_dir, note="Count looked wrong in the third inning.")

            text = result.output_path.read_text(encoding="utf-8")

        self.assertIn("# SidelineHD Extractor Feedback", text)
        self.assertIn("Count looked wrong", text)
        self.assertIn("Player A (#22)", text)
        self.assertIn('"player_number": "22"', text)
        self.assertIn("ocr-number=72", text)
        self.assertIn('"confidence": 0.42', text)
        self.assertIn('"tesseract_version": "5.3.0"', text)
        self.assertNotIn("Emma", text)
        self.assertNotIn("Local Stars", text)
        self.assertNotIn("https://youtu.be", text)
        self.assertNotIn("crops/", text)

    def test_feedback_log_guard_removes_roster_and_observed_name_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            _write_feedback_fixture(run_dir)

            result = write_feedback_log(run_dir)

            text = result.output_path.read_text(encoding="utf-8")

        leaked_tokens = ["Emma", "Olivia", "Maya", "Local Stars"]
        for token in leaked_tokens:
            with self.subTest(token=token):
                self.assertNotIn(token, text)
        self.assertIn("Player A", text)
        self.assertIn("Player B", text)
        self.assertIn("Player C", text)


def _write_feedback_fixture(run_dir: Path) -> None:
    run_dir.mkdir(parents=True)
    write_json(
        run_dir / "manifest.json",
        {
            "template": {"name": "sidelinehd active"},
            "roster": {
                "team_name": "Local Stars",
                "players": [
                    {
                        "number": "22",
                        "full_name": "Emma B.",
                        "display_name": "Emma B.",
                        "aliases": ["Emma"],
                    },
                    {
                        "number": "26",
                        "full_name": "Olivia M.",
                        "display_name": "Olivia M.",
                        "aliases": ["Olivia"],
                    },
                ],
            },
            "tesseract_version": "5.3.0",
            "ocr_backend": "tesseract",
            "ocr_workers": 4,
            "sample_every_seconds": 5.0,
            "fields": ["inning", "batter_card_name", "batter_card_number"],
            "detection": {"batting_half": "auto"},
            "youtube": {"url": "https://youtu.be/private", "video_id": "private"},
            "warnings": [
                {
                    "code": "field-never-read",
                    "field": "right_team",
                    "message": "Local Stars never read.",
                }
            ],
        },
    )
    write_jsonl(
        run_dir / "events.jsonl",
        [
            Event(EventType.HALF_INNING_START, 590, "Top 1"),
            Event(
                EventType.AT_BAT_START,
                600,
                "Emma B. (#22)",
                player_number="22",
                player_name="Emma B.",
                metadata={
                    "ocr_player_number": "72",
                    "batter_card_name": "Emma B.",
                    "left_team": "Local Stars",
                },
            ),
            Event(
                EventType.AT_BAT_START,
                720,
                "Olivia M. (#26)",
                player_number="26",
                player_name="Olivia M.",
                metadata={"batter_card_name": "Olivia M."},
            ),
            Event(
                EventType.AT_BAT_START,
                840,
                "Maya R. (#9)",
                player_number="9",
                player_name="Maya R.",
                metadata={"batter_card_name": "Maya R."},
            ),
        ],
    )
    write_jsonl(
        run_dir / "samples.jsonl",
        [
            OCRSample(
                600,
                "batter_card_name",
                "Emma B.\n",
                normalized_text="Emma B.",
                confidence=0.91,
                crop_path=Path("crops/000600p000_batter_card_name.png"),
            ),
            OCRSample(
                600,
                "batter_card_number",
                "72\n",
                normalized_text="72",
                confidence=0.42,
            ),
            OCRSample(
                720,
                "batter_card_name",
                "Maya R.\n",
                normalized_text="Maya R.",
                confidence=0.5,
            ),
        ],
    )


if __name__ == "__main__":
    unittest.main()
