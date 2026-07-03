"""Tests for the local web app skeleton (item 46 / phase 39a)."""

from __future__ import annotations


import pytest

pytest.importorskip("fastapi")
pytest.importorskip("jinja2")
pytest.importorskip("multipart")
pytest.importorskip("httpx")
import uvicorn  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from sidelinehd_extractor.batch import PlaylistBatchItemResult, PlaylistBatchResult  # noqa: E402
from sidelinehd_extractor.cli import main  # noqa: E402
from sidelinehd_extractor.webapp import jobs as jobs_module  # noqa: E402
from sidelinehd_extractor.webapp.app import create_app  # noqa: E402
from sidelinehd_extractor.webapp.jobs import (  # noqa: E402
    JobRunner,
    JobStore,
    summarize_result,
)
from sidelinehd_extractor.workflow import RunGameResult, RunYoutubeGameResult  # noqa: E402
from sidelinehd_extractor.youtube import DownloadResult  # noqa: E402

FAKE_STAGES = ("download", "process", "warning field-never-read: right_score", "export")


class InlineExecutor:
    """Runs submitted work synchronously so tests are deterministic."""

    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)


def _make_client() -> tuple:
    store = JobStore()
    runner = JobRunner(store, executor=InlineExecutor(), pipeline_kwargs=lambda: {})
    app = create_app(store=store, runner=runner)
    return TestClient(app), store


def _fake_single(store, statuses_seen, result=None):
    def fake(url, video_dir, output_dir, stage_progress=None, **kwargs):
        statuses_seen.append(store.list()[0].status)
        for stage in FAKE_STAGES:
            stage_progress(stage)
        return result if result is not None else {"kind": "single", "run_dir": "runs/fake"}

    return fake


def test_submit_single_job_runs_to_done(monkeypatch):
    client, store = _make_client()
    statuses_seen = []
    monkeypatch.setattr(jobs_module, "run_youtube_game", _fake_single(store, statuses_seen))

    response = client.post("/jobs", data={"url": "https://youtu.be/abc123", "kind": "single"})
    assert response.status_code == 200

    jobs = store.list()
    assert len(jobs) == 1
    job = jobs[0]
    assert statuses_seen == ["running"]
    assert job.status == "done"
    assert job.stages == list(FAKE_STAGES)
    assert job.current_stage == "export"
    assert job.warnings == ["warning field-never-read: right_score"]
    assert job.result == {"kind": "single", "run_dir": "runs/fake"}
    assert job.finished_at is not None
    assert job.id in response.text


def test_submit_playlist_dispatches_to_batch(monkeypatch):
    client, store = _make_client()
    calls = []

    def fake_batch(playlist_url, video_dir, output_dir, stage_progress=None, **kwargs):
        calls.append(playlist_url)
        stage_progress("download")
        return {"kind": "playlist", "processed": 2}

    monkeypatch.setattr(jobs_module, "run_playlist_batch", fake_batch)
    monkeypatch.setattr(
        jobs_module,
        "run_youtube_game",
        lambda **kwargs: pytest.fail("single-game path must not run for playlist jobs"),
    )

    response = client.post(
        "/jobs", data={"url": "https://youtube.com/playlist?list=PL1", "kind": "playlist"}
    )
    assert response.status_code == 200
    assert calls == ["https://youtube.com/playlist?list=PL1"]
    job = store.list()[0]
    assert job.kind == "playlist"
    assert job.status == "done"
    assert job.result == {"kind": "playlist", "processed": 2}


def test_pipeline_exception_sets_error_status(monkeypatch):
    client, store = _make_client()

    def fake_raises(**kwargs):
        raise RuntimeError("yt-dlp exploded")

    monkeypatch.setattr(jobs_module, "run_youtube_game", fake_raises)

    response = client.post("/jobs", data={"url": "https://youtu.be/abc123", "kind": "single"})
    assert response.status_code == 200
    job = store.list()[0]
    assert job.status == "error"
    assert job.error == "yt-dlp exploded"
    assert job.finished_at is not None

    status = client.get(f"/jobs/{job.id}/status")
    assert status.status_code == 200
    assert "yt-dlp exploded" in status.text
    assert "every 1s" not in status.text


