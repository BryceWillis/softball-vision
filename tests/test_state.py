import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from sidelinehd_extractor.constants import INNING_ARROW_DOWN, INNING_ARROW_UP
from sidelinehd_extractor.models import HalfInning, OCRSample, OverlayState
from sidelinehd_extractor.processing import write_jsonl
from sidelinehd_extractor.state import (
    _normalize_game_status,
    load_ocr_samples,
    parse_count,
    parse_inning,
    parse_jersey_number,
    parse_samples_file,
    parse_score,
    parse_states,
    smooth_states,
    state_from_samples,
)


class StateParsingTests(unittest.TestCase):
    def test_parse_count(self):
        self.assertEqual(parse_count("2-0"), (2, 0))
        self.assertEqual(parse_count("noise"), (None, None))

    def test_parse_jersey_number(self):
        self.assertEqual(parse_jersey_number("#22"), "22")
        self.assertIsNone(parse_jersey_number(""))

    def test_parse_score(self):
        self.assertEqual(parse_score("2"), 2)
        self.assertEqual(parse_score("#12"), 12)
        self.assertEqual(parse_score("Home 5"), 5)
        self.assertIsNone(parse_score(""))
        self.assertIsNone(parse_score(None))
        self.assertIsNone(parse_score("noise"))

    def test_parse_score_rejects_implausible_reads(self):
        # Item 60: "164" is the real score 16 with a fused scorebug glyph.
        self.assertIsNone(parse_score("164"))
        self.assertIsNone(parse_score("51"))
        self.assertIsNone(parse_score("100"))
        # Legitimate scores up to the cap still parse.
        self.assertEqual(parse_score("0"), 0)
        self.assertEqual(parse_score("21"), 21)
        self.assertEqual(parse_score("50"), 50)

    def test_normalize_game_status_detects_final(self):
        self.assertEqual(_normalize_game_status("FINAL"), "final")
        self.assertEqual(_normalize_game_status("Game Final"), "final")
        self.assertIsNone(_normalize_game_status("in play"))
        self.assertIsNone(_normalize_game_status(None))

    def test_normalize_game_status_detects_pregame(self):
        self.assertEqual(_normalize_game_status("GAME STARTING SOON"), "pregame")
        self.assertEqual(_normalize_game_status("GAME 7:00 SOON"), "pregame")
        self.assertEqual(_normalize_game_status("GAM Soon NG"), "pregame")
        self.assertEqual(_normalize_game_status("GAM BOON NG"), "pregame")
        self.assertEqual(_normalize_game_status("GAME oon NG"), "pregame")
        self.assertEqual(_normalize_game_status("OAM Eom NG"), "pregame")
        self.assertIsNone(_normalize_game_status("Smash-It Sports 12U"))
        self.assertIsNone(_normalize_game_status("a1 0-0"))
        self.assertIsNone(_normalize_game_status("GAME ON FIELD"))

    def test_parse_inning_handles_noisy_top_first(self):
        self.assertEqual(parse_inning("o1"), (1, HalfInning.TOP))
        self.assertEqual(parse_inning("o 1"), (1, HalfInning.TOP))
        self.assertEqual(parse_inning("1"), (1, None))
        self.assertEqual(parse_inning("71"), (1, HalfInning.BOTTOM))
        self.assertEqual(parse_inning("42"), (2, HalfInning.TOP))
        self.assertEqual(parse_inning("720"), (2, HalfInning.BOTTOM))
        self.assertEqual(parse_inning("▼3"), (3, HalfInning.BOTTOM))
        self.assertEqual(parse_inning("37"), (3, None))
        self.assertEqual(parse_inning("0"), (None, None))
        self.assertEqual(parse_inning("00"), (None, None))

    def test_parse_inning_handles_sidelinehd_arrow_ocr_artifacts(self):
        cases = [
            ("41", (1, HalfInning.TOP)),
            ("42", (2, HalfInning.TOP)),
            ("04", (4, HalfInning.TOP)),
            ("71", (1, HalfInning.BOTTOM)),
            ("72", (2, HalfInning.BOTTOM)),
            ("73", (3, HalfInning.BOTTOM)),
            ("720", (2, HalfInning.BOTTOM)),
            ("▲4", (4, HalfInning.TOP)),
            ("△5", (5, HalfInning.TOP)),
            ("^6", (6, HalfInning.TOP)),
            ("↑7", (7, HalfInning.TOP)),
            ("▼4", (4, HalfInning.BOTTOM)),
            ("▽5", (5, HalfInning.BOTTOM)),
            ("↓6", (6, HalfInning.BOTTOM)),
            ("v7", (7, HalfInning.BOTTOM)),
            ("b8", (8, HalfInning.BOTTOM)),
        ]

        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(parse_inning(value), expected)

    def test_parse_inning_handles_oversized_and_blank_reads(self):
        cases = [
            (None, (None, None)),
            ("", (None, None)),
            ("   ", (None, None)),
            ("0", (None, None)),
            ("00", (None, None)),
            ("37", (3, None)),
            ("102", (1, None)),
            ("909", (9, None)),
            ("abc", (None, None)),
        ]

        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(parse_inning(value), expected)

    def test_parse_states_groups_samples_by_timestamp(self):
        states = parse_states(
            [
                OCRSample(600.0, "inning", "o1", normalized_text="o1"),
                OCRSample(600.0, "count", "0-0", normalized_text="0-0"),
                OCRSample(600.0, "batter_card_name", "Maya R.", normalized_text="Maya R."),
                OCRSample(600.0, "batter_card_number", "#22", normalized_text="#22"),
            ]
        )

        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].inning, 1)
        self.assertEqual(states[0].half, HalfInning.TOP)
        self.assertEqual(states[0].balls, 0)
        self.assertEqual(states[0].strikes, 0)
        self.assertEqual(states[0].batter_number, "22")
        self.assertEqual(states[0].metadata["batter_name"], "Maya R.")
        self.assertEqual(states[0].metadata["batter_number_source"], "batter_card")

    def test_state_from_samples_maps_left_and_right_scores(self):
        state = state_from_samples(
            600.0,
            {
                "left_score": OCRSample(600.0, "left_score", "2", normalized_text="2"),
                "right_score": OCRSample(600.0, "right_score", "1", normalized_text="1"),
            },
        )

        self.assertEqual(state.away_score, 2)
        self.assertEqual(state.home_score, 1)

    def test_state_from_samples_drops_implausible_score_reads(self):
        state = state_from_samples(
            600.0,
            {
                "left_score": OCRSample(600.0, "left_score", "164", normalized_text="164"),
                "right_score": OCRSample(600.0, "right_score", "21", normalized_text="21"),
            },
        )

        self.assertIsNone(state.away_score)
        self.assertEqual(state.home_score, 21)

    def test_state_from_samples_prefers_pixel_arrow_half_over_text(self):
        state = state_from_samples(
            600.0,
            {
                # Text-only parsing would call "43" a top half ("4" prefix);
                # the pixel-detected down arrow must win.
                "inning": OCRSample(
                    600.0,
                    "inning",
                    "43",
                    normalized_text="43",
                    source_detail=INNING_ARROW_DOWN,
                ),
            },
        )

        self.assertEqual(state.inning, 3)
        self.assertEqual(state.half, HalfInning.BOTTOM)

    def test_state_from_samples_ignores_low_confidence_scorebug_reads(self):
        # A pregame speck OCR'd as "7" at near-zero confidence must not
        # become an inning (it would smooth into a phantom across the gap).
        state = state_from_samples(
            600.0,
            {
                "inning": OCRSample(600.0, "inning", "7", normalized_text="7", confidence=0.01),
                "left_score": OCRSample(
                    600.0, "left_score", "8", normalized_text="8", confidence=0.2
                ),
                "right_score": OCRSample(
                    600.0, "right_score", "3", normalized_text="3", confidence=0.9
                ),
            },
        )

        self.assertIsNone(state.inning)
        self.assertIsNone(state.away_score)
        self.assertEqual(state.home_score, 3)

    def test_state_from_samples_accepts_scorebug_reads_without_confidence(self):
        state = state_from_samples(
            600.0,
            {"inning": OCRSample(600.0, "inning", "5", normalized_text="5")},
        )

        self.assertEqual(state.inning, 5)

    def test_state_from_samples_blanks_scorebug_values_during_pregame(self):
        state = state_from_samples(
            300.0,
            {
                "game_status": OCRSample(
                    300.0, "game_status", "GAME STARTING SOON", normalized_text="GAME STARTING SOON"
                ),
                "inning": OCRSample(300.0, "inning", "7", normalized_text="7", confidence=0.9),
                "left_score": OCRSample(
                    300.0, "left_score", "8", normalized_text="8", confidence=0.9
                ),
                "right_score": OCRSample(
                    300.0, "right_score", "0", normalized_text="0", confidence=0.9
                ),
            },
        )

        self.assertEqual(state.metadata["game_status"], "pregame")
        self.assertIsNone(state.inning)
        self.assertIsNone(state.half)
        self.assertIsNone(state.away_score)
        self.assertIsNone(state.home_score)

    def test_state_from_samples_uses_up_arrow_when_text_has_no_half(self):
        state = state_from_samples(
            600.0,
            {
                "inning": OCRSample(
                    600.0,
                    "inning",
                    "5",
                    normalized_text="5",
                    source_detail=INNING_ARROW_UP,
                ),
            },
        )

        self.assertEqual(state.inning, 5)
        self.assertEqual(state.half, HalfInning.TOP)

    def test_state_from_samples_stores_game_status(self):
        state = state_from_samples(
            600.0,
            {
                "game_status": OCRSample(
                    600.0,
                    "game_status",
                    "FINAL",
                    normalized_text="FINAL",
                ),
            },
        )

        self.assertEqual(state.metadata["game_status"], "final")

    def test_state_from_samples_stores_pregame_status(self):
        state = state_from_samples(
            0.0,
            {
                "game_status": OCRSample(
                    0.0,
                    "game_status",
                    "GAM Soon NG",
                    normalized_text="GAM Soon NG",
                ),
            },
        )

        self.assertEqual(state.metadata["game_status"], "pregame")

    def test_state_from_samples_falls_back_to_lineup_batter_number(self):
        state = state_from_samples(
            600.0,
            {
                "batter_number": OCRSample(600.0, "batter_number", "26", normalized_text="26"),
            },
        )

        self.assertEqual(state.batter_number, "26")
        self.assertEqual(state.metadata["batter_number_source"], "lineup_number")

    def test_state_from_samples_prefers_active_lineup_strip_over_static_batter_number(self):
        state = state_from_samples(
            600.0,
            {
                "lineup_strip": OCRSample(
                    600.0,
                    "lineup_strip",
                    "5",
                    normalized_text="5",
                    source_detail="lineup_highlight",
                ),
                "batter_number": OCRSample(600.0, "batter_number", "213", normalized_text="213"),
            },
        )

        self.assertEqual(state.batter_number, "5")
        self.assertEqual(state.metadata["batter_number_source"], "lineup_strip")
        self.assertEqual(state.metadata["lineup_strip_number"], "5")
        self.assertEqual(state.metadata["lineup_batter_number"], "213")
        self.assertEqual(state.metadata["lineup_strip_confidence"], "lineup_highlight")

    def test_state_from_samples_stores_lineup_strip_confidence_in_metadata(self):
        state = state_from_samples(
            600.0,
            {
                "lineup_strip": OCRSample(
                    600.0,
                    "lineup_strip",
                    "15",
                    normalized_text="15",
                    source_detail="lineup_full_strip",
                ),
            },
        )

        self.assertEqual(state.metadata["lineup_strip_confidence"], "lineup_full_strip")

    def test_state_from_samples_prefers_batter_card_over_lineup_number(self):
        state = state_from_samples(
            600.0,
            {
                "batter_card_number": OCRSample(
                    600.0,
                    "batter_card_number",
                    "#15",
                    normalized_text="#15",
                ),
                "batter_number": OCRSample(600.0, "batter_number", "18", normalized_text="18"),
            },
        )

        self.assertEqual(state.batter_number, "15")
        self.assertEqual(state.metadata["batter_number_source"], "batter_card")
        self.assertEqual(
            state.metadata["batter_number_disagreement"],
            "batter_card=15 lineup=18",
        )

    def test_state_from_samples_uses_active_lineup_number_for_disagreement(self):
        state = state_from_samples(
            600.0,
            {
                "batter_card_number": OCRSample(
                    600.0,
                    "batter_card_number",
                    "#13",
                    normalized_text="#13",
                ),
                "lineup_strip": OCRSample(600.0, "lineup_strip", "2", normalized_text="2"),
                "batter_number": OCRSample(600.0, "batter_number", "213", normalized_text="213"),
            },
        )

        self.assertEqual(
            state.metadata["batter_number_disagreement"],
            "batter_card=13 lineup=2",
        )

    def test_parse_states_smooths_missing_inning_from_neighbors(self):
        states = parse_states(
            [
                OCRSample(600.0, "inning", "o", normalized_text="o"),
                OCRSample(600.0, "count", "0-0", normalized_text="0-0"),
                OCRSample(605.0, "inning", "o1", normalized_text="o1"),
                OCRSample(605.0, "count", "0-0", normalized_text="0-0"),
            ]
        )

        self.assertEqual(states[0].inning, 1)
        self.assertEqual(states[0].half, HalfInning.TOP)

    def test_smooth_states_fills_missing_half_from_previous(self):
        states = parse_states(
            [
                OCRSample(600.0, "inning", "o1", normalized_text="o1"),
                OCRSample(605.0, "inning", "1", normalized_text="1"),
            ]
        )

        self.assertEqual(states[1].half, HalfInning.TOP)

    def test_smooth_states_treats_inning_advance_as_top_when_half_missing(self):
        states = parse_states(
            [
                OCRSample(600.0, "inning", "71", normalized_text="71"),
                OCRSample(605.0, "inning", "2", normalized_text="2"),
            ]
        )

        self.assertEqual(states[0].half, HalfInning.BOTTOM)
        self.assertEqual(states[1].inning, 2)
        self.assertEqual(states[1].half, HalfInning.TOP)

    def test_smooth_states_does_not_mutate_input_states(self):
        original_states = [
            OverlayState(600.0, inning=None, half=HalfInning.TOP),
            OverlayState(605.0, inning=1, half=HalfInning.TOP),
        ]

        smoothed = smooth_states(original_states)

        self.assertIsNone(original_states[0].inning)
        self.assertEqual(original_states[0].half, HalfInning.TOP)
        self.assertEqual(smoothed[0].inning, 1)
        self.assertEqual(smoothed[0].half, HalfInning.TOP)
        self.assertIsNot(smoothed[0], original_states[0])

    def test_overlay_state_is_immutable(self):
        state = OverlayState(600.0, inning=1, half=HalfInning.TOP)

        with self.assertRaises(FrozenInstanceError):
            state.inning = 2

    def test_smooth_states_rejects_an_isolated_half_flip(self):
        """One flipped sample inside a settled half-inning is OCR noise.

        Left in, it splits the half-inning chapter in two and — with the
        batting-half filter on — deletes whichever at-bats landed on it.
        """

        states = [
            OverlayState(600.0 + 5.0 * index, inning=3, half=HalfInning.TOP)
            for index in range(7)
        ]
        states[3] = OverlayState(615.0, inning=3, half=HalfInning.BOTTOM)

        smoothed = smooth_states(states)

        self.assertEqual([state.half for state in smoothed], [HalfInning.TOP] * 7)

    def test_smooth_states_keeps_a_real_half_inning_change(self):
        """The genuine top-to-bottom change inside one inning must survive."""

        halves = [HalfInning.TOP] * 6 + [HalfInning.BOTTOM] * 6
        states = [
            OverlayState(600.0 + 5.0 * index, inning=3, half=half)
            for index, half in enumerate(halves)
        ]

        smoothed = smooth_states(states)

        self.assertEqual([state.half for state in smoothed], halves)

    def test_smooth_states_does_not_vote_across_an_inning_change(self):
        """A short trailing half is not outvoted by the next inning's samples.

        The window is wide enough to straddle an inning boundary, so without
        the same-inning restriction the incoming inning's leadoff reads join
        the vote and flip the tail of the outgoing one — erasing a
        half-inning, and every at-bat in it, which is the loss the half vote
        exists to prevent. Both ``Bottom 3`` samples here sit inside a window
        that holds three ``TOP`` reads, so the assertion only holds while the
        restriction does.
        """

        sequence = [
            (3, HalfInning.TOP),
            (3, HalfInning.TOP),
            (3, HalfInning.BOTTOM),
            (3, HalfInning.BOTTOM),
            (4, HalfInning.TOP),
            (4, HalfInning.TOP),
            (4, HalfInning.TOP),
        ]
        states = [
            OverlayState(600.0 + 5.0 * index, inning=inning, half=half)
            for index, (inning, half) in enumerate(sequence)
        ]

        smoothed = smooth_states(states)

        self.assertEqual([(state.inning, state.half) for state in smoothed], sequence)

    def test_smooth_states_does_not_vote_across_a_capture_gap(self):
        """Samples on the far side of a capture hole do not join the vote.

        A stream interruption puts unrelated samples inside the window's
        sample radius while they are minutes away in time. Here the lone
        ``Bottom 5`` read is the only sample in its own time window, so
        without the gap filter the two post-gap ``Top 5`` reads outvote it
        2-to-1 and the half-inning disappears across the interruption.
        """

        states = [
            OverlayState(600.0, inning=5, half=HalfInning.BOTTOM),
            OverlayState(1000.0, inning=5, half=HalfInning.TOP),
            OverlayState(1005.0, inning=5, half=HalfInning.TOP),
        ]

        smoothed = smooth_states(states)

        self.assertEqual(
            [state.half for state in smoothed],
            [HalfInning.BOTTOM, HalfInning.TOP, HalfInning.TOP],
        )

    def test_smooth_states_never_invents_a_half(self):
        """Unknown stays unknown through the majority pass.

        Gap filling may still supply a neighbouring value afterwards, but the
        vote itself must not manufacture one where nothing was read — here
        there is no neighbouring inning to fill from either.
        """

        states = [
            OverlayState(600.0, inning=None, half=None),
            OverlayState(605.0, inning=None, half=None),
        ]

        smoothed = smooth_states(states)

        self.assertEqual([state.half for state in smoothed], [None, None])

    def test_smooth_states_leaves_an_even_split_alone(self):
        """A tie keeps the observed read, so the pass stays deterministic.

        A window that ties is a window straddling a real boundary; picking a
        winner there would move the boundary, and picking it by set-iteration
        order would make the pipeline non-reproducible.
        """

        halves = [HalfInning.TOP, HalfInning.TOP, HalfInning.BOTTOM, HalfInning.BOTTOM]
        states = [
            OverlayState(600.0 + 5.0 * index, inning=3, half=half)
            for index, half in enumerate(halves)
        ]

        first = smooth_states(states)
        second = smooth_states(states)

        self.assertEqual([state.half for state in first], halves)
        self.assertEqual([state.half for state in first], [state.half for state in second])

    def test_smooth_states_fills_short_middle_gap_from_previous_state(self):
        original_states = [
            OverlayState(600.0, inning=1, half=HalfInning.TOP),
            OverlayState(605.0, inning=None, half=None),
            OverlayState(610.0, inning=1, half=HalfInning.TOP),
        ]

        smoothed = smooth_states(original_states)

        self.assertEqual(
            [(state.inning, state.half) for state in smoothed],
            [
                (1, HalfInning.TOP),
                (1, HalfInning.TOP),
                (1, HalfInning.TOP),
            ],
        )
        self.assertIsNone(original_states[1].inning)
        self.assertIsNone(original_states[1].half)

    def test_smooth_states_fills_leading_gap_from_next_known_state(self):
        smoothed = smooth_states(
            [
                OverlayState(600.0, inning=None, half=None),
                OverlayState(605.0, inning=2, half=HalfInning.BOTTOM),
            ]
        )

        self.assertEqual(smoothed[0].inning, 2)
        self.assertEqual(smoothed[0].half, HalfInning.BOTTOM)

    def test_smooth_states_preserves_long_leading_gap_from_next_known_state(self):
        smoothed = smooth_states(
            [
                OverlayState(600.0, inning=None, half=None),
                OverlayState(1040.0, inning=None, half=None),
                OverlayState(1080.0, inning=1, half=HalfInning.TOP),
            ]
        )

        self.assertEqual(
            [(state.inning, state.half) for state in smoothed],
            [(None, None), (None, None), (1, HalfInning.TOP)],
        )

    def test_smooth_states_preserves_unknowns_when_no_neighbor_state_exists(self):
        smoothed = smooth_states(
            [
                OverlayState(600.0, inning=None, half=None),
                OverlayState(605.0, inning=None, half=None),
            ]
        )

        self.assertEqual(
            [(state.inning, state.half) for state in smoothed],
            [(None, None), (None, None)],
        )

    def test_parse_samples_file_writes_states_jsonl(self):
        with tempfile.TemporaryDirectory() as directory:
            samples_path = Path(directory) / "samples.jsonl"
            write_jsonl(
                samples_path,
                [
                    OCRSample(600.0, "count", "0-0", normalized_text="0-0"),
                    OCRSample(600.0, "batter_card_number", "#22", normalized_text="#22"),
                ],
            )

            result = parse_samples_file(samples_path)

            self.assertEqual(result.state_count, 1)
            self.assertTrue(result.output_path.exists())

    def test_ocr_sample_serializes_source_detail(self):
        with tempfile.TemporaryDirectory() as directory:
            samples_path = Path(directory) / "samples.jsonl"

            write_jsonl(
                samples_path,
                [
                    OCRSample(
                        600.0,
                        "lineup_strip",
                        "26\n",
                        normalized_text="26",
                        source_detail="lineup_highlight",
                    )
                ],
            )

            text = samples_path.read_text(encoding="utf-8")

        self.assertIn('"source_detail": "lineup_highlight"', text)

    def test_load_ocr_samples_reads_source_detail(self):
        with tempfile.TemporaryDirectory() as directory:
            samples_path = Path(directory) / "samples.jsonl"
            samples_path.write_text(
                '{"timestamp_seconds": 600, "field_name": "lineup_strip", '
                '"raw_text": "26", "normalized_text": "26", '
                '"source_detail": "lineup_highlight"}\n',
                encoding="utf-8",
            )

            samples = load_ocr_samples(samples_path)

        self.assertEqual(samples[0].source_detail, "lineup_highlight")

    def test_load_ocr_samples_defaults_source_detail_to_none_for_old_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            samples_path = Path(directory) / "samples.jsonl"
            samples_path.write_text(
                '{"timestamp_seconds": 600, "field_name": "lineup_strip", '
                '"raw_text": "26", "normalized_text": "26"}\n',
                encoding="utf-8",
            )

            samples = load_ocr_samples(samples_path)

        self.assertIsNone(samples[0].source_detail)


