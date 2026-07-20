import json
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

from sidelinehd_extractor.config import (
    BUILTIN_TEMPLATE_NAME,
    ProjectConfig,
    default_overlay_template,
    full_frame_overlay_template,
    load_overlay_template,
    load_project_config,
    load_project_config_values,
    load_roster,
    write_project_config,
)


class ConfigLoaderTests(unittest.TestCase):
    def test_load_overlay_template(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "template.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "sidelinehd_1080p",
                        "regions": {
                            "inning": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1}
                        },
                    }
                ),
                encoding="utf-8",
            )

            template = load_overlay_template(path)

        self.assertEqual(template.name, "sidelinehd_1080p")
        self.assertIn("inning", template.regions)
        self.assertEqual(template.regions["inning"].x, 0.1)

    def test_active_example_template_right_score_uses_calibrated_region(self):
        template = load_overlay_template(Path("examples/sidelinehd_640x360_active.example.json"))
        region = template.regions["right_score"]

        self.assertAlmostEqual(region.x, 0.580)
        self.assertAlmostEqual(region.y, 0.025)
        self.assertAlmostEqual(region.width, 0.050)
        self.assertAlmostEqual(region.height, 0.064)

    def test_default_overlay_template_is_the_packaged_sidelinehd_template(self):
        template = default_overlay_template()

        self.assertEqual(template.name, BUILTIN_TEMPLATE_NAME)
        for field_name in ("left_score", "right_score", "count", "inning", "batter_card"):
            self.assertIn(field_name, template.regions)
        self.assertNotIn("full_frame", template.regions)
        # The packaged copy must stay in sync with the calibrated example.
        example = load_overlay_template(
            Path("examples/sidelinehd_640x360_active.example.json")
        )
        self.assertEqual(set(template.regions), set(example.regions))
        for name, region in example.regions.items():
            self.assertEqual(template.regions[name], region)

    def test_full_frame_overlay_template_is_explicit_opt_in(self):
        template = full_frame_overlay_template()

        self.assertEqual(template.name, "full_frame")
        self.assertEqual(list(template.regions), ["full_frame"])
        self.assertEqual(template.regions["full_frame"].width, 1.0)

    def test_load_roster_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roster.csv"
            path.write_text(
                "number,full_name,preferred_name,display_name,aliases\n"
                "7,Jane Smith,Jane,Jane S.,Janie;J. Smith\n"
                "12,Sam Lee,Sam,,\n",
                encoding="utf-8",
            )

            roster = load_roster(path, team_name="Stars")

        self.assertEqual(roster.team_name, "Stars")
        self.assertEqual(roster.name_for_number("#7"), "Jane S.")
        self.assertEqual(roster.name_for_number(12), "Sam Lee")
        self.assertEqual(roster.number_for_name("Janie"), "7")
        self.assertEqual(roster.number_for_name("Jane S."), "7")
        self.assertEqual(roster.number_for_name("Jame Smith"), "7")

    def test_load_project_config_returns_empty_when_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            config = load_project_config(cwd=Path(directory))

        self.assertEqual(config, ProjectConfig())

    def test_load_project_config_reads_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            roster = root / "roster.csv"
            template = root / "template.json"
            roster.write_text("number,full_name\n22,Maya R.\n", encoding="utf-8")
            template.write_text('{"regions":{"inning":{"x":0,"y":0,"width":1,"height":1}}}', encoding="utf-8")
            (root / "sidelinehd.cfg").write_text(
                "[defaults]\n"
                "roster = roster.csv\n"
                "template = template.json\n"
                "team_name = Stars\n",
                encoding="utf-8",
            )

            config = load_project_config(cwd=root)

        self.assertEqual(config.roster, Path("roster.csv"))
        self.assertEqual(config.template, Path("template.json"))
        self.assertEqual(config.team_name, "Stars")

    def test_load_project_config_ignores_missing_section_and_unknown_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sidelinehd.cfg").write_text(
                "[other]\nunknown = value\n",
                encoding="utf-8",
            )

            config = load_project_config(cwd=root)

        self.assertEqual(config, ProjectConfig())

    def test_write_project_config_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            roster = root / "roster.csv"
            template = root / "template.json"
            roster.write_text("number,full_name\n22,Maya R.\n", encoding="utf-8")
            template.write_text('{"regions":{"inning":{"x":0,"y":0,"width":1,"height":1}}}', encoding="utf-8")

            write_project_config(
                ProjectConfig(
                    roster=Path("roster.csv"),
                    template=Path("template.json"),
                    team_name="Stars",
                ),
                cwd=root,
            )
            config = load_project_config(cwd=root)

        self.assertEqual(config.roster, Path("roster.csv"))
        self.assertEqual(config.template, Path("template.json"))
        self.assertEqual(config.team_name, "Stars")

    def test_load_project_config_values_includes_check_for_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sidelinehd.cfg").write_text(
                "[defaults]\ncheck_for_updates = false\n",
                encoding="utf-8",
            )

            values = load_project_config_values(cwd=root)

        self.assertEqual(values.get("check_for_updates"), "false")

    def test_write_project_config_preserves_unmanaged_keys(self):
        """Item 67d: a roster update (CLI setup or the web UI's set-default)
        must not silently drop a hand-written check_for_updates opt-out."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sidelinehd.cfg").write_text(
                "[defaults]\n"
                "team_name = Old Name\n"
                "check_for_updates = false\n",
                encoding="utf-8",
            )

            write_project_config(
                ProjectConfig(roster=Path("roster.csv"), team_name="Stars"),
                cwd=root,
            )
            values = load_project_config_values(cwd=root)

        self.assertEqual(values.get("roster"), "roster.csv")
        self.assertEqual(values.get("team_name"), "Stars")  # managed key replaced
        self.assertEqual(values.get("check_for_updates"), "false")  # preserved

    def test_load_project_config_warns_and_skips_missing_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sidelinehd.cfg").write_text(
                "[defaults]\n"
                "roster = missing-roster.csv\n"
                "template = missing-template.json\n"
                "team_name = Stars\n",
                encoding="utf-8",
            )
            stderr = StringIO()

            with redirect_stderr(stderr):
                config = load_project_config(cwd=root)

        self.assertIsNone(config.roster)
        self.assertIsNone(config.template)
        self.assertEqual(config.team_name, "Stars")
        self.assertIn("missing-roster.csv", stderr.getvalue())
        self.assertIn("missing-template.json", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
