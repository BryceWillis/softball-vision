import unittest

from sidelinehd_extractor.models import Event, EventType
from sidelinehd_extractor.review import render_event_review


class ReviewTests(unittest.TestCase):
    def test_render_event_review_flags_close_at_bats_and_ocr_mismatch(self):
        events = [
            Event(
                event_type=EventType.AT_BAT_START,
                timestamp_seconds=600,
                label="Amelia V. (#26)",
                player_number="26",
                player_name="Amelia V.",
                metadata={"ocr_player_number": "28"},
            ),
            Event(
                event_type=EventType.AT_BAT_START,
                timestamp_seconds=630,
                label="Maya R. (#22)",
                player_number="22",
                player_name="Maya R.",
            ),
        ]

        text = render_event_review(events, kind="at-bats")

        self.assertIn("ocr-number=28", text)
        self.assertIn("close-at-bat=30s", text)

    def test_render_event_review_does_not_flag_name_matched_roster_number_correction(self):
        events = [
            Event(
                event_type=EventType.AT_BAT_START,
                timestamp_seconds=600,
                label="Amelia V. (#26)",
                player_number="26",
                player_name="Amelia V.",
                metadata={"ocr_player_number": "28", "roster_match_source": "name"},
            ),
        ]

        text = render_event_review(events, kind="at-bats")

        self.assertNotIn("ocr-number=28", text)

    def test_render_event_review_filters_chapters(self):
        events = [
            Event(EventType.HALF_INNING_START, 600, "Top 1"),
            Event(EventType.AT_BAT_START, 605, "#22", player_number="22"),
        ]

        text = render_event_review(events, kind="chapters")

        self.assertIn("Top 1", text)
        self.assertNotIn("#22", text)


if __name__ == "__main__":
    unittest.main()
