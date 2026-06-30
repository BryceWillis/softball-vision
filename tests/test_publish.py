import html
import tempfile
import unittest
from pathlib import Path

from sidelinehd_extractor.exports import PROJECT_CREDIT
from sidelinehd_extractor.publish import (
    default_publish_kit_path,
    render_publish_kit,
    render_publish_kit_html,
    write_publish_kit,
)


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
            chapters_text = f"0:00 Pregame\n10:00 Top 1\n\n{PROJECT_CREDIT}\n"
            at_bats_text = f"10:00 Maya R. (#22)\n\n{PROJECT_CREDIT}\n"
            chapters.write_text(chapters_text, encoding="utf-8")
            at_bats.write_text(at_bats_text, encoding="utf-8")

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
            self.assertEqual(result.markdown_path, result.output_path)
            self.assertEqual(result.html_path, result.output_path.with_suffix(".html"))
            self.assertTrue(result.html_path.exists())
            self.assertIn("Game Name", kit_text)

    def test_write_publish_kit_can_skip_html(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "runs" / "game"
            run_dir.mkdir(parents=True)
            chapters = root / "chapters.txt"
            at_bats = root / "at_bats.txt"
            chapters.write_text("0:00 Pregame\n", encoding="utf-8")
            at_bats.write_text("10:00 Maya R. (#22)\n", encoding="utf-8")

            result = write_publish_kit(
                run_path=run_dir,
                chapters_path=chapters,
                at_bats_path=at_bats,
                generate_html=False,
            )

            self.assertIsNone(result.html_path)
            self.assertFalse(result.output_path.with_suffix(".html").exists())

    def test_render_publish_kit_html_includes_escaped_text_and_copy_controls(self):
        chapters_text = f"0:00 Pregame\n10:00 Top <1>\n\n{PROJECT_CREDIT}\n"
        at_bats_text = f"1st Inning\n10:00 Maya R. (#22) & Team\n\n{PROJECT_CREDIT}\n"

        text = render_publish_kit_html(
            game_name="Game <Name>",
            chapters_text=chapters_text,
            at_bats_text=at_bats_text,
            chapters_path=Path("runs/game/chapters.txt"),
            at_bats_path=Path("runs/game/at_bats.txt"),
        )

        self.assertIn(html.escape("YouTube Paste Kit: Game <Name>"), text)
        self.assertIn(html.escape(chapters_text), text)
        self.assertIn(html.escape(at_bats_text), text)
        self.assertIn(PROJECT_CREDIT, html.unescape(text))
        self.assertIn('data-copy-target="chapters-text"', text)
        self.assertIn('data-copy-target="at-bats-text"', text)
        self.assertIn("navigator.clipboard.writeText", text)
        self.assertIn('document.execCommand("copy")', text)
        self.assertIn("Select the text and copy manually.", text)
        self.assertIn('type="checkbox"', text)


if __name__ == "__main__":
    unittest.main()