class SmoothScoreSequenceTests(unittest.TestCase):
    """Scores are cumulative: unconfirmed decreases and wild jumps are OCR noise."""

    def _smooth(self, values):
        from sidelinehd_extractor.state import _smooth_score_sequence

        return _smooth_score_sequence(values)

    def test_flip_flop_from_dropped_leading_digit_holds_established_score(self):
        # The live-fire failure: "12" alternating with "2" every few reads.
        self.assertEqual(
            self._smooth([12, 2, 12, 2, 12, 2, 12]),
            [12, 12, 12, 12, 12, 12, 12],
        )

    def test_single_stray_decrease_at_a_boundary_is_suppressed(self):
        self.assertEqual(self._smooth([12, 12, 2, 12, 12]), [12, 12, 12, 12, 12])

    def test_stray_decrease_at_end_of_sequence_is_suppressed(self):
        self.assertEqual(self._smooth([12, 12, 2]), [12, 12, 12])

    def test_operator_correction_persisting_is_accepted(self):
        self.assertEqual(self._smooth([3, 3, 2, 2, 2, 2]), [3, 3, 2, 2, 2, 2])

    def test_normal_increments_pass_through(self):
        self.assertEqual(self._smooth([0, 1, 1, 3, 3, 4]), [0, 1, 1, 3, 3, 4])

    def test_none_gaps_stay_none_and_do_not_break_confirmation(self):
        self.assertEqual(
            self._smooth([7, None, None, 12, None, 12, 12]),
            [7, None, None, 12, None, 12, 12],
        )

    def test_unconfirmed_wild_jump_is_suppressed(self):
        self.assertEqual(self._smooth([6, 65, 7, 7]), [6, 6, 7, 7])

    def test_confirmed_large_jump_after_gap_is_accepted(self):
        # A real rally read back after a long unreadable stretch.
        self.assertEqual(self._smooth([7, None, 12, 12, 13]), [7, None, 12, 12, 13])

    def test_bad_initial_read_is_recovered_by_confirmed_decrease(self):
        self.assertEqual(self._smooth([8, 0, 0, 0, 1]), [8, 0, 0, 0, 1])

    def test_all_none_passes_through(self):
        self.assertEqual(self._smooth([None, None]), [None, None])

    def test_smooth_states_applies_score_guard(self):
        from sidelinehd_extractor.models import OverlayState
        from sidelinehd_extractor.state import smooth_states

        states = [
            OverlayState(timestamp_seconds=float(index * 5), away_score=score, home_score=6)
            for index, score in enumerate([12, 2, 12])
        ]
        smoothed = smooth_states(states)
        self.assertEqual([state.away_score for state in smoothed], [12, 12, 12])
        self.assertEqual([state.home_score for state in smoothed], [6, 6, 6])


if __name__ == "__main__":
    unittest.main()
