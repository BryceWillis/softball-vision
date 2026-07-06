import tempfile
import unittest
from pathlib import Path

from sidelinehd_extractor.events import (
    _at_bat_spacing_for_roster_match,
    _detect_game_final,
    _enrich_states_digit_runs,
    _game_active_timestamp,
    _lineup_is_highlight_confirmed,
    _resolve_lineup_digit_run,
    _score_snapshot,
    _window_has_game_active_signal,
    detect_events,
    detect_events_file,
    filter_at_bats_to_half,
    infer_batting_cycle,
    infer_batting_half,
    validate_batting_order,
)
from sidelinehd_extractor.exports import export_at_bat_comment, export_youtube_chapters
from sidelinehd_extractor.models import (
    Event,
    EventType,
    HalfInning,
    OverlayState,
    Roster,
    RosterPlayer,
)
from sidelinehd_extractor.processing import write_jsonl


class EventDetectionTests(unittest.TestCase):
    def _chapter(
        self,
        timestamp: float,
        inning: int = 1,
        half: HalfInning = HalfInning.BOTTOM,
    ) -> Event:
        return Event(
            EventType.HALF_INNING_START,
            timestamp,
            f"{'Bottom' if half == HalfInning.BOTTOM else 'Top'} {inning}",
            inning=inning,
            half=half,
        )

    def _at_bat(
        self,
        number: str,
        timestamp: float,
        inning: int = 1,
        half: HalfInning = HalfInning.BOTTOM,
        source: str = "name",
        name=None,
    ) -> Event:
        player_name = name or f"Player {number}"
        return Event(
            EventType.AT_BAT_START,
            timestamp,
            f"{player_name} (#{number})",
            inning=inning,
            half=half,
            player_number=number,
            player_name=player_name,
            metadata={"roster_match_source": source},
        )

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

        self.assertEqual(
            [event.event_type for event in events],
            [
                EventType.HALF_INNING_START,
                EventType.AT_BAT_START,
            ],
        )
        self.assertEqual(events[0].label, "Top 1")
        self.assertEqual(events[1].label, "Maya R. (#22)")

    def test_detect_events_refires_same_batter_after_half_change(self):
        # Item 61: the lineup highlight points at the upcoming leadoff batter
        # during the opposing half, firing a phantom at-bat there. The real
        # leadoff at-bat in the next half must still fire even though the
        # batter identity matches the phantom.
        def state(ts, half):
            return OverlayState(
                timestamp_seconds=ts,
                inning=1,
                half=half,
                balls=0,
                strikes=0,
                batter_number="22",
                metadata={"batter_name": "Maya R."},
            )

        states = [state(600 + offset, HalfInning.TOP) for offset in (0, 5, 10)]
        states += [state(700 + offset, HalfInning.BOTTOM) for offset in (0, 5, 10)]

        events = detect_events(states)

        at_bats = [event for event in events if event.event_type == EventType.AT_BAT_START]
        self.assertEqual(len(at_bats), 2)
        self.assertEqual(at_bats[0].half, HalfInning.TOP)
        self.assertEqual(at_bats[1].half, HalfInning.BOTTOM)
        self.assertEqual(at_bats[1].timestamp_seconds, 700)
        self.assertEqual(at_bats[1].player_number, "22")

    def test_detect_events_includes_stable_final_marker(self):
        events = detect_events(
            [
                OverlayState(600, inning=1, half=HalfInning.TOP),
                OverlayState(605, inning=1, half=HalfInning.TOP),
                OverlayState(900, metadata={"game_status": "final"}),
                OverlayState(905, metadata={"game_status": "final"}),
                OverlayState(910, metadata={"game_status": "final"}),
            ],
            min_game_final_observations=3,
        )

        self.assertEqual(events[-1].event_type, EventType.GAME_FINAL)
        self.assertEqual(events[-1].timestamp_seconds, 900)
        self.assertEqual(events[-1].label, "Final")

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

    def test_detect_events_recovers_missing_batter_card_from_lineup_number(self):
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
                    batter_number="26",
                    metadata={
                        "batter_number_source": "lineup_strip",
                        "lineup_strip_confidence": "lineup_highlight",
                    },
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="26",
                    metadata={
                        "batter_number_source": "lineup_strip",
                        "lineup_strip_confidence": "lineup_highlight",
                    },
                ),
            ],
            roster=roster,
        )

        at_bat = [event for event in events if event.event_type == EventType.AT_BAT_START][0]
        self.assertEqual(at_bat.player_name, "Amelia V.")
        self.assertEqual(at_bat.player_number, "26")
        self.assertEqual(at_bat.metadata["roster_match_source"], "lineup_number")
        self.assertEqual(at_bat.metadata["batter_number_source"], "lineup_strip")
        self.assertEqual(at_bat.metadata["lineup_strip_confidence"], "lineup_highlight")

    def test_detect_events_keeps_old_lineup_number_source_usable(self):
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
                    batter_number="26",
                    metadata={"batter_number_source": "lineup_number"},
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="26",
                    metadata={"batter_number_source": "lineup_number"},
                ),
            ],
            roster=roster,
        )

        at_bat = [event for event in events if event.event_type == EventType.AT_BAT_START][0]
        self.assertEqual(at_bat.player_name, "Amelia V.")
        self.assertEqual(at_bat.player_number, "26")
        self.assertEqual(at_bat.metadata["roster_match_source"], "lineup_number")
        self.assertEqual(at_bat.metadata["batter_number_source"], "lineup_number")

    def test_lineup_is_highlight_confirmed_returns_true_for_lineup_highlight(self):
        state = OverlayState(
            600,
            metadata={"lineup_strip_confidence": "lineup_highlight"},
        )

        self.assertTrue(_lineup_is_highlight_confirmed(state))

    def test_lineup_is_highlight_confirmed_returns_false_for_full_strip(self):
        state = OverlayState(
            600,
            metadata={"lineup_strip_confidence": "lineup_full_strip"},
        )

        self.assertFalse(_lineup_is_highlight_confirmed(state))

    def test_lineup_is_highlight_confirmed_returns_false_for_none(self):
        self.assertFalse(_lineup_is_highlight_confirmed(OverlayState(600)))

    def test_detect_game_final_uses_first_timestamp_of_stable_run(self):
        event = _detect_game_final(
            [
                OverlayState(900, away_score=4, home_score=3, metadata={"game_status": "final"}),
                OverlayState(905, away_score=4, home_score=3, metadata={"game_status": "final"}),
                OverlayState(910, away_score=4, home_score=3, metadata={"game_status": "final"}),
            ],
            min_observations=3,
        )

        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, EventType.GAME_FINAL)
        self.assertEqual(event.timestamp_seconds, 900)
        self.assertEqual(event.metadata["away_score"], 4)
        self.assertEqual(event.metadata["home_score"], 3)

    def test_detect_game_final_requires_stable_run(self):
        event = _detect_game_final(
            [
                OverlayState(900, metadata={"game_status": "final"}),
                OverlayState(905, metadata={"game_status": "final"}),
            ],
            min_observations=3,
        )

        self.assertIsNone(event)

    def test_detect_game_final_returns_none_without_final_states(self):
        self.assertIsNone(_detect_game_final([OverlayState(900), OverlayState(905)]))

    def test_detect_game_final_resets_after_gap(self):
        event = _detect_game_final(
            [
                OverlayState(900, metadata={"game_status": "final"}),
                OverlayState(905),
                OverlayState(910, metadata={"game_status": "final"}),
                OverlayState(915, metadata={"game_status": "final"}),
                OverlayState(920, metadata={"game_status": "final"}),
            ],
            min_observations=3,
        )

        self.assertIsNotNone(event)
        self.assertEqual(event.timestamp_seconds, 910)

    def test_window_has_game_active_signal_returns_false_for_pregame_zero_count_stable_batter(
        self,
    ):
        states = [
            OverlayState(
                timestamp_seconds=0,
                inning=1,
                half=HalfInning.TOP,
                balls=0,
                strikes=0,
                batter_number="26",
                metadata={
                    "batter_number_source": "lineup_strip",
                    "lineup_strip_confidence": "lineup_highlight",
                },
            ),
            OverlayState(
                timestamp_seconds=5,
                inning=1,
                half=HalfInning.TOP,
                balls=0,
                strikes=0,
                batter_number="26",
            ),
        ]

        self.assertFalse(_window_has_game_active_signal(states, (1, HalfInning.TOP)))

    def test_window_has_game_active_signal_ignores_untrusted_full_strip_pregame_noise(
        self,
    ):
        states = [
            OverlayState(
                timestamp_seconds=0,
                inning=1,
                half=HalfInning.TOP,
                batter_number="1",
                metadata={
                    "batter_number_source": "lineup_strip",
                    "lineup_strip_confidence": "lineup_full_strip",
                },
            ),
            OverlayState(
                timestamp_seconds=55,
                inning=1,
                half=HalfInning.TOP,
                batter_number="7",
                metadata={
                    "batter_number_source": "lineup_strip",
                    "lineup_strip_confidence": "lineup_full_strip",
                },
            ),
        ]

        self.assertFalse(_window_has_game_active_signal(states, (1, HalfInning.TOP)))

    def test_window_has_game_active_signal_returns_true_on_nonzero_balls(self):
        states = [
            OverlayState(
                timestamp_seconds=0,
                inning=1,
                half=HalfInning.TOP,
                balls=1,
                strikes=0,
                batter_number="26",
            )
        ]

        self.assertTrue(_window_has_game_active_signal(states, (1, HalfInning.TOP)))

    def test_window_has_game_active_signal_returns_true_on_nonzero_strikes(self):
        states = [
            OverlayState(
                timestamp_seconds=0,
                inning=1,
                half=HalfInning.TOP,
                balls=0,
                strikes=1,
                batter_number="26",
            )
        ]

        self.assertTrue(_window_has_game_active_signal(states, (1, HalfInning.TOP)))

    def test_window_has_game_active_signal_returns_true_on_batter_change(self):
        states = [
            OverlayState(
                timestamp_seconds=0,
                inning=1,
                half=HalfInning.TOP,
                balls=0,
                strikes=0,
                batter_number="26",
                metadata={
                    "batter_number_source": "lineup_strip",
                    "lineup_strip_confidence": "lineup_highlight",
                },
            ),
            OverlayState(
                timestamp_seconds=5,
                inning=1,
                half=HalfInning.TOP,
                balls=0,
                strikes=0,
                batter_number="2",
                metadata={
                    "batter_number_source": "lineup_strip",
                    "lineup_strip_confidence": "lineup_highlight",
                },
            ),
        ]

        self.assertTrue(_window_has_game_active_signal(states, (1, HalfInning.TOP)))

    def test_window_has_game_active_signal_suppresses_pregame_zero_count(self):
        states = [
            OverlayState(
                timestamp_seconds=390,
                inning=1,
                half=HalfInning.TOP,
                metadata={"game_status": "pregame"},
            ),
            OverlayState(
                timestamp_seconds=395,
                inning=1,
                half=HalfInning.TOP,
                balls=0,
                strikes=0,
                batter_number="10",
            ),
        ]

        self.assertFalse(_window_has_game_active_signal(states, (1, HalfInning.TOP)))

    def test_window_has_game_active_signal_ignores_states_with_wrong_half_key(self):
        states = [
            OverlayState(
                timestamp_seconds=0,
                inning=1,
                half=HalfInning.BOTTOM,
                balls=1,
                strikes=0,
                batter_number="26",
            )
        ]

        self.assertFalse(_window_has_game_active_signal(states, (1, HalfInning.TOP)))

    def test_window_has_game_active_signal_ignores_implausible_batter_states(self):
        states = [
            OverlayState(
                timestamp_seconds=0,
                inning=1,
                half=HalfInning.TOP,
                balls=1,
                strikes=0,
                batter_number="265",
            )
        ]

        self.assertFalse(_window_has_game_active_signal(states, (1, HalfInning.TOP)))

    def test_window_has_game_active_signal_ignores_noisy_batter_card_number_changes(self):
        states = [
            OverlayState(
                timestamp_seconds=0,
                inning=1,
                half=HalfInning.TOP,
                balls=None,
                strikes=None,
                batter_number="3",
                metadata={"batter_number_source": "batter_card", "batter_name": "non"},
            ),
            OverlayState(
                timestamp_seconds=5,
                inning=1,
                half=HalfInning.TOP,
                balls=None,
                strikes=None,
                batter_number="1",
                metadata={"batter_number_source": "batter_card", "batter_name": "TT |"},
            ),
        ]

        self.assertFalse(_window_has_game_active_signal(states, (1, HalfInning.TOP)))

    def test_game_active_timestamp_returns_first_nonzero_count_state(self):
        states = [
            OverlayState(0, inning=1, half=HalfInning.TOP, balls=0, strikes=0, batter_number="26"),
            OverlayState(5, inning=1, half=HalfInning.TOP, balls=0, strikes=0, batter_number="26"),
            OverlayState(10, inning=1, half=HalfInning.TOP, balls=0, strikes=1, batter_number="26"),
        ]

        self.assertEqual(_game_active_timestamp(states, 0, (1, HalfInning.TOP), 3), 10)

    def test_game_active_timestamp_ignores_named_card_with_zero_count_state(self):
        states = [
            OverlayState(
                0,
                inning=1,
                half=HalfInning.TOP,
                balls=0,
                strikes=0,
                batter_number="10",
                metadata={
                    "batter_name": "Teagan L.",
                    "batter_number_source": "batter_card",
                },
            )
        ]

        self.assertIsNone(_game_active_timestamp(states, 0, (1, HalfInning.TOP), 1))

    def test_game_active_timestamp_returns_batter_card_change_without_count(self):
        states = [
            OverlayState(
                0,
                inning=1,
                half=HalfInning.TOP,
                batter_number="10",
                metadata={
                    "batter_name": "Teagan L.",
                    "batter_number_source": "batter_card",
                },
            ),
            OverlayState(
                5,
                inning=1,
                half=HalfInning.TOP,
                batter_number="12",
                metadata={
                    "batter_name": "Eliana D.",
                    "batter_number_source": "batter_card",
                },
            ),
        ]

        self.assertEqual(_game_active_timestamp(states, 0, (1, HalfInning.TOP), 2), 5)

    def test_game_active_timestamp_returns_old_lineup_number_change_without_count(self):
        states = [
            OverlayState(
                0,
                inning=1,
                half=HalfInning.TOP,
                batter_number="26",
                metadata={"batter_number_source": "lineup_number"},
            ),
            OverlayState(
                5,
                inning=1,
                half=HalfInning.TOP,
                batter_number="2",
                metadata={"batter_number_source": "lineup_number"},
            ),
        ]

        self.assertEqual(_game_active_timestamp(states, 0, (1, HalfInning.TOP), 2), 5)

    def test_game_active_timestamp_returns_batter_change_timestamp_when_no_count(self):
        states = [
            OverlayState(
                0,
                inning=1,
                half=HalfInning.TOP,
                balls=0,
                strikes=0,
                batter_number="26",
                metadata={
                    "batter_number_source": "lineup_strip",
                    "lineup_strip_confidence": "lineup_highlight",
                },
            ),
            OverlayState(
                5,
                inning=1,
                half=HalfInning.TOP,
                balls=0,
                strikes=0,
                batter_number="2",
                metadata={
                    "batter_number_source": "lineup_strip",
                    "lineup_strip_confidence": "lineup_highlight",
                },
            ),
        ]

        self.assertEqual(_game_active_timestamp(states, 0, (1, HalfInning.TOP), 2), 5)

    def test_game_active_timestamp_ignores_first_non_pregame_zero_count_state(self):
        states = [
            OverlayState(
                390,
                inning=1,
                half=HalfInning.TOP,
                metadata={"game_status": "pregame"},
            ),
            OverlayState(395, inning=1, half=HalfInning.TOP, balls=0, strikes=0, batter_number="10"),
            OverlayState(400, inning=1, half=HalfInning.TOP, balls=0, strikes=0, batter_number="10"),
        ]

        self.assertIsNone(_game_active_timestamp(states, 0, (1, HalfInning.TOP), 3))

    def test_game_active_timestamp_waits_for_positive_activity_after_intermittent_pregame_reads(
        self,
    ):
        states = [
            OverlayState(340, inning=1, half=HalfInning.TOP),
            OverlayState(
                345,
                inning=1,
                half=HalfInning.TOP,
                metadata={"game_status": "pregame"},
            ),
            OverlayState(350, inning=1, half=HalfInning.TOP),
            OverlayState(
                370,
                inning=1,
                half=HalfInning.TOP,
                metadata={"game_status": "pregame"},
            ),
            OverlayState(385, inning=1, half=HalfInning.TOP),
            OverlayState(390, inning=1, half=HalfInning.TOP),
            OverlayState(395, inning=1, half=HalfInning.TOP, balls=0, strikes=0, batter_number="10"),
            OverlayState(400, inning=1, half=HalfInning.TOP, balls=0, strikes=0, batter_number="10"),
            OverlayState(405, inning=1, half=HalfInning.TOP, balls=0, strikes=1, batter_number="10"),
        ]

        self.assertEqual(_game_active_timestamp(states, 0, (1, HalfInning.TOP), 9), 405)

    def test_game_active_timestamp_returns_none_when_no_signal_in_window(self):
        states = [
            OverlayState(0, inning=1, half=HalfInning.TOP, balls=0, strikes=0, batter_number="26"),
            OverlayState(5, inning=1, half=HalfInning.TOP, balls=0, strikes=0, batter_number="26"),
        ]

        self.assertIsNone(_game_active_timestamp(states, 0, (1, HalfInning.TOP), 2))

    def test_detect_events_suppresses_full_strip_lineup_event_even_when_rostered(self):
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="15", full_name="Riley S.", display_name="Riley S.")],
        )

        events = detect_events(
            [
                OverlayState(
                    timestamp_seconds=600,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="15",
                    metadata={
                        "batter_number_source": "lineup_strip",
                        "lineup_strip_confidence": "lineup_full_strip",
                    },
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="15",
                    metadata={
                        "batter_number_source": "lineup_strip",
                        "lineup_strip_confidence": "lineup_full_strip",
                    },
                ),
            ],
            roster=roster,
        )

        self.assertEqual(
            [event.event_type for event in events],
            [EventType.HALF_INNING_START],
        )

    def test_detect_events_emits_at_bat_from_lineup_highlight_without_roster(self):
        events = detect_events(
            [
                OverlayState(
                    timestamp_seconds=600,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="26",
                    metadata={
                        "batter_number_source": "lineup_strip",
                        "lineup_strip_confidence": "lineup_highlight",
                    },
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="26",
                    metadata={
                        "batter_number_source": "lineup_strip",
                        "lineup_strip_confidence": "lineup_highlight",
                    },
                ),
            ]
        )

        at_bat = [event for event in events if event.event_type == EventType.AT_BAT_START][0]
        self.assertEqual(at_bat.player_number, "26")

    def test_detect_events_suppresses_full_strip_event_without_roster(self):
        events = detect_events(
            [
                OverlayState(
                    timestamp_seconds=600,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="15",
                    metadata={
                        "batter_number_source": "lineup_strip",
                        "lineup_strip_confidence": "lineup_full_strip",
                    },
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="15",
                    metadata={
                        "batter_number_source": "lineup_strip",
                        "lineup_strip_confidence": "lineup_full_strip",
                    },
                ),
            ]
        )

        self.assertEqual(
            [event.event_type for event in events],
            [EventType.HALF_INNING_START],
        )

    def test_detect_events_ignores_unrostered_lineup_number_when_roster_is_available(self):
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
                    batter_number="7",
                    metadata={"batter_number_source": "lineup_strip"},
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="7",
                    metadata={"batter_number_source": "lineup_strip"},
                ),
            ],
            roster=roster,
        )

        self.assertEqual(
            [event.event_type for event in events],
            [EventType.HALF_INNING_START],
        )

    def test_detect_events_ignores_unrostered_batter_card_number_when_roster_is_available(self):
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
                    batter_number="7",
                    metadata={"batter_number_source": "batter_card"},
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="7",
                    metadata={"batter_number_source": "batter_card"},
                ),
            ],
            roster=roster,
        )

        self.assertEqual(
            [event.event_type for event in events],
            [EventType.HALF_INNING_START],
        )

    def test_detect_events_ignores_unrostered_batter_card_with_unmatched_ocr_name(self):
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
                    batter_number="7",
                    metadata={
                        "batter_name": "Noisy Text",
                        "batter_number_source": "batter_card",
                    },
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="7",
                    metadata={
                        "batter_name": "Noisy Text",
                        "batter_number_source": "batter_card",
                    },
                ),
            ],
            roster=roster,
        )

        self.assertEqual(
            [event.event_type for event in events],
            [EventType.HALF_INNING_START],
        )

    def test_detect_events_named_card_match_is_not_overridden_by_lineup_disagreement(self):
        roster = Roster(
            team_name="Stars",
            players=[
                RosterPlayer(number="15", full_name="Riley S.", display_name="Riley S."),
                RosterPlayer(number="18", full_name="Other Player", display_name="Other Player"),
            ],
        )

        events = detect_events(
            [
                OverlayState(
                    timestamp_seconds=600,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="15",
                    metadata={
                        "batter_name": "Riley S.",
                        "batter_number_source": "batter_card",
                        "batter_number_disagreement": "batter_card=15 lineup=18",
                    },
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="15",
                    metadata={
                        "batter_name": "Riley S.",
                        "batter_number_source": "batter_card",
                        "batter_number_disagreement": "batter_card=15 lineup=18",
                    },
                ),
            ],
            roster=roster,
        )

        at_bat = [event for event in events if event.event_type == EventType.AT_BAT_START][0]
        self.assertEqual(at_bat.player_name, "Riley S.")
        self.assertEqual(at_bat.player_number, "15")
        self.assertEqual(at_bat.metadata["roster_match_source"], "name")
        self.assertEqual(
            at_bat.metadata["batter_number_disagreement"],
            "batter_card=15 lineup=18",
        )
        self.assertEqual(at_bat.metadata["batter_card_name"], "Riley S.")

    def test_detect_events_prefers_active_lineup_over_nameless_card_disagreement(self):
        roster = Roster(
            team_name="Stars",
            players=[
                RosterPlayer(number="2", full_name="Emma B.", display_name="Emma B."),
                RosterPlayer(number="15", full_name="Riley S.", display_name="Riley S."),
            ],
        )

        events = detect_events(
            [
                OverlayState(
                    timestamp_seconds=600,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="2",
                    metadata={
                        "batter_name": "",
                        "batter_number_source": "batter_card",
                        "batter_number_disagreement": "batter_card=2 lineup=15",
                        "lineup_strip_number": "15",
                        "lineup_strip_confidence": "lineup_full_strip",
                    },
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="2",
                    metadata={
                        "batter_name": "",
                        "batter_number_source": "batter_card",
                        "batter_number_disagreement": "batter_card=2 lineup=15",
                        "lineup_strip_number": "15",
                        "lineup_strip_confidence": "lineup_full_strip",
                    },
                ),
            ],
            roster=roster,
        )

        at_bat = [event for event in events if event.event_type == EventType.AT_BAT_START][0]
        self.assertEqual(at_bat.player_name, "Riley S.")
        self.assertEqual(at_bat.player_number, "15")
        self.assertEqual(at_bat.metadata["roster_match_source"], "lineup_number")

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
            [event.label for event in events if event.event_type == EventType.AT_BAT_START],
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

    def test_detect_events_uses_roster_name_when_lineup_digit_run_is_invalid(self):
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
                    batter_number="213",
                    metadata={
                        "batter_name": "Ava T.",
                        "batter_number_source": "lineup_strip",
                        "lineup_strip_confidence": "lineup_highlight",
                    },
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="213",
                    metadata={
                        "batter_name": "Ava T.",
                        "batter_number_source": "lineup_strip",
                        "lineup_strip_confidence": "lineup_highlight",
                    },
                ),
            ],
            roster=roster,
        )

        at_bat = [event for event in events if event.event_type == EventType.AT_BAT_START][0]
        self.assertEqual(at_bat.player_name, "Ava T.")
        self.assertEqual(at_bat.player_number, "5")

    def test_detect_events_uses_jersey_number_from_card_name_text(self):
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="4", full_name="Sofia L.", display_name="Sofia L.")],
        )

        events = detect_events(
            [
                OverlayState(
                    timestamp_seconds=600,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="213",
                    metadata={
                        "batter_name": "#4",
                        "batter_number_source": "lineup_strip",
                        "lineup_strip_confidence": "lineup_highlight",
                    },
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="213",
                    metadata={
                        "batter_name": "#4",
                        "batter_number_source": "lineup_strip",
                        "lineup_strip_confidence": "lineup_highlight",
                    },
                ),
            ],
            roster=roster,
        )

        at_bat = [event for event in events if event.event_type == EventType.AT_BAT_START][0]
        self.assertEqual(at_bat.player_name, "Sofia L.")
        self.assertEqual(at_bat.player_number, "4")

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

    def test_detect_events_allows_short_spacing_for_name_confirmed_batters(self):
        roster = Roster(
            team_name="Stars",
            players=[
                RosterPlayer(number="22", full_name="Maya R.", display_name="Maya R."),
                RosterPlayer(number="26", full_name="Amelia V.", display_name="Amelia V."),
            ],
        )

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
                OverlayState(
                    622,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="26",
                    metadata={"batter_name": "Amelia V."},
                ),
                OverlayState(
                    627,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="26",
                    metadata={"batter_name": "Amelia V."},
                ),
            ],
            roster=roster,
        )

        self.assertEqual(
            [event.player_number for event in events if event.event_type == EventType.AT_BAT_START],
            ["22", "26"],
        )

    def test_detect_events_keeps_long_spacing_for_unconfirmed_batters(self):
        events = detect_events(
            [
                OverlayState(600, inning=1, half=HalfInning.TOP, batter_number="22"),
                OverlayState(605, inning=1, half=HalfInning.TOP, batter_number="22"),
                OverlayState(622, inning=1, half=HalfInning.TOP, batter_number="26"),
                OverlayState(627, inning=1, half=HalfInning.TOP, batter_number="26"),
            ]
        )

        self.assertEqual(
            [event.player_number for event in events if event.event_type == EventType.AT_BAT_START],
            ["22"],
        )

    def test_detect_events_honors_custom_roster_confirmed_spacing(self):
        roster = Roster(
            team_name="Stars",
            players=[
                RosterPlayer(number="22", full_name="Maya R.", display_name="Maya R."),
                RosterPlayer(number="26", full_name="Amelia V.", display_name="Amelia V."),
            ],
        )

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
                OverlayState(
                    622,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="26",
                    metadata={"batter_name": "Amelia V."},
                ),
                OverlayState(
                    627,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="26",
                    metadata={"batter_name": "Amelia V."},
                ),
            ],
            roster=roster,
            min_at_bat_spacing_roster_confirmed_seconds=30,
        )

        self.assertEqual(
            [event.player_number for event in events if event.event_type == EventType.AT_BAT_START],
            ["22"],
        )

    def test_at_bat_spacing_for_roster_match_uses_roster_confirmed_floor(self):
        self.assertEqual(_at_bat_spacing_for_roster_match("name", 45, 20), 20)
        self.assertEqual(_at_bat_spacing_for_roster_match("number", 45, 20), 20)
        self.assertEqual(_at_bat_spacing_for_roster_match("lineup_number", 45, 20), 20)
        self.assertEqual(_at_bat_spacing_for_roster_match(None, 45, 20), 45)
        self.assertEqual(_at_bat_spacing_for_roster_match("other", 45, 20), 45)

    def test_resolve_lineup_digit_run_returns_single_roster_match(self):
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="26", full_name="Amelia V.", display_name="Amelia V.")],
        )

        self.assertEqual(_resolve_lineup_digit_run("265", roster), "26")
        self.assertIsNone(_resolve_lineup_digit_run("26", roster))
        self.assertIsNone(_resolve_lineup_digit_run("789", roster))

    def test_resolve_lineup_digit_run_rejects_ambiguous_matches(self):
        roster = Roster(
            team_name="Stars",
            players=[
                RosterPlayer(number="2", full_name="Emma B.", display_name="Emma B."),
                RosterPlayer(number="26", full_name="Amelia V.", display_name="Amelia V."),
            ],
        )

        self.assertIsNone(_resolve_lineup_digit_run("265", roster))

    def test_enrich_states_digit_runs_resolves_unambiguous_lineup_numbers(self):
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="26", full_name="Amelia V.", display_name="Amelia V.")],
        )
        state = OverlayState(
            timestamp_seconds=600,
            inning=1,
            half=HalfInning.TOP,
            batter_number="265",
            metadata={
                "batter_number_source": "lineup_strip",
                "lineup_strip_confidence": "lineup_highlight",
            },
        )

        enriched = _enrich_states_digit_runs([state], roster)

        self.assertEqual(enriched[0].batter_number, "26")
        self.assertEqual(enriched[0].metadata["batter_number_digit_run_original"], "265")

    def test_enrich_states_digit_runs_skips_full_strip_states(self):
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="26", full_name="Amelia V.", display_name="Amelia V.")],
        )
        state = OverlayState(
            timestamp_seconds=600,
            inning=1,
            half=HalfInning.TOP,
            batter_number="265",
            metadata={
                "batter_number_source": "lineup_strip",
                "lineup_strip_confidence": "lineup_full_strip",
            },
        )

        enriched = _enrich_states_digit_runs([state], roster)

        self.assertEqual(enriched[0].batter_number, "265")
        self.assertNotIn("batter_number_digit_run_original", enriched[0].metadata)

    def test_confirmed_batter_identity_counts_unambiguous_full_strip_digit_run(self):
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
                    batter_number="265",
                    metadata={
                        "batter_number_source": "lineup_strip",
                        "lineup_strip_confidence": "lineup_highlight",
                    },
                ),
                OverlayState(
                    timestamp_seconds=605,
                    inning=1,
                    half=HalfInning.TOP,
                    batter_number="265",
                    metadata={
                        "batter_number_source": "lineup_strip",
                        "lineup_strip_confidence": "lineup_full_strip",
                    },
                ),
            ],
            roster=roster,
        )

        at_bat = [event for event in events if event.event_type == EventType.AT_BAT_START][0]
        self.assertEqual(at_bat.player_name, "Amelia V.")
        self.assertEqual(at_bat.player_number, "26")

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

    def test_detect_events_file_forwards_min_game_final_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            states_path = Path(directory) / "states.jsonl"
            write_jsonl(
                states_path,
                [
                    OverlayState(900, metadata={"game_status": "final"}),
                    OverlayState(905, metadata={"game_status": "final"}),
                ],
            )

            result = detect_events_file(states_path, min_game_final_observations=2)

            self.assertEqual(result.event_count, 1)
            self.assertIn('"event_type": "game_final"', result.output_path.read_text())

    def test_export_text_from_detected_events(self):
        events = detect_events(
            [
                OverlayState(600, inning=1, half=HalfInning.TOP, batter_number="22"),
                OverlayState(605, inning=1, half=HalfInning.TOP, batter_number="22"),
            ]
        )

        self.assertEqual(
            export_youtube_chapters(events, include_credit=False),
            "0:00 Pregame\n10:00 Top 1",
        )
        self.assertEqual(
            export_at_bat_comment(events, include_credit=False),
            "1st Inning\n10:00 #22",
        )

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

        self.assertEqual(
            export_at_bat_comment(events, include_credit=False),
            "1st Inning\n10:00 Maya R. (#22)",
        )

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
            [event.label for event in events if event.event_type == EventType.HALF_INNING_START],
            ["Top 1", "Top 2"],
        )

    def test_score_snapshot_returns_first_complete_pair_in_window(self):
        states = [
            OverlayState(600, inning=1, half=HalfInning.TOP, away_score=None, home_score=1),
            OverlayState(605, inning=1, half=HalfInning.TOP, away_score=2, home_score=1),
            OverlayState(610, inning=1, half=HalfInning.TOP, away_score=3, home_score=1),
        ]

        self.assertEqual(_score_snapshot(states, 0, 2, half_key=(1, HalfInning.TOP)), (2, 1))

    def test_score_snapshot_returns_empty_pair_when_window_has_no_complete_score(self):
        states = [
            OverlayState(600, inning=1, half=HalfInning.TOP, away_score=None, home_score=1),
            OverlayState(605, inning=1, half=HalfInning.TOP, away_score=2, home_score=None),
            OverlayState(610, inning=1, half=HalfInning.TOP, away_score=3, home_score=1),
        ]

        self.assertEqual(_score_snapshot(states, 0, 2), (None, None))

    def test_score_snapshot_ignores_scores_from_different_half_inning(self):
        states = [
            OverlayState(600, inning=3, half=HalfInning.TOP),
            OverlayState(605, inning=3, half=HalfInning.TOP),
            OverlayState(610, inning=3, half=HalfInning.TOP),
            OverlayState(615, inning=3, half=HalfInning.TOP),
            OverlayState(620, inning=3, half=HalfInning.BOTTOM, away_score=4, home_score=2),
            OverlayState(625, inning=3, half=HalfInning.BOTTOM, away_score=4, home_score=2),
        ]

        self.assertEqual(
            _score_snapshot(states, 0, 6, half_key=(3, HalfInning.TOP)),
            (None, None),
        )

    def test_detect_events_stores_score_snapshot_on_half_inning_start(self):
        events = detect_events(
            [
                OverlayState(
                    600,
                    inning=1,
                    half=HalfInning.TOP,
                    away_score=None,
                    home_score=0,
                ),
                OverlayState(
                    605,
                    inning=1,
                    half=HalfInning.TOP,
                    away_score=2,
                    home_score=0,
                ),
                OverlayState(
                    610,
                    inning=1,
                    half=HalfInning.TOP,
                    away_score=2,
                    home_score=0,
                ),
                OverlayState(
                    615,
                    inning=1,
                    half=HalfInning.TOP,
                    away_score=3,
                    home_score=0,
                ),
            ]
        )

        chapter = next(event for event in events if event.event_type == EventType.HALF_INNING_START)
        self.assertEqual(chapter.metadata["away_score"], 2)
        self.assertEqual(chapter.metadata["home_score"], 0)

    def test_detect_events_stores_empty_score_when_confirmation_window_has_no_pair(self):
        events = detect_events(
            [
                OverlayState(
                    600,
                    inning=1,
                    half=HalfInning.TOP,
                    away_score=None,
                    home_score=0,
                ),
                OverlayState(
                    605,
                    inning=1,
                    half=HalfInning.TOP,
                    away_score=1,
                    home_score=None,
                ),
            ]
        )

        chapter = next(event for event in events if event.event_type == EventType.HALF_INNING_START)
        self.assertIsNone(chapter.metadata["away_score"])
        self.assertIsNone(chapter.metadata["home_score"])

    def test_detect_events_defers_first_chapter_to_game_active_timestamp_on_pregame_stream(
        self,
    ):
        states = [
            OverlayState(
                timestamp_seconds=0,
                inning=1,
                half=HalfInning.TOP,
                metadata={"batter_name": ">", "fields": {"count": "1", "inning": ""}},
            ),
            OverlayState(
                timestamp_seconds=5,
                inning=1,
                half=HalfInning.TOP,
                metadata={"batter_name": "~~", "fields": {"count": "1", "inning": ""}},
            ),
            OverlayState(
                timestamp_seconds=10,
                inning=1,
                half=HalfInning.TOP,
                metadata={"batter_name": "Se", "fields": {"count": "1", "inning": ""}},
            ),
            OverlayState(
                timestamp_seconds=535,
                inning=1,
                half=HalfInning.TOP,
                balls=0,
                strikes=0,
                batter_number="4",
            ),
            OverlayState(
                timestamp_seconds=540,
                inning=1,
                half=HalfInning.TOP,
                balls=0,
                strikes=0,
                batter_number="10",
                metadata={
                    "batter_name": "Teagan L.",
                    "batter_number_source": "batter_card",
                },
            ),
            OverlayState(
                timestamp_seconds=550,
                inning=1,
                half=HalfInning.TOP,
                balls=0,
                strikes=1,
                batter_number="4",
            ),
        ]

        events = detect_events(states)

        chapters = [event for event in events if event.event_type == EventType.HALF_INNING_START]
        self.assertEqual(
            [(event.timestamp_seconds, event.label) for event in chapters], [(550, "Top 1")]
        )
        self.assertEqual(
            export_youtube_chapters(events, include_credit=False),
            "0:00 Pregame\n9:10 Top 1",
        )

    def test_detect_events_defers_first_chapter_until_activity_after_pregame(self):
        states = [
            OverlayState(0, inning=1, half=HalfInning.TOP, metadata={"game_status": "pregame"}),
            OverlayState(5, inning=1, half=HalfInning.TOP, metadata={"game_status": "pregame"}),
            OverlayState(10, inning=1, half=HalfInning.TOP, metadata={"game_status": "pregame"}),
            OverlayState(395, inning=1, half=HalfInning.TOP, balls=0, strikes=0, batter_number="10"),
            OverlayState(400, inning=1, half=HalfInning.TOP, balls=0, strikes=0, batter_number="10"),
            OverlayState(405, inning=1, half=HalfInning.TOP, balls=0, strikes=1, batter_number="10"),
        ]

        events = detect_events(states)

        chapters = [event for event in events if event.event_type == EventType.HALF_INNING_START]
        self.assertEqual(
            [(event.timestamp_seconds, event.label) for event in chapters],
            [(405, "Top 1")],
        )
        self.assertEqual(
            export_youtube_chapters(events, include_credit=False),
            "0:00 Pregame\n6:45 Top 1",
        )

    def test_detect_events_emits_first_chapter_at_zero_for_mid_game_stream_start(self):
        events = detect_events(
            [
                OverlayState(
                    0,
                    inning=1,
                    half=HalfInning.TOP,
                    balls=1,
                    strikes=0,
                    batter_number="22",
                ),
                OverlayState(
                    5,
                    inning=1,
                    half=HalfInning.TOP,
                    balls=1,
                    strikes=0,
                    batter_number="22",
                ),
                OverlayState(
                    10,
                    inning=1,
                    half=HalfInning.TOP,
                    balls=1,
                    strikes=0,
                    batter_number="22",
                ),
                OverlayState(
                    15,
                    inning=1,
                    half=HalfInning.TOP,
                    balls=1,
                    strikes=0,
                    batter_number="22",
                ),
            ]
        )

        chapters = [event for event in events if event.event_type == EventType.HALF_INNING_START]
        self.assertEqual([(event.timestamp_seconds, event.label) for event in chapters], [(0, "Top 1")])

    def test_detect_events_skips_activity_signal_for_non_zero_starting_stream(self):
        events = detect_events(
            [
                OverlayState(600, inning=1, half=HalfInning.TOP, balls=0, strikes=0, batter_number="22"),
                OverlayState(605, inning=1, half=HalfInning.TOP, balls=0, strikes=0, batter_number="22"),
            ]
        )

        chapters = [event for event in events if event.event_type == EventType.HALF_INNING_START]
        self.assertEqual(
            [(event.timestamp_seconds, event.label) for event in chapters],
            [(600, "Top 1")],
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
                OverlayState(
                    0,
                    inning=1,
                    half=HalfInning.TOP,
                    balls=0,
                    strikes=1,
                    batter_number="22",
                ),
                OverlayState(
                    5,
                    inning=1,
                    half=HalfInning.TOP,
                    balls=0,
                    strikes=1,
                    batter_number="22",
                ),
                OverlayState(
                    10,
                    inning=1,
                    half=HalfInning.TOP,
                    balls=0,
                    strikes=1,
                    batter_number="22",
                ),
                OverlayState(
                    15,
                    inning=1,
                    half=HalfInning.TOP,
                    balls=0,
                    strikes=1,
                    batter_number="22",
                ),
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
            [event.label for event in events if event.event_type == EventType.HALF_INNING_START],
            ["Top 1", "Bottom 1", "Top 2"],
        )
        self.assertEqual(
            [event.player_number for event in events if event.event_type == EventType.AT_BAT_START],
            ["22", "24"],
        )

    def test_detect_events_subsequent_half_innings_unaffected_by_activity_signal_change(self):
        events = detect_events(
            [
                OverlayState(0, inning=1, half=HalfInning.TOP, balls=1, strikes=0, batter_number="22"),
                OverlayState(5, inning=1, half=HalfInning.TOP, balls=1, strikes=0, batter_number="22"),
                OverlayState(10, inning=1, half=HalfInning.TOP, balls=1, strikes=0, batter_number="22"),
                OverlayState(15, inning=1, half=HalfInning.TOP, balls=1, strikes=0, batter_number="22"),
                OverlayState(900, inning=1, half=HalfInning.BOTTOM, balls=0, strikes=0, batter_number="10"),
                OverlayState(905, inning=1, half=HalfInning.BOTTOM, balls=0, strikes=0, batter_number="10"),
                OverlayState(910, inning=1, half=HalfInning.BOTTOM, balls=0, strikes=0, batter_number="10"),
                OverlayState(915, inning=1, half=HalfInning.BOTTOM, balls=0, strikes=0, batter_number="10"),
            ]
        )

        self.assertEqual(
            [
                (event.timestamp_seconds, event.label)
                for event in events
                if event.event_type == EventType.HALF_INNING_START
            ],
            [(0, "Top 1"), (900, "Bottom 1")],
        )

    def test_infer_batting_cycle_returns_cycle_from_first_qualifying_half(self):
        events = [
            self._at_bat("8", 100, half=HalfInning.TOP),
            self._at_bat("9", 160, half=HalfInning.TOP),
            self._at_bat("26", 300),
            self._at_bat("2", 360),
            self._at_bat("13", 420),
        ]

        self.assertEqual(infer_batting_cycle(events), ["26", "2", "13"])

    def test_infer_batting_cycle_sorts_top_before_bottom_in_same_inning(self):
        events = [
            self._at_bat("8", 100, half=HalfInning.TOP),
            self._at_bat("9", 160, half=HalfInning.TOP),
            self._at_bat("10", 220, half=HalfInning.TOP),
            self._at_bat("26", 300),
            self._at_bat("2", 360),
            self._at_bat("13", 420),
        ]

        self.assertEqual(infer_batting_cycle(events), ["8", "9", "10"])

    def test_infer_batting_cycle_returns_empty_when_insufficient_confirmed_events(self):
        events = [
            self._at_bat("26", 300),
            self._at_bat("2", 360),
        ]

        self.assertEqual(infer_batting_cycle(events), [])

    def test_infer_batting_cycle_ignores_unconfirmed_events(self):
        events = [
            self._at_bat("26", 300, source="batting_order"),
            self._at_bat("2", 360, source=None),
            self._at_bat("13", 420, source="lineup_number"),
        ]

        self.assertEqual(infer_batting_cycle(events), [])

    def test_infer_batting_cycle_deduplicates_repeated_player(self):
        events = [
            self._at_bat("26", 300),
            self._at_bat("2", 360),
            self._at_bat("13", 420),
            self._at_bat("26", 480),
        ]

        self.assertEqual(infer_batting_cycle(events), ["26", "2", "13"])

    def test_validate_batting_order_synthesizes_inferred_event_for_one_skipped_batter(self):
        events = [
            self._chapter(90, inning=1),
            self._at_bat("26", 100, inning=1),
            self._at_bat("2", 160, inning=1),
            self._at_bat("13", 220, inning=1),
            self._chapter(290, inning=2),
            self._at_bat("26", 300, inning=2),
            self._at_bat("13", 360, inning=2),
        ]

        validated = validate_batting_order(events)
        inferred = [
            event
            for event in validated
            if event.metadata.get("order_flags") == ["inferred-missing"]
        ]

        self.assertEqual([(event.player_number, event.timestamp_seconds) for event in inferred], [("2", 330)])
        self.assertEqual(inferred[0].metadata["roster_match_source"], "batting_order")
        self.assertEqual(
            [event.player_number for event in validated if event.event_type == EventType.AT_BAT_START],
            ["26", "2", "13", "26", "2", "13"],
        )

    def test_validate_batting_order_synthesizes_two_inferred_events_for_two_skipped_batters(self):
        events = [
            self._chapter(90, inning=1),
            self._at_bat("26", 100, inning=1),
            self._at_bat("2", 160, inning=1),
            self._at_bat("13", 220, inning=1),
            self._chapter(290, inning=2),
            self._at_bat("26", 300, inning=2),
            self._at_bat("26", 390, inning=2),
        ]

        validated = validate_batting_order(events)
        inferred = [
            event
            for event in validated
            if event.metadata.get("order_flags") == ["inferred-missing"]
        ]

        self.assertEqual(
            [(event.player_number, event.timestamp_seconds) for event in inferred],
            [("2", 330), ("13", 360)],
        )

    def test_validate_batting_order_flags_out_of_order_when_forward_skip_exceeds_tolerance(self):
        events = [
            self._at_bat("26", 100),
            self._at_bat("2", 160),
            self._at_bat("13", 220),
            self._at_bat("5", 280),
            self._at_bat("4", 340),
            self._chapter(390, inning=2),
            self._at_bat("26", 400, inning=2),
            self._at_bat("4", 460, inning=2),
        ]

        validated = validate_batting_order(events)
        flagged = [event for event in validated if event.player_number == "4" and event.inning == 2][0]

        self.assertIn("out-of-order-candidate", flagged.metadata["order_flags"])

    def test_validate_batting_order_does_not_flag_roster_confirmed_player_outside_seed_cycle(self):
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="99", full_name="Emma B.", display_name="Emma B.")],
        )
        events = [
            self._at_bat("26", 100),
            self._at_bat("2", 160),
            self._at_bat("13", 220),
            self._chapter(290, inning=2),
            self._at_bat("99", 300, inning=2),
            self._at_bat("26", 360, inning=2),
        ]

        validated = validate_batting_order(events, roster=roster)
        roster_confirmed = [event for event in validated if event.player_number == "99"][0]

        self.assertNotIn("order_flags", roster_confirmed.metadata)

    def test_validate_batting_order_flags_possible_substitute_for_unknown_player(self):
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="8", full_name="Olivia M.", display_name="Olivia M.")],
        )
        events = [
            self._at_bat("26", 100),
            self._at_bat("2", 160),
            self._at_bat("13", 220),
            self._chapter(290, inning=2),
            self._at_bat("99", 300, inning=2),
            self._at_bat("26", 360, inning=2),
        ]

        validated = validate_batting_order(events, roster=roster)
        substitute = [event for event in validated if event.player_number == "99"][0]

        self.assertIn("possible-substitute", substitute.metadata["order_flags"])
        self.assertFalse(
            [
                event
                for event in validated
                if event.metadata.get("order_flags") == ["inferred-missing"]
            ]
        )

    def test_validate_batting_order_inferred_event_prefers_observed_name(self):
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="2", full_name="Savanah P.", display_name="Savanah P.")],
        )
        events = [
            self._at_bat("26", 100),
            self._at_bat("2", 160, name="Bobby S."),
            self._at_bat("13", 220),
            self._at_bat("26", 300),
            self._at_bat("13", 360),
        ]

        validated = validate_batting_order(events, roster=roster)
        inferred = [
            event
            for event in validated
            if event.metadata.get("order_flags") == ["inferred-missing"]
        ][0]

        self.assertEqual(inferred.player_name, "Bobby S.")
        self.assertEqual(inferred.label, "Bobby S. (#2)")

    def test_validate_batting_order_inferred_event_uses_roster_name_as_fallback(self):
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="2", full_name="Savanah P.", display_name="Savanah P.")],
        )
        events = [
            self._at_bat("26", 100),
            Event(
                EventType.AT_BAT_START,
                160,
                "#2",
                inning=1,
                half=HalfInning.BOTTOM,
                player_number="2",
                metadata={"roster_match_source": "number"},
            ),
            self._at_bat("13", 220),
            self._at_bat("26", 300),
            self._at_bat("13", 360),
        ]

        validated = validate_batting_order(events, roster=roster)
        inferred = [
            event
            for event in validated
            if event.metadata.get("order_flags") == ["inferred-missing"]
        ][0]

        self.assertEqual(inferred.player_name, "Savanah P.")
        self.assertEqual(inferred.label, "Savanah P. (#2)")

    def test_validate_batting_order_does_not_infer_missing_events_across_inning_boundary(self):
        events = [
            self._at_bat("26", 100),
            self._at_bat("2", 160),
            self._at_bat("13", 220),
            self._chapter(300, inning=2),
            self._at_bat("13", 360, inning=2),
        ]

        validated = validate_batting_order(events)
        inferred = [
            event
            for event in validated
            if event.metadata.get("order_flags") == ["inferred-missing"]
        ]

        self.assertEqual(inferred, [])

    def test_validate_batting_order_opposite_half_events_pass_through(self):
        events = [
            self._at_bat("26", 100),
            self._at_bat("2", 160),
            self._at_bat("13", 220),
            self._at_bat("8", 300, inning=1, half=HalfInning.TOP),
        ]

        validated = validate_batting_order(events)
        top_event = [event for event in validated if event.half == HalfInning.TOP][0]

        self.assertEqual(top_event.player_number, "8")
        self.assertNotIn("order_flags", top_event.metadata)

    def test_validate_batting_order_no_cycle_returns_events_unchanged(self):
        events = [self._at_bat("26", 100), self._at_bat("2", 160)]

        self.assertEqual(validate_batting_order(events), events)

    def test_infer_batting_half_uses_roster_name_match_counts(self):
        roster = Roster(
            team_name="Stars",
            players=[
                RosterPlayer(number="22", full_name="Maya R.", display_name="Maya R."),
                RosterPlayer(number="26", full_name="Amelia V.", display_name="Amelia V."),
            ],
        )
        events = [
            Event(EventType.AT_BAT_START, 600, "#22", half=HalfInning.TOP, player_number="22"),
            Event(
                EventType.AT_BAT_START,
                900,
                "Maya R. (#22)",
                half=HalfInning.BOTTOM,
                player_number="22",
                player_name="Maya R.",
                metadata={"roster_match_source": "name"},
            ),
            Event(
                EventType.AT_BAT_START,
                960,
                "Amelia V. (#26)",
                half=HalfInning.BOTTOM,
                player_number="26",
                player_name="Amelia V.",
                metadata={"roster_match_source": "name"},
            ),
        ]

        inference = infer_batting_half(events, roster)

        self.assertEqual(inference.inferred_half, HalfInning.BOTTOM)
        self.assertEqual(inference.top_at_bats, 1)
        self.assertEqual(inference.top_roster_matches, 0)
        self.assertEqual(inference.bottom_at_bats, 2)
        self.assertEqual(inference.bottom_roster_matches, 2)
        self.assertIn("Inferred batting half: bottom", inference.message)

    def test_infer_batting_half_falls_back_to_both_without_roster_matches(self):
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="22", full_name="Maya R.", display_name="Maya R.")],
        )
        events = [
            Event(EventType.AT_BAT_START, 600, "#22", half=HalfInning.TOP, player_number="22"),
            Event(EventType.AT_BAT_START, 900, "#8", half=HalfInning.BOTTOM, player_number="8"),
        ]

        inference = infer_batting_half(events, roster)

        self.assertIsNone(inference.inferred_half)
        self.assertEqual(inference.warning, "no roster-name matches found")
        self.assertIn("Inferred batting half: both", inference.message)

    def test_infer_batting_half_ignores_lineup_number_matches(self):
        roster = Roster(
            team_name="Stars",
            players=[RosterPlayer(number="26", full_name="Amelia V.", display_name="Amelia V.")],
        )
        events = [
            Event(
                EventType.AT_BAT_START,
                600,
                "Amelia V. (#26)",
                half=HalfInning.TOP,
                player_number="26",
                player_name="Amelia V.",
                metadata={"roster_match_source": "lineup_number"},
            ),
        ]

        inference = infer_batting_half(events, roster)

        self.assertIsNone(inference.inferred_half)
        self.assertEqual(inference.top_roster_matches, 0)
        self.assertEqual(inference.warning, "no roster-name matches found")

    def test_infer_batting_half_falls_back_to_both_without_roster(self):
        events = [
            Event(EventType.AT_BAT_START, 600, "#22", half=HalfInning.TOP, player_number="22"),
            Event(EventType.AT_BAT_START, 900, "#8", half=HalfInning.BOTTOM, player_number="8"),
        ]

        inference = infer_batting_half(events, None)

        self.assertIsNone(inference.inferred_half)
        self.assertEqual(inference.warning, "no roster provided")
        self.assertIn("Inferred batting half: both", inference.message)

    def test_infer_batting_half_ignores_enriched_match_metadata_without_roster(self):
        events = [
            Event(
                EventType.AT_BAT_START,
                600,
                "Maya R. (#22)",
                half=HalfInning.TOP,
                player_number="22",
                player_name="Maya R.",
                metadata={"roster_match_source": "name"},
            ),
        ]

        inference = infer_batting_half(events, None)

        self.assertIsNone(inference.inferred_half)
        self.assertEqual(inference.warning, "no roster provided")
        self.assertEqual(inference.top_at_bats, 1)
        self.assertEqual(inference.top_roster_matches, 0)

    def test_filter_at_bats_to_half_keeps_chapters_and_selected_at_bats(self):
        events = [
            Event(EventType.HALF_INNING_START, 590, "Top 1", inning=1, half=HalfInning.TOP),
            Event(EventType.AT_BAT_START, 600, "#22", half=HalfInning.TOP, player_number="22"),
            Event(EventType.HALF_INNING_START, 890, "Bottom 1", inning=1, half=HalfInning.BOTTOM),
            Event(EventType.AT_BAT_START, 900, "#26", half=HalfInning.BOTTOM, player_number="26"),
        ]

        filtered = filter_at_bats_to_half(events, HalfInning.BOTTOM)

        self.assertEqual(
            [event.label for event in filtered],
            ["Top 1", "Bottom 1", "#26"],
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
            [event.player_number for event in events if event.event_type == EventType.AT_BAT_START],
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
