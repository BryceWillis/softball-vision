import json
import tempfile
import unittest
from pathlib import Path

from sidelinehd_extractor.config import load_overlay_template, load_roster


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


if __name__ == "__main__":
    unittest.main()
