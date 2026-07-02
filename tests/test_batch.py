import tempfile
import unittest
from pathlib import Path

from sidelinehd_extractor.batch import run_playlist_batch
from sidelinehd_extractor.workflow import RunGameResult, RunYoutubeGameResult
from sidelinehd_extractor.youtube import DownloadResult, PlaylistEntry, YTDLPError


class PlaylistBatchTests(unittest.TestCase):
    def test_run_playlist_batch_processes_entries_in_order_and_writes_state(self):
        entries = [
            PlaylistEntry("one", "https://youtu.be/one", "Game One", 1),
            PlaylistEntry("two", "https://youtu.be/two", "Game Two", 2),
        ]
        calls = []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def run_youtube(**kwargs):
                calls.append(kwargs["url"])
                return _run_result(root, kwargs["url"].rsplit("/", 1)[-1])

            result = run_playlist_batch(
                "playlist",
                video_dir=root / "videos",
                output_dir=root / "runs",
                list_videos=lambda *_args, **_kwargs: entries,
                run_youtube=run_youtube,
                sleep=lambda _seconds: None,
            )

            state_text = result.state_path.read_text(encoding="utf-8")
            summary_text = result.summary_path.read_text(encoding="utf-8")

        self.assertEqual(calls, ["https://youtu.be/one", "https://youtu.be/two"])
        self.assertEqual(result.total, 2)
        self.assertEqual(result.processed, 2)
        self.assertEqual(result.failed, 0)
        self.assertEqual(
            result.summary,
            "Playlist batch complete: 2 processed, 0 skipped, 0 failed out of 2.",
        )
        self.assertIn('"video_id": "one"', state_text)
        self.assertIn('"status": "done"', state_text)
        self.assertIn("# Playlist Batch Summary", summary_text)
        self.assertIn("## 1. Game One", summary_text)
        self.assertIn("- URL: https://youtu.be/one", summary_text)
        self.assertIn("- Chapters:", summary_text)
        self.assertIn("- At-bats:", summary_text)

    def test_run_playlist_batch_skips_already_done_entries(self):
        entries = [
            PlaylistEntry("one", "https://youtu.be/one", "Game One", 1),
            PlaylistEntry("two", "https://youtu.be/two", "Game Two", 2),
        ]
        calls = []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "runs" / "playlist_state.jsonl"
            state_path.parent.mkdir(parents=True)
            prior = _run_result(root, "one").run
            state_path.write_text(
                '{"video_id": "one", "url": "https://youtu.be/one", "title": "Game One", '
                f'"index": 1, "status": "done", "run_dir": "{prior.run_dir}", '
                f'"chapters_path": "{prior.chapters_path}", '
                f'"at_bats_path": "{prior.at_bats_path}"}}\n',
                encoding="utf-8",
            )

            def run_youtube(**kwargs):
                calls.append(kwargs["url"])
                return _run_result(root, "two")

            result = run_playlist_batch(
                "playlist",
                video_dir=root / "videos",
                output_dir=root / "runs",
                list_videos=lambda *_args, **_kwargs: entries,
                run_youtube=run_youtube,
                sleep=lambda _seconds: None,
            )

        self.assertEqual(calls, ["https://youtu.be/two"])
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.processed, 1)
        self.assertEqual(result.entries[0].status, "skipped")

    def test_run_playlist_batch_reprocesses_done_entry_when_outputs_are_missing(self):
        entries = [PlaylistEntry("one", "https://youtu.be/one", "Game One", 1)]
        calls = []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "runs" / "playlist_state.jsonl"
            state_path.parent.mkdir(parents=True)
            state_path.write_text(
                '{"video_id": "one", "url": "https://youtu.be/one", "title": "Game One", '
                '"index": 1, "status": "done", "run_dir": "missing/run", '
                '"chapters_path": "missing/chapters.txt", '
                '"at_bats_path": "missing/at_bats.txt"}\n',
                encoding="utf-8",
            )

            def run_youtube(**kwargs):
                calls.append(kwargs["url"])
                return _run_result(root, "one")

            result = run_playlist_batch(
                "playlist",
                video_dir=root / "videos",
                output_dir=root / "runs",
                list_videos=lambda *_args, **_kwargs: entries,
                run_youtube=run_youtube,
                sleep=lambda _seconds: None,
            )

        self.assertEqual(calls, ["https://youtu.be/one"])
        self.assertEqual(result.skipped, 0)
        self.assertEqual(result.processed, 1)

    def test_run_playlist_batch_force_reprocesses_done_entries(self):
        entries = [PlaylistEntry("one", "https://youtu.be/one", "Game One", 1)]
        calls = []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "runs" / "playlist_state.jsonl"
            state_path.parent.mkdir(parents=True)
            state_path.write_text(
                '{"video_id": "one", "url": "https://youtu.be/one", "title": "Game One", '
                '"index": 1, "status": "done"}\n',
                encoding="utf-8",
            )

            def run_youtube(**kwargs):
                calls.append(kwargs["url"])
                return _run_result(root, "one")

            result = run_playlist_batch(
                "playlist",
                video_dir=root / "videos",
                output_dir=root / "runs",
                force=True,
                list_videos=lambda *_args, **_kwargs: entries,
                run_youtube=run_youtube,
                sleep=lambda _seconds: None,
            )

        self.assertEqual(calls, ["https://youtu.be/one"])
        self.assertEqual(result.skipped, 0)
        self.assertEqual(result.processed, 1)

    def test_run_playlist_batch_does_not_retry_deterministic_failures(self):
        entries = [
            PlaylistEntry("bad", "https://youtu.be/bad", "Bad Game", 1),
            PlaylistEntry("good", "https://youtu.be/good", "Good Game", 2),
        ]
        calls = []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def run_youtube(**kwargs):
                calls.append(kwargs["url"])
                if kwargs["url"].endswith("/bad"):
                    raise RuntimeError("download failed")
                return _run_result(root, "good")

            result = run_playlist_batch(
                "playlist",
                video_dir=root / "videos",
                output_dir=root / "runs",
                retries=1,
                list_videos=lambda *_args, **_kwargs: entries,
                run_youtube=run_youtube,
                sleep=lambda _seconds: None,
            )
            summary_text = result.summary_path.read_text(encoding="utf-8")

        self.assertEqual(
            calls,
            ["https://youtu.be/bad", "https://youtu.be/good"],
        )
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.processed, 1)
        self.assertEqual(result.entries[0].status, "failed")
        self.assertEqual(result.entries[0].attempts, 1)
        self.assertIn("download failed", summary_text)

    def test_run_playlist_batch_retries_ytdlp_failures(self):
        entries = [PlaylistEntry("bad", "https://youtu.be/bad", "Bad Game", 1)]
        calls = []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def run_youtube(**kwargs):
                calls.append(kwargs["url"])
                raise YTDLPError(["yt-dlp", kwargs["url"]], 1, "", "rate limited")

            result = run_playlist_batch(
                "playlist",
                video_dir=root / "videos",
                output_dir=root / "runs",
                retries=1,
                list_videos=lambda *_args, **_kwargs: entries,
                run_youtube=run_youtube,
                sleep=lambda _seconds: None,
            )

        self.assertEqual(calls, ["https://youtu.be/bad", "https://youtu.be/bad"])
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.entries[0].attempts, 2)
        self.assertIn("yt-dlp failed", result.entries[0].error)

    def test_run_playlist_batch_applies_start_index_and_limit(self):
        entries = [
            PlaylistEntry("one", "https://youtu.be/one", "Game One", 1),
            PlaylistEntry("two", "https://youtu.be/two", "Game Two", 2),
            PlaylistEntry("three", "https://youtu.be/three", "Game Three", 3),
        ]
        calls = []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def run_youtube(**kwargs):
                calls.append(kwargs["url"])
                return _run_result(root, kwargs["url"].rsplit("/", 1)[-1])

            result = run_playlist_batch(
                "playlist",
                video_dir=root / "videos",
                output_dir=root / "runs",
                start_index=1,
                limit=1,
                list_videos=lambda *_args, **_kwargs: entries,
                run_youtube=run_youtube,
                sleep=lambda _seconds: None,
            )

        self.assertEqual(calls, ["https://youtu.be/two"])
        self.assertEqual(result.total, 1)
        self.assertEqual(result.processed, 1)

    def test_run_playlist_batch_compacts_state_to_one_record_per_entry(self):
        entries = [
            PlaylistEntry("one", "https://youtu.be/one", "Game One", 1),
            PlaylistEntry("two", "https://youtu.be/two", "Game Two", 2),
        ]
        calls = []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def run_youtube(**kwargs):
                calls.append(kwargs["url"])
                return _run_result(root, kwargs["url"].rsplit("/", 1)[-1])

            run_playlist_batch(
                "playlist",
                video_dir=root / "videos",
                output_dir=root / "runs",
                list_videos=lambda *_args, **_kwargs: entries,
                run_youtube=run_youtube,
                sleep=lambda _seconds: None,
            )
            run_playlist_batch(
                "playlist",
                video_dir=root / "videos",
                output_dir=root / "runs",
                list_videos=lambda *_args, **_kwargs: entries,
                run_youtube=run_youtube,
                sleep=lambda _seconds: None,
            )
            state_lines = (root / "runs" / "playlist_state.jsonl").read_text().splitlines()

        self.assertEqual(calls, ["https://youtu.be/one", "https://youtu.be/two"])
        self.assertEqual(len(state_lines), 2)
        self.assertTrue(all('"status": "done"' in line for line in state_lines))


def _run_result(root: Path, stem: str) -> RunYoutubeGameResult:
    run_dir = root / "runs" / stem
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text("{}\n", encoding="utf-8")
    download = DownloadResult(
        url=f"https://youtu.be/{stem}",
        output_dir=root / "videos",
        video_path=root / "videos" / f"{stem}.mp4",
        command=["yt-dlp", stem],
        stdout="",
        stderr="",
    )
    run = RunGameResult(
        run_dir=run_dir,
        manifest_path=manifest_path,
        samples_path=run_dir / "samples.jsonl",
        states_path=run_dir / "states.jsonl",
        events_path=run_dir / "events.jsonl",
        chapters_path=run_dir / "chapters.txt",
        at_bats_path=run_dir / "at_bats.txt",
        sample_count=1,
        state_count=1,
        event_count=1,
    )
    run.chapters_path.write_text("chapters\n", encoding="utf-8")
    run.at_bats_path.write_text("at bats\n", encoding="utf-8")
    return RunYoutubeGameResult(download=download, run=run)


if __name__ == "__main__":
    unittest.main()