@pytest.mark.parametrize(
    "data",
    [
        {"url": "", "kind": "single"},
        {"url": "   ", "kind": "single"},
        {"url": "notaurl", "kind": "single"},
        {"url": "ftp://example.com/x", "kind": "single"},
        {"url": "https://youtu.be/abc123", "kind": "sideways"},
    ],
)
def test_submit_invalid_returns_400_and_creates_no_job(data):
    client, store = _make_client()
    response = client.post("/jobs", data=data)
    assert response.status_code == 400
    assert "form-error-message" in response.text
    assert store.list() == []


def test_status_partial_polls_while_active_and_stops_when_done(monkeypatch):
    client, store = _make_client()
    monkeypatch.setattr(jobs_module, "run_youtube_game", _fake_single(store, []))

    active = store.create(kind="single", url="https://youtu.be/active")
    store.update(active.id, status="running")
    store.record_stage(active.id, "download")
    response = client.get(f"/jobs/{active.id}/status")
    assert response.status_code == 200
    assert 'hx-trigger="every 1s"' in response.text
    assert "download" in response.text

    client.post("/jobs", data={"url": "https://youtu.be/done", "kind": "single"})
    done = store.list()[0]
    response = client.get(f"/jobs/{done.id}/status")
    assert response.status_code == 200
    assert "every 1s" not in response.text
    assert "warning field-never-read: right_score" in response.text
    assert f"/jobs/{done.id}/results" in response.text


def test_index_renders_form_and_jobs():
    client, store = _make_client()
    store.create(kind="single", url="https://youtu.be/first")
    store.create(kind="playlist", url="https://youtube.com/playlist?list=PL2")

    response = client.get("/")
    assert response.status_code == 200
    assert 'hx-post="/jobs"' in response.text
    assert "https://youtu.be/first" in response.text
    assert "https://youtube.com/playlist?list=PL2" in response.text
    # Newest first.
    assert response.text.index("PL2") < response.text.index("first")


def test_job_detail_shows_stage_log_and_404s():
    client, store = _make_client()
    job = store.create(kind="single", url="https://youtu.be/abc123")
    store.record_stage(job.id, "download")
    store.record_stage(job.id, "warning field-never-read: right_score")
    store.update(job.id, status="done", result={"run_dir": "runs/fake"})

    response = client.get(f"/jobs/{job.id}")
    assert response.status_code == 200
    assert "download" in response.text
    assert "warning field-never-read: right_score" in response.text
    assert f"/jobs/{job.id}/results" in response.text
    assert "runs/fake" in response.text

    assert client.get("/jobs/deadbeef").status_code == 404
    assert client.get("/jobs/deadbeef/status").status_code == 404


def test_static_htmx_is_vendored():
    client, _ = _make_client()
    response = client.get("/static/htmx.min.js")
    assert response.status_code == 200
    assert len(response.content) > 10000


def test_job_store_list_newest_first_and_update_rejects_unknown_field():
    store = JobStore()
    first = store.create(kind="single", url="https://a")
    second = store.create(kind="single", url="https://b")
    assert [job.id for job in store.list()] == [second.id, first.id]
    assert store.get("missing") is None
    with pytest.raises(AttributeError):
        store.update(first.id, bogus_field=1)


