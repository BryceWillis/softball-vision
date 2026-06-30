import tempfile
import unittest
from pathlib import Path

from sidelinehd_extractor.publish import default_publish_kit_path, render_publish_kit, write_publish_kit


class PublishTests(unittest.TestCase):
    def test_render_publish_kit_includes_chapters_comment_and_checklist(self):
        text = render_publish_kit(
            game_name="Smash It Sports @ FLX ICE",
            chapters_text="0:00 Pregame\n10:00 Top 1\n",
            at_bats_text="10:00 Maya R. (#22)\n",
        )

        self.assertIn("# YouTube Paste Kit: Smash It Sports @ FLX ICE", text)
        self.assertIn("## Description Chapters", text)
        self.assertIn("0:00 Pregame", text)
        self.assertIn("## Pinned Comment", text)
        self.assertIn("10:00 Maya R. (#22)", text)
        self.assertIn("- [ ] At-bat comment pinned", text)

    def test_default_publish_kit_path_uses_game_slug_folder(self):
        path = default_publish_kit_path(
            Path("runs/game-20260627-142836"),
            output_dir=Path("scratch/publish"),
        )

        self.assertEqual(path, Path("scratch/publish/game/youtube_paste_kit.md"))

    def test_default_publish_kit_path_uses_run_exports_when_no_output_dir_is_given(self):
        path = default_publish_kit_path(Path("runs/game-20260627-142836"))

        self.assertEqual(path, Path("runs/game-20260627-142836/exports/game/youtube_paste_kit.md"))

    def test_write_publish_kit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "runs" / "game"
            run_dir.mkdir(parents=True)
            chapters = root / "chapters.txt"
            at_bats = root / "at_bats.txt"
            chapters.write_text("0:00 Pregame\n10:00 Top 1\n", encoding="utf-8")
            at_bats.write_text("10:00 Maya R. (#22)\n", encoding="utf-8")

            result = write_publish_kit(
                run_path=run_dir,
                chapters_path=chapters,
                at_bats_path=at_bats,
                output_dir=root / "publish",
                game_name="Game Name",
            )
            kit_text = result.output_path.read_text(encoding="utf-8")

            self.assertEqual(result.game_name, "Game Name")
            self.assertEqual(result.output_path.name, "youtube_paste_kit.md")
            self.assertIn("Game Name", kit_text)


if __name__ == "__main__":
    unittest.main()
