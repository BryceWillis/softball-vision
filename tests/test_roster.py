import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from sidelinehd_extractor.config import load_roster, write_project_config, ProjectConfig
from sidelinehd_extractor.roster import (
    UnknownRoster,
    configured_roster_path,
    default_roster_path,
    existing_roster_path,
    is_configured_default,
    parse_team_list,
    parse_team_list_line,
    roster_csv_path,
    rosters_directory,
    write_roster_csv,
)


@contextmanager
def _working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


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


class RosterSlugHelperTests(unittest.TestCase):
    """The slug/default helpers the web routes and CLI admin commands share (70e)."""

    def test_roster_csv_path_resolves_a_valid_slug_under_rosters(self):
        self.assertEqual(roster_csv_path("blue_thunder"), Path("rosters") / "blue_thunder.csv")

    def test_roster_csv_path_rejects_slugs_slugify_would_not_produce(self):
        # The traversal guard both surfaces rely on: anything but [a-z0-9_].
        for bad in ("../roster", "foo/bar", "/etc/passwd", "Blue Thunder", "team.csv", ""):
            with self.assertRaises(UnknownRoster):
                roster_csv_path(bad)

    def test_existing_roster_path_raises_for_a_valid_but_missing_slug(self):
        with tempfile.TemporaryDirectory() as directory:
            with _working_directory(Path(directory)):
                with self.assertRaises(UnknownRoster):
                    existing_roster_path("no_such_team")

    def test_existing_roster_path_returns_a_present_roster(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with _working_directory(root):
                path = default_roster_path("Blue Thunder")
                write_roster_csv(parse_team_list("#7 Zoe H.\n", team_name="Blue Thunder"), path)
                self.assertEqual(existing_roster_path("blue_thunder"), path)

    def test_configured_default_tracks_the_config_roster(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with _working_directory(root):
                path = default_roster_path("Blue Thunder")
                write_roster_csv(parse_team_list("#7 Zoe H.\n", team_name="Blue Thunder"), path)
                other = default_roster_path("Red Storm")
                write_roster_csv(parse_team_list("#3 Emma B.\n", team_name="Red Storm"), other)

                # No config yet: nothing is the default.
                self.assertIsNone(configured_roster_path())
                self.assertFalse(is_configured_default(path))

                write_project_config(ProjectConfig(roster=path, team_name="Blue Thunder"), cwd=root)
                self.assertEqual(configured_roster_path(), path)
                self.assertTrue(is_configured_default(path))
                self.assertFalse(is_configured_default(other))


class RosterBaseResolutionTests(unittest.TestCase):
    """M7 / 70f: the ``rosters/`` directory resolves against an explicit base.

    ``base=None`` keeps the CWD-relative path the CLI has always produced, byte
    for byte; a supplied base resolves ``rosters/`` under it so the desktop app
    works without an ``os.chdir``.
    """

    def test_rosters_directory_defaults_to_the_cwd_relative_name(self):
        # Byte-identical to the pre-70f literal both surfaces resolved at open.
        self.assertEqual(rosters_directory(), Path("rosters"))
        self.assertEqual(rosters_directory(None), Path("rosters"))

    def test_rosters_directory_resolves_under_an_explicit_base(self):
        base = Path("/tmp/data-root")
        self.assertEqual(rosters_directory(base), base / "rosters")

    def test_roster_helpers_thread_the_base_through(self):
        base = Path("/tmp/data-root")
        self.assertEqual(roster_csv_path("blue_thunder"), Path("rosters") / "blue_thunder.csv")
        self.assertEqual(
            roster_csv_path("blue_thunder", base=base),
            base / "rosters" / "blue_thunder.csv",
        )
        self.assertEqual(
            default_roster_path("Blue Thunder", base=base),
            base / "rosters" / "blue_thunder.csv",
        )

    def test_slug_guard_holds_regardless_of_base(self):
        # A base must never weaken the traversal guard both surfaces share.
        for bad in ("../roster", "foo/bar", "/etc/passwd", "Blue Thunder"):
            with self.assertRaises(UnknownRoster):
                roster_csv_path(bad, base=Path("/tmp/data-root"))

    def test_explicit_base_round_trips_with_cwd_elsewhere(self):
        # The regression guard 70f names: exercise the roster helpers from a
        # process whose CWD is *not* the data dir, against an explicit base.
        with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as elsewhere:
            root = Path(data_dir)
            with _working_directory(Path(elsewhere)):
                path = default_roster_path("Blue Thunder", base=root)
                write_roster_csv(
                    parse_team_list("#7 Zoe H.\n", team_name="Blue Thunder"), path
                )
                # Resolves under the base even though the CWD is elsewhere...
                self.assertEqual(existing_roster_path("blue_thunder", base=root), path)
                self.assertEqual(load_roster(path).name_for_number("7"), "Zoe H.")
                # ...and the CWD-relative lookup (no base) does not find it.
                with self.assertRaises(UnknownRoster):
                    existing_roster_path("blue_thunder")


if __name__ == "__main__":
    unittest.main()