def test_summarize_result_single_dataclass(tmp_path):
    run = RunGameResult(
        run_dir=tmp_path / "run",
        manifest_path=tmp_path / "run/manifest.json",
        samples_path=tmp_path / "run/samples.jsonl",
        states_path=tmp_path / "run/states.jsonl",
        events_path=tmp_path / "run/events.jsonl",
        chapters_path=tmp_path / "run/chapters.txt",
        at_bats_path=tmp_path / "run/at_bats.txt",
        sample_count=10,
        state_count=8,
        event_count=3,
    )
    download = DownloadResult(
        url="https://youtu.be/abc123",
        output_dir=tmp_path,
        video_path=tmp_path / "video.mp4",
        command=["yt-dlp"],
        stdout="",
        stderr="",
    )
    summary = summarize_result(RunYoutubeGameResult(download=download, run=run))
    assert summary["kind"] == "single"
    assert summary["run_dir"] == str(tmp_path / "run")
    assert summary["chapters_path"] == str(tmp_path / "run/chapters.txt")
    assert summary["event_count"] == 3


def test_summarize_result_playlist_dataclass(tmp_path):
    entry = PlaylistBatchItemResult(
        video_id="abc123",
        url="https://youtu.be/abc123",
        title="Game 1",
        index=0,
        status="done",
        attempts=1,
        run_dir=tmp_path / "run",
        chapters_path=tmp_path / "run/chapters.txt",
        at_bats_path=tmp_path / "run/at_bats.txt",
    )
    batch = PlaylistBatchResult(
        playlist_url="https://youtube.com/playlist?list=PL1",
        state_path=tmp_path / "playlist_state.jsonl",
        summary_path=tmp_path / "batch_summary.md",
        summary="",
        total=1,
        processed=1,
        skipped=0,
        failed=0,
        entries=[entry],
    )
    summary = summarize_result(batch)
    assert summary["kind"] == "playlist"
    assert summary["total"] == 1
    assert summary["entries"][0]["video_id"] == "abc123"
    assert summary["entries"][0]["chapters_path"] == str(tmp_path / "run/chapters.txt")


def test_create_app_builds_without_binding_a_socket():
    app = create_app()
    routes = {route.path for route in app.routes}
    assert {
        "/",
        "/jobs",
        "/jobs/{job_id}",
        "/jobs/{job_id}/status",
        "/jobs/{job_id}/results",
    } <= routes


CHAPTERS_TEXT = "0:00 Pregame\n12:34 Top 1\n"
AT_BATS_TEXT = "1st Inning\n12:34 #22\n14:05 #7\n"
REVIEW_REPORT_TEXT = (
    "# Review Report\n"
    "\n"
    "Run: `runs/fake`\n"
    "\n"
    "## Run Warnings\n"
    "\n"
    "- `field-never-read` `right_score` - right_score was never read\n"
    "\n"
    "Flagged events: 3\n"
    "\n"
    "Use this file to inspect likely OCR/detection issues.\n"
)


def _write_fake_run_dir(root, name="run", review_report=True):
    """Materialize the artifacts item 47 reads: exports plus review_report.md."""

    run_dir = root / name
    run_dir.mkdir(parents=True)
    chapters = run_dir / "full_chapters.txt"
    at_bats = run_dir / "full_at_bats.txt"
    chapters.write_text(CHAPTERS_TEXT, encoding="utf-8")
    at_bats.write_text(AT_BATS_TEXT, encoding="utf-8")
    if review_report:
        (run_dir / "review_report.md").write_text(REVIEW_REPORT_TEXT, encoding="utf-8")
    return {
        "run_dir": str(run_dir),
        "chapters_path": str(chapters),
        "at_bats_path": str(at_bats),
    }


