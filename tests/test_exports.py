import unittest

from sidelinehd_extractor.exports import (
    PROJECT_CREDIT,
    export_at_bat_comment,
    export_youtube_chapters,
    format_timestamp,
)
from sidelinehd_extractor.models import Event, EventType


class FormatTimestampTests(unittest.TestCase):
    def test_format_timestamp(self):
        cases = [
            (0, "0:00"),
            (4.9, "0:04"),
            (65, "1:05"),
            (3599.9, "59:59"),
            (3600, "1:00:00"),
            (3661, "1:01:01"),
        ]

        for seconds, expected in cases:
            with self.subTest(seconds=seconds):
                self.assertEqual(format_timestamp(seconds), expected)

    def test_format_timestamp_rejects_negative_seconds(self):
        with self.assertRaises(ValueError):
            format_timestamp(-1)

    def test_export_youtube_chapters_adds_intro_when_first_chapter_is_later(self):
        text = export_youtube_chapters([
            Event(EventType.HALF_INNING_START, 600, "Top 1"),
            Event(EventType.HALF_INNING_START, 1200, "Top 2"),
        ], include_credit=False)

        self.assertEqual(text, "0:00 Pregame\n10:00 Top 1\n20:00 Top 2")

    def test_export_youtube_chapters_does_not_duplicate_zero_chapter(self):
        text = export_youtube_chapters([
            Event(EventType.HALF_INNING_START, 0, "Top 1"),
            Event(EventType.HALF_INNING_START, 600, "Top 2"),
        ], include_credit=False)

        self.assertEqual(text, "0:00 Top 1\n10:00 Top 2")

    def test_export_youtube_chapters_allows_intro_override(self):
        text = export_youtube_chapters(
            [Event(EventType.HALF_INNING_START, 600, "Top 1")],
            intro_label="Warmups",
            include_credit=False,
        )

        self.assertEqual(text, "0:00 Warmups\n10:00 Top 1")

    def test_export_youtube_chapters_can_skip_intro(self):
        text = export_youtube_chapters(
            [Event(EventType.HALF_INNING_START, 600, "Top 1")],
            include_intro=False,
            include_credit=False,
        )

        self.assertEqual(text, "10:00 Top 1")

    def test_export_youtube_chapters_appends_score_when_present(self):
        text = export_youtube_chapters(
            [
                Event(
                    EventType.HALF_INNING_START,
                    600,
                    "Top 1",
                    metadata={"away_score": 2, "home_score": 1},
                )
            ],
            include_credit=False,
        )

        self.assertEqual(text, "0:00 Pregame\n10:00 Top 1 (2-1)")

    def test_export_youtube_chapters_can_omit_score(self):
        text = export_youtube_chapters(
            [
                Event(
                    EventType.HALF_INNING_START,
                    600,
                    "Top 1",
                    metadata={"away_score": 2, "home_score": 1},
                )
            ],
            include_score=False,
            include_credit=False,
        )

        self.assertEqual(text, "0:00 Pregame\n10:00 Top 1")

    def test_export_youtube_chapters_omits_incomplete_score(self):
        text = export_youtube_chapters(
            [
                Event(
                    EventType.HALF_INNING_START,
                    600,
                    "Top 1",
                    metadata={"away_score": 2, "home_score": None},
                )
            ],
            include_credit=False,
        )

        self.assertEqual(text, "0:00 Pregame\n10:00 Top 1")

    def test_export_youtube_chapters_includes_final_marker_with_score(self):
        text = export_youtube_chapters(
            [
                Event(EventType.HALF_INNING_START, 0, "Top 1"),
                Event(
                    EventType.GAME_FINAL,
                    3600,
                    "Final",
                    metadata={"away_score": 8, "home_score": 6},
                ),
            ],
            include_credit=False,
        )

        self.assertEqual(text, "0:00 Top 1\n1:00:00 Final (8-6)")

    def test_export_youtube_chapters_can_omit_final_score(self):
        text = export_youtube_chapters(
            [
                Event(
                    EventType.GAME_FINAL,
                    3600,
                    "Final",
                    metadata={"away_score": 8, "home_score": 6},
                )
            ],
            include_score=False,
            include_credit=False,
        )

        self.assertEqual(text, "0:00 Pregame\n1:00:00 Final")

    def test_export_youtube_chapters_omits_incomplete_final_score(self):
        text = export_youtube_chapters(
            [
                Event(
                    EventType.GAME_FINAL,
                    3600,
                    "Final",
                    metadata={"away_score": None, "home_score": None},
                )
            ],
            include_credit=False,
        )

        self.assertEqual(text, "0:00 Pregame\n1:00:00 Final")

    def test_export_youtube_chapters_collapses_a_final_onto_the_half_inning_it_lands_on(self):
        # CR-117: YouTube renders no chapters at all when two share a
        # timestamp, so the collision costs the whole list rather than a line.
        text = export_youtube_chapters(
            [
                Event(EventType.HALF_INNING_START, 600, "Top 1"),
                Event(
                    EventType.HALF_INNING_START,
                    900,
                    "Bottom 1",
                    metadata={"away_score": 3, "home_score": 1},
                ),
                Event(
                    EventType.GAME_FINAL,
                    900,
                    "Final",
                    metadata={"away_score": 3, "home_score": 1},
                ),
            ],
            include_credit=False,
        )

        self.assertEqual(text, "0:00 Pregame\n10:00 Top 1\n15:00 Final (3-1)")

    def test_export_youtube_chapters_collapses_chapters_that_only_collide_once_formatted(self):
        # format_timestamp truncates, so these differ as floats and collide as
        # strings. The comparison has to be on the rendered stamp.
        text = export_youtube_chapters(
            [
                Event(EventType.HALF_INNING_START, 900.2, "Bottom 1"),
                Event(EventType.GAME_FINAL, 900.9, "Final"),
            ],
            include_credit=False,
        )

        self.assertEqual(text, "0:00 Pregame\n15:00 Final")

    def test_export_youtube_chapters_prefers_the_terminal_chapter_whatever_the_order(self):
        # Terminality decides, not position: the final wins even when it is
        # the one that arrives first.
        text = export_youtube_chapters(
            [
                Event(EventType.GAME_FINAL, 900, "Final"),
                Event(EventType.HALF_INNING_START, 900, "Bottom 1"),
            ],
            include_credit=False,
        )

        self.assertEqual(text, "0:00 Pregame\n15:00 Final")

    def test_export_youtube_chapters_collapses_a_half_inning_onto_an_inning_start(self):
        text = export_youtube_chapters(
            [
                Event(EventType.INNING_START, 900, "Inning 2"),
                Event(EventType.HALF_INNING_START, 900, "Top 2"),
            ],
            include_credit=False,
        )

        self.assertEqual(text, "0:00 Pregame\n15:00 Top 2")

    def test_export_youtube_chapters_keeps_the_later_of_two_equally_terminal_chapters(self):
        # Same rule, same reason: the first chapter has no duration to offer.
        text = export_youtube_chapters(
            [
                Event(EventType.HALF_INNING_START, 900.1, "Top 2"),
                Event(EventType.HALF_INNING_START, 900.8, "Bottom 2"),
            ],
            include_credit=False,
        )

        self.assertEqual(text, "0:00 Pregame\n15:00 Bottom 2")

    def test_export_youtube_chapters_keeps_chapters_five_seconds_apart(self):
        # The control. One local run exports a legitimate 5.0s gap; only exact
        # collisions collapse, and YouTube's 10s rule is left alone.
        text = export_youtube_chapters(
            [
                Event(EventType.HALF_INNING_START, 900, "Bottom 1"),
                Event(EventType.GAME_FINAL, 905, "Final"),
            ],
            include_credit=False,
        )

        self.assertEqual(text, "0:00 Pregame\n15:00 Bottom 1\n15:05 Final")

    def test_export_youtube_chapters_skips_the_intro_when_the_first_chapter_renders_at_zero(self):
        # `--start 0.4` puts the first chapter under a second, where it renders
        # as 0:00 and the intro would collide with it. The guard was a float
        # comparison; the collision is on the rendered stamp.
        text = export_youtube_chapters(
            [
                Event(EventType.HALF_INNING_START, 0.4, "Top 1"),
                Event(EventType.HALF_INNING_START, 600, "Bottom 1"),
            ],
            include_credit=False,
        )

        self.assertEqual(text, "0:00 Top 1\n10:00 Bottom 1")

    def test_export_at_bat_comment_groups_by_inning(self):
        text = export_at_bat_comment([
            Event(EventType.HALF_INNING_START, 590, "Top 1", inning=1),
            Event(EventType.AT_BAT_START, 600, "Maya R. (#22)", inning=1),
            Event(EventType.AT_BAT_START, 675, "Amelia V. (#26)", inning=1),
            Event(EventType.HALF_INNING_START, 1350, "Top 2", inning=2),
            Event(EventType.AT_BAT_START, 1360, "Olivia M. (#3)", inning=2),
        ], include_credit=False)

        self.assertEqual(
            text,
            "1st Inning\n"
            "10:00 Maya R. (#22)\n"
            "11:15 Amelia V. (#26)\n"
            "\n"
            "2nd Inning\n"
            "22:40 Olivia M. (#3)",
        )

    def test_export_at_bat_comment_prefers_current_chapter_inning_for_grouping(self):
        text = export_at_bat_comment([
            Event(EventType.HALF_INNING_START, 4900, "Top 6", inning=6),
            Event(EventType.AT_BAT_START, 5065, "Chloe W. (#12)", inning=2),
            Event(EventType.AT_BAT_START, 5145, "Stella H. (#24)", inning=6),
        ], include_credit=False)

        self.assertEqual(
            text,
            "6th Inning\n"
            "1:24:25 Chloe W. (#12)\n"
            "1:25:45 Stella H. (#24)",
        )

    def test_export_at_bat_comment_can_skip_inning_headers(self):
        text = export_at_bat_comment(
            [Event(EventType.AT_BAT_START, 600, "Maya R. (#22)", inning=1)],
            include_inning_headers=False,
            include_credit=False,
        )

        self.assertEqual(text, "10:00 Maya R. (#22)")

    def test_exports_include_project_credit_by_default(self):
        chapters = export_youtube_chapters([Event(EventType.HALF_INNING_START, 0, "Top 1")])
        at_bats = export_at_bat_comment([Event(EventType.AT_BAT_START, 600, "Maya R. (#22)", inning=1)])

        self.assertTrue(chapters.endswith(PROJECT_CREDIT))
        self.assertTrue(at_bats.endswith(PROJECT_CREDIT))
        self.assertIn("MIT License", PROJECT_CREDIT)
        self.assertIn("https://github.com/BryceWillis/softball-vision", PROJECT_CREDIT)


if __name__ == "__main__":
    unittest.main()
