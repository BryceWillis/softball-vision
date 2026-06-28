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
