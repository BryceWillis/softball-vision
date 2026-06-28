import json
import tempfile
import unittest
from pathlib import Path

from sidelinehd_extractor.naming import game_name_for_run, game_slug_for_run, slugify, strip_run_timestamp


class NamingTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Smash It Sports 12U @ FLX ICE"), "smash_it_sports_12u_flx_ice")

    def test_strip_run_timestamp(self):
        self.assertEqual(strip_run_timestamp("game-name-20260627-142836"), "game-name")

    def test_game_name_for_run_uses_manifest_video_stem(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            run_dir.mkdir()
            (run_dir / "manifest.json").write_text(
                json.dumps({"video": {"path": "videos/Smash_It_@_FLX_ICE.mp4"}}),
                encoding="utf-8",
            )

            self.assertEqual(game_name_for_run(run_dir), "Smash_It_@_FLX_ICE")
            self.assertEqual(game_slug_for_run(run_dir), "smash_it_flx_ice")

    def test_game_name_for_run_prefers_info_json_title(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            video_path = root / "videos" / "downloaded_name.mp4"
            run_dir.mkdir()
            video_path.parent.mkdir()
            video_path.with_suffix(".info.json").write_text(
                json.dumps({"title": "Smash It Sports 12U @ FLX ICE 12U (2026.06.24)"}),
                encoding="utf-8",
            )
            (run_dir / "manifest.json").write_text(
                json.dumps({"video": {"path": str(video_path)}}),
                encoding="utf-8",
            )

            self.assertEqual(
                game_name_for_run(run_dir),
                "Smash It Sports 12U @ FLX ICE 12U (2026.06.24)",
            )
            self.assertEqual(
                game_slug_for_run(run_dir),
                "smash_it_sports_12u_flx_ice_12u_2026_06_24",
            )


if __name__ == "__main__":
    unittest.main()
