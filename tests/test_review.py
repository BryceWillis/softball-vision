import unittest

from sidelinehd_extractor.models import Event, EventType, Roster, RosterPlayer
from sidelinehd_extractor.review import _lineup_has_rostered_candidate, render_event_review


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

    def test_render_event_review_flags_lineup_recovered_without_ocr_number_noise(self):
        events = [
            Event(
                event_type=EventType.AT_BAT_START,
                timestamp_seconds=600,
                label="Amelia V. (#26)",
                player_number="26",
                player_name="Amelia V.",
                metadata={
                    "ocr_player_number": "28",
                    "roster_match_source": "lineup_number",
                    "batter_number_source": "lineup_strip",
                    "lineup_strip_confidence": "lineup_highlight",
                },
            ),
        ]

        text = render_event_review(events, kind="at-bats")

        self.assertIn("lineup-recovered", text)
        self.assertNotIn("ocr-number=28", text)

    def test_render_event_review_flags_card_and_lineup_disagreement(self):
        events = [
            Event(
                event_type=EventType.AT_BAT_START,
                timestamp_seconds=600,
                label="Riley S. (#15)",
                player_number="15",
                player_name="Riley S.",
                metadata={"batter_number_disagreement": "batter_card=15 lineup=18"},
            ),
        ]

        text = render_event_review(events, kind="at-bats")

        self.assertIn("card-vs-lineup=batter_card=15 lineup=18", text)

    def test_render_event_review_flags_unrostered_card_number_and_lineup_candidate(self):
        roster = Roster(
            team_name="Stars",
            players=[
                RosterPlayer(number="26", full_name="Amelia V.", display_name="Amelia V."),
                RosterPlayer(number="5", full_name="Ava T.", display_name="Ava T."),
            ],
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
                    "batter_number_disagreement": "batter_card=7 lineup=265",
                },
            ),
        ]

        text = render_event_review(events, kind="at-bats", roster=roster)

        self.assertIn("unrostered-card-number=7", text)
        self.assertIn("lineup-had-rostered-candidate=265", text)

    def test_render_event_review_flags_garbled_card_name(self):
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
                    "batter_card_name": ">>",
                    "batter_number_source": "batter_card",
                    "roster_match_source": None,
                },
            ),
        ]

        text = render_event_review(events, kind="at-bats", roster=roster)

        self.assertIn("garbled-card-name", text)

    def test_render_event_review_passes_through_order_flags(self):
        events = [
            Event(
                event_type=EventType.AT_BAT_START,
                timestamp_seconds=600,
                label="Emma B. (#2)",
                player_number="2",
                player_name="Emma B.",
                metadata={"order_flags": ["inferred-missing"]},
            ),
        ]

        text = render_event_review(events, kind="at-bats")

        self.assertIn("inferred-missing", text)

    def test_lineup_has_rostered_candidate_matches_exact_and_substrings(self):
        roster = Roster(
            team_name="Stars",
            players=[
                RosterPlayer(number="26", full_name="Amelia V.", display_name="Amelia V."),
                RosterPlayer(number="5", full_name="Ava T.", display_name="Ava T."),
            ],
        )

        self.assertTrue(_lineup_has_rostered_candidate("26", roster))
        self.assertTrue(_lineup_has_rostered_candidate("265", roster))
        self.assertFalse(_lineup_has_rostered_candidate("78", roster))
        self.assertFalse(_lineup_has_rostered_candidate("265", None))

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