def test_results_single_done_job_renders_copy_kit_and_review_summary(tmp_path):
    client, store = _make_client()
    paths = _write_fake_run_dir(tmp_path)
    job = store.create(kind="single", url="https://youtu.be/abc123")
    store.update(
        job.id,
        status="done",
        result={"kind": "single", "video_path": "videos/Game vs Ice.mp4", **paths},
    )

    response = client.get(f"/jobs/{job.id}/results")
    assert response.status_code == 200
    # Exports rendered into copy panels with the publish-kit copy markup.
    assert "12:34 Top 1" in response.text
    assert "12:34 #22" in response.text
    assert 'data-copy-target="game-0-chapters-text"' in response.text
    assert 'data-copy-target="game-0-at-bats-text"' in response.text
    assert "navigator.clipboard.writeText" in response.text
    # Review-report summary: flagged count plus the item-45 run warning.
    assert "Flagged events: 3" in response.text
    assert "right_score was never read" in response.text
    # Game label comes from the video name.
    assert "Game vs Ice.mp4" in response.text


def test_results_single_job_without_review_report_degrades_gracefully(tmp_path):
    client, store = _make_client()
    paths = _write_fake_run_dir(tmp_path, review_report=False)
    job = store.create(kind="single", url="https://youtu.be/abc123")
    store.update(job.id, status="done", result={"kind": "single", **paths})

    response = client.get(f"/jobs/{job.id}/results")
    assert response.status_code == 200
    assert "12:34 Top 1" in response.text
    assert "No review report found" in response.text


def test_results_playlist_renders_blocks_in_order_with_error_block(tmp_path):
    client, store = _make_client()
    ok_paths = _write_fake_run_dir(tmp_path, name="run-1")
    job = store.create(kind="playlist", url="https://youtube.com/playlist?list=PL1")
    store.update(
        job.id,
        status="done",
        result={
            "kind": "playlist",
            "entries": [
                {"video_id": "vid1", "title": "Game 1", "status": "done", **ok_paths},
                {
                    "video_id": "vid2",
                    "title": "Game 2",
                    "status": "failed",
                    "run_dir": None,
                    "chapters_path": None,
                    "at_bats_path": None,
                    "error": "yt-dlp exploded",
                },
            ],
        },
    )

    response = client.get(f"/jobs/{job.id}/results")
    assert response.status_code == 200
    assert "1. Game 1" in response.text
    assert "2. Game 2" in response.text
    # Batch order preserved: the successful block precedes the failed one.
    assert response.text.index("1. Game 1") < response.text.index("2. Game 2")
    # Success block carries the copy kit and review summary.
    assert 'data-copy-target="game-0-chapters-text"' in response.text
    assert "Flagged events: 3" in response.text
    # Failure is a clearly-marked error block with no copy kit of its own.
    assert "error-block" in response.text
    assert "yt-dlp exploded" in response.text
    assert 'data-copy-target="game-1-chapters-text"' not in response.text


def test_results_not_done_job_links_back_to_detail_and_unknown_404s():
    client, store = _make_client()
    job = store.create(kind="single", url="https://youtu.be/abc123")
    store.update(job.id, status="running")

    response = client.get(f"/jobs/{job.id}/results")
    assert response.status_code == 200
    assert "not finished" in response.text
    assert f"/jobs/{job.id}" in response.text
    assert "data-copy-target" not in response.text

    assert client.get("/jobs/deadbeef/results").status_code == 404


def test_index_error_clear_is_scoped_to_the_submit_request():
    """CR-51: the afterRequest clear must be gated on the /jobs submit path so
    the 1s status polls cannot wipe a validation message."""

    client, _ = _make_client()
    response = client.get("/")
    assert 'evt.detail.requestConfig.path === "/jobs"' in response.text


def test_cli_serve_wiring(monkeypatch, capsys):
    recorded = {}

    def fake_run(app, **kwargs):
        recorded["app"] = app
        recorded.update(kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    assert main(["serve", "--port", "9999"]) == 0
    assert recorded["app"] == "sidelinehd_extractor.webapp.app:create_app"
    assert recorded["factory"] is True
    assert recorded["host"] == "127.0.0.1"
    assert recorded["port"] == 9999
    assert recorded["reload"] is False
    assert "http://127.0.0.1:9999" in capsys.readouterr().err
