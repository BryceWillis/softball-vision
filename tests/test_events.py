import tempfile
import unittest
from pathlib import Path

from sidelinehd_extractor.events import detect_events, detect_events_file
from sidelinehd_extractor.exports import export_at_bat_comment, export_youtube_chapters
from sidelinehd_extractor.models import (
    EventType,
    HalfInning,
    OverlayState,
    Roster,
    RosterPlayer,
)
from sidelinehd_extractor.processing import write_jsonl


class EventDetectionTests(unittest.TestCase):
    def test_detect_events_emits_half_inning_and_first_at_bat(self):
        events = detect_events(
            [
                OverlayState(
                    timestamp_seconds=600,
                    inning=1,
                    half=HalfInning.TOP,
                    balls=0,
                    strikes=0,
                    batter_number="22",
                    metadata={"batter_name": "Maya R."},
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    balls=1,
                    strikes=0,
                    batter_number="22",
                    metadata={"batter_name": "Maya R."},
                ),
                OverlayState(
                    timestamp_seconds=610,
                    inning=1,
                    half=HalfInning.TOP,
                    balls=1,
                    strikes=0,
                    batter_number="22",
                    metadata={"batter_name": "Maya R."},
                ),
            ]
        )

        self.assertEqual([event.event_type for event in events], [
            EventType.HALF_INNING_START,
            EventType.AT_BAT_START,
        ])
        self.assertEqual(events[0].label, "Top 1")
        self.assertEqual(events[1].label, "Maya R. (#22)")

    def test_detect_events_uses_roster_name(self):
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="22", full_name="Maya R.", display_name="Maya R.")],
        )

        events = detect_events(
            [
                OverlayState(
                    timestamp_seconds=600,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="22",
                    metadata={"batter_name": "Maya R."},
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="22",
                    metadata={"batter_name": "Maya R."},
                ),
            ],
            roster=roster,
        )

        at_bat = [event for event in events if event.event_type == EventType.AT_BAT_START][0]
        self.assertEqual(at_bat.player_name, "Maya R.")
        self.assertEqual(at_bat.label, "Maya R. (#22)")

    def test_detect_events_uses_roster_number_from_ocr_name(self):
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="26", full_name="Amelia V.", display_name="Amelia V.")],
        )

        events = detect_events(
            [
                OverlayState(
                    timestamp_seconds=600,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="28",
                    metadata={"batter_name": "Amelia V."},
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="28",
                    metadata={"batter_name": "Amelia V."},
                ),
            ],
            roster=roster,
        )

        at_bat = [event for event in events if event.event_type == EventType.AT_BAT_START][0]
        self.assertEqual(at_bat.player_number, "26")
        self.assertEqual(at_bat.metadata["ocr_player_number"], "28")
        self.assertEqual(at_bat.label, "Amelia V. (#26)")

    def test_detect_events_uses_fuzzy_roster_name_from_ocr_name(self):
        # "Amelea V." is a deliberate OCR typo for "Amelia V." (i→e substitution).
        # SequenceMatcher ratio("ameleav", "ameliav") ≈ 0.857, above the 0.84 threshold.
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="26", full_name="Amelia V.", display_name="Amelia V.")],
        )

        events = detect_events(
            [
                OverlayState(
                    timestamp_seconds=600,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="28",
                    metadata={"batter_name": "Amelea V."},
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="28",
                    metadata={"batter_name": "Amelea V."},
                ),
            ],
            roster=roster,
        )

        at_bat = [event for event in events if event.event_type == EventType.AT_BAT_START][0]
        self.assertEqual(at_bat.player_name, "Amelia V.")
        self.assertEqual(at_bat.player_number, "26")
        self.assertEqual(at_bat.label, "Amelia V. (#26)")

    def test_detect_events_prefers_roster_name_match_over_noisy_number(self):
        roster = Roster(
            team_name="Stars",
            players=[
                RosterPlayer(number="2", full_name="Emma B.", display_name="Emma B."),
                RosterPlayer(number="12", full_name="Chloe W.", display_name="Chloe W."),
            ],
        )

        events = detect_events(
            [
                OverlayState(
                    timestamp_seconds=600,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="12",
                    metadata={"batter_name": "Chloe W."},
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="2",
                    metadata={"batter_name": "Chloe W."},
                ),
                OverlayState(
                    timestamp_seconds=610,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="12",
                    metadata={"batter_name": "Chloe W."},
                ),
            ],
            roster=roster,
        )

        self.assertEqual(
            [
                event.label
                for event in events
                if event.event_type == EventType.AT_BAT_START
            ],
            ["Chloe W. (#12)"],
        )

    def test_detect_events_uses_roster_name_when_number_crop_is_blank_or_noisy(self):
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="5", full_name="Ava T.", display_name="Ava T.")],
        )

        events = detect_events(
            [
                OverlayState(
                    timestamp_seconds=600,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number=None,
                    metadata={"batter_name": "Ava T."},
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number=None,
                    metadata={"batter_name": "Ava T."},
                ),
                OverlayState(
                    timestamp_seconds=610,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="8",
                    metadata={"batter_name": "Ava T."},
                ),
                OverlayState(
                    timestamp_seconds=615,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number=None,
                    metadata={"batter_name": "Ava T."},
                ),
            ],
            roster=roster,
        )

        at_bat = [event for event in events if event.event_type == EventType.AT_BAT_START][0]
        self.assertEqual(at_bat.player_name, "Ava T.")
        self.assertEqual(at_bat.player_number, "5")
        self.assertEqual(at_bat.label, "Ava T. (#5)")

    def test_detect_events_emits_batter_changes(self):
        events = detect_events(
            [
                OverlayState(600, inning=1, half=HalfInning.TOP, batter_number="22"),
                OverlayState(605, inning=1, half=HalfInning.TOP, batter_number="22"),
                OverlayState(650, inning=1, half=HalfInning.TOP, batter_number="7"),
                OverlayState(655, inning=1, half=HalfInning.TOP, batter_number="7"),
            ]
        )

        self.assertEqual(
            [event.player_number for event in events if event.event_type == EventType.AT_BAT_START],
            ["22", "7"],
        )

    def test_detect_events_file_writes_events_jsonl(self):
        with tempfile.TemporaryDirectory() as directory:
            states_path = Path(directory) / "states.jsonl"
            write_jsonl(
                states_path,
                [
                    OverlayState(600, inning=1, half=HalfInning.TOP, batter_number="22"),
                    OverlayState(605, inning=1, half=HalfInning.TOP, batter_number="22"),
                ],
            )

            result = detect_events_file(states_path)

            self.assertEqual(result.event_count, 2)
            self.assertTrue(result.output_path.exists())

    def test_export_text_from_detected_events(self):
        events = detect_events(
            [
                OverlayState(600, inning=1, half=HalfInning.TOP, batter_number="22"),
                OverlayState(605, inning=1, half=HalfInning.TOP, batter_number="22"),
            ]
        )

        self.assertEqual(export_youtube_chapters(events), "0:00 Pregame\n10:00 Top 1")
        self.assertEqual(export_at_bat_comment(events), "1st Inning\n10:00 #22")

    def test_export_at_bat_comment_preserves_event_label(self):
        events = detect_events(
            [
                OverlayState(
                    600,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="22",
                    metadata={"batter_name": "Maya R."},
                ),
                OverlayState(
                    605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="22",
                    metadata={"batter_name": "Maya R."},
                ),
            ]
        )

        self.assertEqual(export_at_bat_comment(events), "1st Inning\n10:00 Maya R. (#22)")

    def test_detect_events_ignores_single_noisy_batter_read(self):
        events = detect_events(
            [
                OverlayState(600, inning=1, half=HalfInning.TOP, batter_number="22"),
                OverlayState(605, inning=1, half=HalfInning.TOP, batter_number=None),
            ]
        )

        self.assertEqual(
            [event.event_type for event in events],
            [EventType.HALF_INNING_START],
        )

    def test_detect_events_debounces_noisy_half_inning_reads(self):
        states = [
            OverlayState(600, inning=1, half=HalfInning.TOP),
            OverlayState(605, inning=1, half=HalfInning.TOP),
            OverlayState(610, inning=1, half=HalfInning.TOP),
            OverlayState(615, inning=1, half=HalfInning.TOP),
            OverlayState(620, inning=2, half=HalfInning.TOP),
            OverlayState(625, inning=1, half=HalfInning.TOP),
            OverlayState(630, inning=2, half=HalfInning.TOP),
            OverlayState(635, inning=2, half=HalfInning.TOP),
            OverlayState(640, inning=2, half=HalfInning.TOP),
            OverlayState(645, inning=1, half=HalfInning.TOP),
            OverlayState(650, inning=2, half=HalfInning.TOP),
            OverlayState(655, inning=3, half=HalfInning.TOP),
            OverlayState(660, inning=2, half=HalfInning.TOP),
            OverlayState(665, inning=3, half=HalfInning.TOP),
        ]

        events = detect_events(states)

        self.assertEqual(
            [
                event.label
                for event in events
                if event.event_type == EventType.HALF_INNING_START
            ],
            ["Top 1", "Top 2"],
        )

    def test_detect_events_allows_short_confirmed_half_inning_inputs(self):
        events = detect_events(
            [
                OverlayState(600, inning=1, half=HalfInning.TOP),
                OverlayState(605, inning=1, half=HalfInning.TOP),
            ]
        )

        self.assertEqual(
            [event.label for event in events if event.event_type == EventType.HALF_INNING_START],
            ["Top 1"],
        )

    def test_detect_events_ignores_number_flicker_when_name_is_same(self):
        # "Amelea V." is a deliberate OCR typo for "Amelia V." — fuzzy name match
        # treats these as the same batter, so only one at-bat is emitted.
        events = detect_events(
            [
                OverlayState(
                    600,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="28",
                    metadata={"batter_name": "Amelia V."},
                ),
                OverlayState(
                    605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="28",
                    metadata={"batter_name": "Amelia V."},
                ),
                OverlayState(
                    610,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="26",
                    metadata={"batter_name": "Amelia V."},
                ),
                OverlayState(
                    615,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="26",
                    metadata={"batter_name": "Amelea V."},
                ),
            ]
        )

        self.assertEqual(
            [event.player_number for event in events if event.event_type == EventType.AT_BAT_START],
            ["28"],
        )

    def test_detect_events_reuses_known_number_for_same_name_after_other_batter(self):
        events = detect_events(
            [
                OverlayState(
                    600,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="28",
                    metadata={"batter_name": "Amelia V."},
                ),
                OverlayState(
                    605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="28",
                    metadata={"batter_name": "Amelia V."},
                ),
                OverlayState(
                    700,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="22",
                    metadata={"batter_name": "Maya R."},
                ),
                OverlayState(
                    705,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="22",
                    metadata={"batter_name": "Maya R."},
                ),
                OverlayState(
                    800,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="26",
                    metadata={"batter_name": "Amelia V."},
                ),
                OverlayState(
                    805,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="26",
                    metadata={"batter_name": "Amelia V."},
                ),
            ]
        )

        self.assertEqual(
            [
                (event.player_name, event.player_number)
                for event in events
                if event.event_type == EventType.AT_BAT_START
            ],
            [("Amelia V.", "28"), ("Maya R.", "22"), ("Amelia V.", "28")],
        )

    def test_detect_events_can_filter_at_bats_to_one_half(self):
        events = detect_events(
            [
                OverlayState(0, inning=1, half=HalfInning.TOP, batter_number="22"),
                OverlayState(5, inning=1, half=HalfInning.TOP, batter_number="22"),
                OverlayState(10, inning=1, half=HalfInning.TOP, batter_number="22"),
                OverlayState(15, inning=1, half=HalfInning.TOP, batter_number="22"),
                OverlayState(900, inning=1, half=HalfInning.BOTTOM, batter_number="10"),
                OverlayState(905, inning=1, half=HalfInning.BOTTOM, batter_number="10"),
                OverlayState(910, inning=1, half=HalfInning.BOTTOM, batter_number="10"),
                OverlayState(915, inning=1, half=HalfInning.BOTTOM, batter_number="10"),
                OverlayState(1320, inning=2, half=HalfInning.TOP, batter_number="24"),
                OverlayState(1325, inning=2, half=HalfInning.TOP, batter_number="24"),
                OverlayState(1330, inning=2, half=HalfInning.TOP, batter_number="24"),
                OverlayState(1335, inning=2, half=HalfInning.TOP, batter_number="24"),
            ],
            batting_half=HalfInning.TOP,
        )

        self.assertEqual(
            [
                event.label
                for event in events
                if event.event_type == EventType.HALF_INNING_START
            ],
            ["Top 1", "Bottom 1", "Top 2"],
        )
        self.assertEqual(
            [
                event.player_number
                for event in events
                if event.event_type == EventType.AT_BAT_START
            ],
            ["22", "24"],
        )

    def test_detect_events_ignores_too_close_batter_flip_without_swallowing_later_batter(self):
        events = detect_events(
            [
                OverlayState(0, inning=1, half=HalfInning.TOP, batter_number="5"),
                OverlayState(5, inning=1, half=HalfInning.TOP, batter_number="5"),
                OverlayState(10, inning=1, half=HalfInning.TOP, batter_number="3"),
                OverlayState(15, inning=1, half=HalfInning.TOP, batter_number="3"),
                OverlayState(530, inning=2, half=HalfInning.TOP, batter_number="3"),
                OverlayState(535, inning=2, half=HalfInning.TOP, batter_number="3"),
            ]
        )

        self.assertEqual(
            [
                event.player_number
                for event in events
                if event.event_type == EventType.AT_BAT_START
            ],
            ["5", "3"],
        )
        self.assertEqual(
            [
                event.timestamp_seconds
                for event in events
                if event.event_type == EventType.AT_BAT_START
            ],
            [0, 530],
        )


if __name__ == "__main__":
    unittest.main()
