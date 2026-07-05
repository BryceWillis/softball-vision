import tempfile
import unittest
from pathlib import Path

from sidelinehd_extractor.config import load_roster
from sidelinehd_extractor.roster import (
    default_roster_path,
    parse_team_list,
    parse_team_list_line,
    write_roster_csv,
)


class RosterBuilderTests(unittest.TestCase):
    def test_parse_team_list_line(self):
        player = parse_team_list_line("#26 Amelia V.")

        self.assertEqual(player.number, "26")
        self.assertEqual(player.full_name, "Amelia V.")
        self.assertEqual(player.preferred_name, "Amelia")
        self.assertEqual(player.display_name, "Amelia V.")
        self.assertEqual(player.aliases, ["Amelia"])

    def test_parse_team_list_accepts_bullets_and_plain_numbers(self):
        roster = parse_team_list(
            """
            - #2 Emma B.
            * 3 Olivia M.
            10 Mia K.
            """,
            team_name="Stars",
        )

        self.assertEqual(roster.team_name, "Stars")
        self.assertEqual([player.number for player in roster.players], ["2", "3", "10"])
        self.assertEqual([player.full_name for player in roster.players], [
            "Emma B.",
            "Olivia M.",
            "Mia K.",
        ])

    def test_parse_team_list_rejects_duplicate_numbers(self):
        with self.assertRaises(ValueError):
            parse_team_list("#2 Emma B.\n#2 Other Player")

    def test_write_roster_csv_round_trips_with_loader(self):
        roster = parse_team_list("#22 Maya R.\n#26 Amelia V.", team_name="Stars")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roster.csv"
            result = write_roster_csv(roster, path)
            loaded = load_roster(path, team_name="Stars")

        self.assertEqual(result.player_count, 2)
        self.assertEqual(loaded.name_for_number("22"), "Maya R.")
        self.assertEqual(loaded.number_for_name("Amelia"), "26")

    def test_team_name_round_trips_through_csv(self):
        # Item 52: the pretty team name survives write -> load without the
        # caller re-supplying it (previously it degraded to the file stem).
        roster = parse_team_list("#22 Maya R.", team_name="St. Mary's 12U")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "st_mary_s_12u.csv"
            write_roster_csv(roster, path)
            loaded = load_roster(path)
            content = path.read_text(encoding="utf-8")

        self.assertEqual(loaded.team_name, "St. Mary's 12U")
        self.assertTrue(content.startswith("# team_name: St. Mary's 12U"))
        # Column contract unchanged after the comment line.
        self.assertIn("number,full_name,preferred_name,display_name,aliases", content)

    def test_explicit_team_name_overrides_csv_header(self):
        roster = parse_team_list("#22 Maya R.", team_name="St. Mary's 12U")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roster.csv"
            write_roster_csv(roster, path)
            loaded = load_roster(path, team_name="Override 10U")

        self.assertEqual(loaded.team_name, "Override 10U")

    def test_pre_item_52_csv_without_comment_falls_back_to_stem(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "blue_thunder.csv"
            path.write_text("number,full_name\n22,Maya R.\n", encoding="utf-8")
            loaded = load_roster(path)

        self.assertEqual(loaded.team_name, "blue_thunder")
        self.assertEqual(loaded.name_for_number("22"), "Maya R.")

    def test_default_roster_path_slugifies_team_name(self):
        self.assertEqual(
            default_roster_path("Smash It Sports 12U"),
            Path("rosters") / "smash_it_sports_12u.csv",
        )


if __name__ == "__main__":
    unittest.main()
