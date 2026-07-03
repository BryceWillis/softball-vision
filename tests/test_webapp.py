"""Tests for the local web app skeleton (item 46 / phase 39a)."""

from __future__ import annotations


import html
import re
from urllib.parse import parse_qs, urlparse

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


def test_frame_progress_callback_updates_job_fields(monkeypatch):
    client, store = _make_client()

    def fake(url, video_dir, output_dir, stage_progress=None, progress=None, **kwargs):
        stage_progress("process")
        progress(3, 10, 15.0, 42, 140)
        return {"kind": "single", "run_dir": "runs/fake"}

    monkeypatch.setattr(jobs_module, "run_youtube_game", fake)

    client.post("/jobs", data={"url": "https://youtu.be/abc123", "kind": "single"})
    job = store.list()[0]
    assert job.frames_done == 3
    assert job.frames_total == 10


def test_status_partial_shows_frame_progress_during_process_stage():
    client, store = _make_client()
    job = store.create(kind="single", url="https://youtu.be/abc123")
    store.update(job.id, status="running", frames_done=3, frames_total=10)
    store.record_stage(job.id, "process")

    response = client.get(f"/jobs/{job.id}/status")
    assert response.status_code == 200
    assert "Processing: 3 / 10 frames" in response.text
    assert "(30%)" in response.text

    # Outside the process stage the plain stage word still renders.
    store.record_stage(job.id, "detect-events")
    response = client.get(f"/jobs/{job.id}/status")
    assert "Processing:" not in response.text
    assert "detect-events" in response.text


def test_job_detail_body_polls_in_place_and_stops_when_terminal():
    client, store = _make_client()
    job = store.create(kind="single", url="https://youtu.be/abc123")
    store.update(job.id, status="running")
    store.record_stage(job.id, "download")

    page = client.get(f"/jobs/{job.id}")
    assert page.status_code == 200
    # The whole detail body polls; the embedded status partial must not add a
    # second poller of its own.
    assert f'hx-get="/jobs/{job.id}/detail"' in page.text
    assert f'hx-get="/jobs/{job.id}/status"' not in page.text
    assert 'hx-trigger="every 1s"' in page.text

    partial = client.get(f"/jobs/{job.id}/detail")
    assert partial.status_code == 200
    assert "Stage log" in partial.text
    assert "download" in partial.text
    assert 'hx-trigger="every 1s"' in partial.text

    store.update(job.id, status="done", result={"run_dir": "runs/fake"})
    finished = client.get(f"/jobs/{job.id}/detail")
    assert "every 1s" not in finished.text
    assert f"/jobs/{job.id}/results" in finished.text

    assert client.get("/jobs/deadbeef/detail").status_code == 404


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
        "/jobs/{job_id}/feedback",
        "/jobs/{job_id}/feedback/preview",
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


def _write_feedback_run_dir(root):
    """Run dir for the item 51 feedback egress tests."""

    from sidelinehd_extractor.models import Event, EventType
    from sidelinehd_extractor.processing import write_json, write_jsonl

    run_dir = root / "feedback-run"
    run_dir.mkdir(parents=True)
    write_json(
        run_dir / "manifest.json",
        {
            "template": {"name": "sidelinehd active"},
            "tesseract_version": "5.3.0",
            "ocr_backend": "tesseract",
            "ocr_workers": 2,
            "sample_every_seconds": 5.0,
            "fields": ["batter_card_number"],
            "warnings": [],
        },
    )
    write_jsonl(
        run_dir / "events.jsonl",
        [
            Event(EventType.HALF_INNING_START, 600, "Top 1"),
            Event(
                EventType.AT_BAT_START,
                605,
                "Charlotte P. (#44)",
                player_number="44",
                metadata={"ocr_player_number": "88"},
            ),
        ],
    )
    return {
        "run_dir": str(run_dir),
        "chapters_path": str(run_dir / "full_chapters.txt"),
        "at_bats_path": str(run_dir / "full_at_bats.txt"),
    }


def _decoded_feedback_bodies(response_text):
    github_href = html.unescape(
        re.search(r'href="([^"]*github\.com[^"]*)"', response_text).group(1)
    )
    mailto_href = html.unescape(re.search(r'href="(mailto:[^"]*)"', response_text).group(1))
    preview_body = html.unescape(
        re.search(
            r'<textarea[^>]+id="feedback-body"[^>]*>(.*?)</textarea>',
            response_text,
            flags=re.S,
        ).group(1)
    )
    return {
        "preview": preview_body,
        "github": parse_qs(urlparse(github_href).query)["body"][0],
        "email": parse_qs(urlparse(mailto_href).query)["body"][0],
        "copy": preview_body,
        "github_href": github_href,
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


def test_results_page_shows_loud_health_banner_from_job_summary(tmp_path):
    from sidelinehd_extractor.workflow import NO_SCOREBOARD_WARNING

    client, store = _make_client()
    paths = _write_fake_run_dir(tmp_path)
    job = store.create(kind="single", url="https://youtu.be/abc123")
    store.update(
        job.id,
        status="done",
        result={"kind": "single", "health_warning": NO_SCOREBOARD_WARNING, **paths},
    )

    response = client.get(f"/jobs/{job.id}/results")
    assert response.status_code == 200
    assert 'class="health-banner"' in response.text
    assert "No scoreboard detected" in response.text


def test_results_page_reads_health_from_manifest_for_playlist_entries(tmp_path):
    import json as json_module

    client, store = _make_client()
    paths = _write_fake_run_dir(tmp_path)
    (tmp_path / "run" / "manifest.json").write_text(
        json_module.dumps(
            {
                "health": {
                    "event_count": 0,
                    "no_scoreboard_detected": True,
                    "message": "No scoreboard detected — the template may not match "
                    "this video's overlay.",
                }
            }
        ),
        encoding="utf-8",
    )
    job = store.create(kind="playlist", url="https://youtube.com/playlist?list=PL1")
    store.update(
        job.id,
        status="done",
        result={
            "kind": "playlist",
            "entries": [{"video_id": "vid1", "title": "Game 1", "status": "done", **paths}],
        },
    )

    response = client.get(f"/jobs/{job.id}/results")
    assert response.status_code == 200
    assert 'class="health-banner"' in response.text
    assert "No scoreboard detected" in response.text


def test_results_page_has_no_health_banner_for_healthy_run(tmp_path):
    client, store = _make_client()
    paths = _write_fake_run_dir(tmp_path)
    job = store.create(kind="single", url="https://youtu.be/abc123")
    store.update(job.id, status="done", result={"kind": "single", **paths})

    response = client.get(f"/jobs/{job.id}/results")
    assert response.status_code == 200
    assert 'class="health-banner"' not in response.text


def test_job_status_and_detail_show_health_banner_from_stage_warning():
    from sidelinehd_extractor.workflow import NO_SCOREBOARD_WARNING

    client, store = _make_client()
    job = store.create(kind="single", url="https://youtu.be/abc123")
    store.record_stage(job.id, f"warning no-scoreboard-detected: {NO_SCOREBOARD_WARNING}")
    store.record_stage(job.id, "warning field-never-read: right_score")
    store.update(job.id, status="done")

    for path in (f"/jobs/{job.id}/status", f"/jobs/{job.id}"):
        response = client.get(path)
        assert response.status_code == 200
        assert 'class="health-banner"' in response.text
        assert "No scoreboard detected" in response.text
        # Ordinary warnings still render in the plain list, not the banner.
        assert "field-never-read: right_score" in response.text


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


def test_feedback_preview_and_handoff_bodies_are_sanitized(tmp_path):
    client, store = _make_client()
    paths = _write_feedback_run_dir(tmp_path)
    job = store.create(kind="single", url="https://youtu.be/abc123")
    store.update(job.id, status="done", result={"kind": "single", **paths})

    response = client.get(f"/jobs/{job.id}/feedback")

    assert response.status_code == 200
    assert "Open GitHub issue" in response.text
    assert "Charlotte" not in response.text
    assert "Player A (#44)" in response.text
    assert "#44" in response.text
    bodies = _decoded_feedback_bodies(response.text)
    assert bodies["github_href"].startswith(
        "https://github.com/BryceWillis/softball-vision/issues/new?"
    )
    for channel in ("preview", "github", "email", "copy"):
        body = bodies[channel]
        assert "Charlotte" not in body
        assert "Player A (#44)" in body
        assert '"player_number": "44"' in body


def test_feedback_preview_post_includes_note_in_all_handoff_paths(tmp_path):
    client, store = _make_client()
    paths = _write_feedback_run_dir(tmp_path)
    job = store.create(kind="single", url="https://youtu.be/abc123")
    store.update(job.id, status="done", result={"kind": "single", **paths})

    response = client.post(
        f"/jobs/{job.id}/feedback/preview",
        data={"entry": "0", "note": "Count looked wrong after the delay."},
    )

    assert response.status_code == 200
    assert "Count looked wrong after the delay." in response.text
    bodies = _decoded_feedback_bodies(response.text)
    for channel in ("preview", "github", "email", "copy"):
        assert "Count looked wrong after the delay." in bodies[channel]
        assert "Charlotte" not in bodies[channel]


def test_feedback_not_done_links_back_unknown_id_404_and_no_outbound_http(
    tmp_path, monkeypatch
):
    import http.client

    def fail_outbound_request(*args, **kwargs):
        pytest.fail("feedback route must not make outbound HTTP requests")

    monkeypatch.setattr(http.client.HTTPConnection, "request", fail_outbound_request)

    client, store = _make_client()
    running = store.create(kind="single", url="https://youtu.be/abc123")
    store.update(running.id, status="running")

    response = client.get(f"/jobs/{running.id}/feedback")
    assert response.status_code == 200
    assert "not finished" in response.text
    assert f"/jobs/{running.id}" in response.text

    paths = _write_feedback_run_dir(tmp_path)
    done = store.create(kind="single", url="https://youtu.be/def456")
    store.update(done.id, status="done", result={"kind": "single", **paths})
    response = client.get(f"/jobs/{done.id}/feedback")
    assert response.status_code == 200
    assert "Open GitHub issue" in response.text

    assert client.get("/jobs/deadbeef/feedback").status_code == 404


def test_results_page_lights_up_from_report_generated_by_run_game(tmp_path, monkeypatch):
    """Item 48 end-to-end: run_game writes review_report.md as a run artifact and
    the item 47 results page renders its flagged count and run warnings — no
    hand-written report fixture."""

    from unittest.mock import patch

    from sidelinehd_extractor.events import EventDetectionResult
    from sidelinehd_extractor.models import Event, EventType, HalfInning
    from sidelinehd_extractor.processing import ProcessResult, write_json, write_jsonl
    from sidelinehd_extractor.state import StateParseResult
    from sidelinehd_extractor.workflow import run_game

    run_dir = tmp_path / "runs" / "game-run"
    run_dir.mkdir(parents=True)
    process_result = ProcessResult(
        run_dir=run_dir,
        manifest_path=run_dir / "manifest.json",
        samples_path=run_dir / "samples.jsonl",
        sample_count=1,
        crop_count=1,
        warnings=[],
    )
    state_result = StateParseResult(
        input_path=run_dir / "samples.jsonl",
        output_path=run_dir / "states.jsonl",
        state_count=1,
    )
    event_result = EventDetectionResult(
        input_path=run_dir / "states.jsonl",
        output_path=run_dir / "events.jsonl",
        event_count=2,
    )
    write_json(
        process_result.manifest_path,
        {"warnings": [{"code": "field-never-read", "field": "right_score", "message": "empty"}]},
    )
    events = [
        Event(EventType.HALF_INNING_START, 600, "Top 1", inning=1, half=HalfInning.TOP),
        # OCR/roster disagreement makes this at-bat a flagged review row.
        Event(
            EventType.AT_BAT_START,
            605,
            "#22",
            inning=1,
            player_number="22",
            metadata={"ocr_player_number": "28"},
        ),
    ]
    write_jsonl(event_result.output_path, events)

    with patch("sidelinehd_extractor.workflow.process_video", return_value=process_result):
        with patch("sidelinehd_extractor.workflow.parse_samples_file", return_value=state_result):
            with patch(
                "sidelinehd_extractor.workflow.detect_events_file", return_value=event_result
            ):
                with patch("sidelinehd_extractor.workflow.load_events", return_value=events):
                    run = run_game(
                        video_path=tmp_path / "game.mp4",
                        output_dir=tmp_path / "runs",
                        output_prefix=tmp_path / "scratch" / "full",
                    )

    assert (run_dir / "review_report.md").exists()

    client, store = _make_client()
    job = store.create(kind="single", url="https://youtu.be/abc123")
    store.update(
        job.id,
        status="done",
        result={
            "kind": "single",
            "run_dir": str(run.run_dir),
            "chapters_path": str(run.chapters_path),
            "at_bats_path": str(run.at_bats_path),
        },
    )

    response = client.get(f"/jobs/{job.id}/results")
    assert response.status_code == 200
    assert "Flagged events: 1" in response.text
    assert "right_score" in response.text
    assert "No review report found" not in response.text
    assert 'data-copy-target="game-0-chapters-text"' in response.text


def _seed_review_run(tmp_path):
    """Run dir with a flagged at-bat, an unflagged at-bat, and real exports."""

    from sidelinehd_extractor.models import Event, EventType, HalfInning
    from sidelinehd_extractor.processing import write_json, write_jsonl
    from sidelinehd_extractor.workflow import finalize_run_exports

    run_dir = tmp_path / "runs" / "game-run"
    run_dir.mkdir(parents=True)
    prefix = run_dir / "full"
    write_json(
        run_dir / "manifest.json",
        {
            "export": {
                "include_chapter_intro": True,
                "chapter_intro_label": "Pregame",
                "include_inning_score": True,
                "include_at_bat_inning_headers": True,
                "output_prefix": str(prefix),
            }
        },
    )
    events = [
        Event(EventType.HALF_INNING_START, 600, "Top 1", inning=1, half=HalfInning.TOP),
        # OCR read 28 but the event says 22 -> "ocr-number=28" review flag.
        Event(
            EventType.AT_BAT_START,
            605,
            "Maya R. (#22)",
            inning=1,
            player_number="22",
            player_name="Maya R.",
            metadata={"ocr_player_number": "28"},
        ),
        Event(
            EventType.AT_BAT_START,
            700,
            "Zoe H. (#7)",
            inning=1,
            player_number="7",
            player_name="Zoe H.",
        ),
    ]
    write_jsonl(run_dir / "events.jsonl", events)
    chapters_path, at_bats_path = finalize_run_exports(run_dir)
    return run_dir, chapters_path, at_bats_path


def _make_review_client(tmp_path, monkeypatch):
    from sidelinehd_extractor.webapp import app as app_module

    # Flags must not depend on whatever project config exists in the CWD.
    monkeypatch.setattr(app_module, "load_configured_roster", lambda: None)
    run_dir, chapters_path, at_bats_path = _seed_review_run(tmp_path)
    client, store = _make_client()
    job = store.create(kind="single", url="https://youtu.be/abc123")
    store.update(
        job.id,
        status="done",
        result={
            "kind": "single",
            "run_dir": str(run_dir),
            "chapters_path": str(chapters_path),
            "at_bats_path": str(at_bats_path),
        },
    )
    return client, job, run_dir, at_bats_path


def test_review_page_lists_flagged_events_with_show_all_toggle(tmp_path, monkeypatch):
    client, job, _, _ = _make_review_client(tmp_path, monkeypatch)

    response = client.get(f"/jobs/{job.id}/review")
    assert response.status_code == 200
    assert "ocr-number=28" in response.text
    assert "Maya R." in response.text
    assert "Zoe H." not in response.text  # unflagged, hidden by default
    assert "Flagged events: 1 of 3" in response.text
    assert f"/jobs/{job.id}/results" in response.text

    everything = client.get(f"/jobs/{job.id}/review?show=all")
    assert "Zoe H." in everything.text


def test_review_edit_writes_csv_resolves_flag_and_rewrites_exports(tmp_path, monkeypatch):
    from sidelinehd_extractor.corrections import CORRECTION_CSV_COLUMNS

    client, job, run_dir, at_bats_path = _make_review_client(tmp_path, monkeypatch)

    response = client.post(
        f"/jobs/{job.id}/corrections",
        data={
            "timestamp": "605.0",
            "event_type": "at_bat_start",
            "field": "player_number",
            "value": "28",
        },
    )
    assert response.status_code == 200
    assert "ocr-number=28" not in response.text  # flag resolved in the partial

    csv_text = (run_dir / "corrections.csv").read_text(encoding="utf-8")
    lines = csv_text.splitlines()
    assert lines[0] == ",".join(CORRECTION_CSV_COLUMNS)
    assert len(lines) == 2

    # A label edit changes the exported text via the shared finalize helper.
    response = client.post(
        f"/jobs/{job.id}/corrections",
        data={
            "timestamp": "605.0",
            "event_type": "at_bat_start",
            "field": "label",
            "value": "Maya R. (#28)",
        },
    )
    assert response.status_code == 200
    assert "10:05 Maya R. (#28)" in at_bats_path.read_text(encoding="utf-8")
    assert len((run_dir / "corrections.csv").read_text(encoding="utf-8").splitlines()) == 3


def test_review_reposting_same_key_replaces_row_and_clear_reverts(tmp_path, monkeypatch):
    client, job, run_dir, at_bats_path = _make_review_client(tmp_path, monkeypatch)
    edit = {
        "timestamp": "605.0",
        "event_type": "at_bat_start",
        "field": "label",
        "value": "Maya R. (#28)",
    }
    client.post(f"/jobs/{job.id}/corrections", data=edit)
    client.post(f"/jobs/{job.id}/corrections", data={**edit, "value": "Maya R. (#26)"})

    csv_text = (run_dir / "corrections.csv").read_text(encoding="utf-8")
    assert len(csv_text.splitlines()) == 2  # replaced, not appended
    assert "Maya R. (#26)" in csv_text
    assert "Maya R. (#28)" not in csv_text
    assert "10:05 Maya R. (#26)" in at_bats_path.read_text(encoding="utf-8")

    response = client.post(
        f"/jobs/{job.id}/corrections/clear",
        data={"timestamp": "605.0", "event_type": "at_bat_start", "field": "label"},
    )
    assert response.status_code == 200
    assert len((run_dir / "corrections.csv").read_text(encoding="utf-8").splitlines()) == 1
    assert "10:05 Maya R. (#22)" in at_bats_path.read_text(encoding="utf-8")  # reverted


def test_review_delete_and_add_update_exports_in_order(tmp_path, monkeypatch):
    client, job, run_dir, at_bats_path = _make_review_client(tmp_path, monkeypatch)

    response = client.post(
        f"/jobs/{job.id}/corrections",
        data={"timestamp": "700", "event_type": "at_bat_start", "field": "delete"},
    )
    assert response.status_code == 200
    assert "Zoe H. (#7)" not in at_bats_path.read_text(encoding="utf-8")

    response = client.post(
        f"/jobs/{job.id}/corrections",
        data={
            "timestamp": "10:30",
            "event_type": "at_bat_start",
            "field": "add",
            "player_number": "26",
        },
    )
    assert response.status_code == 200
    at_bats_text = at_bats_path.read_text(encoding="utf-8")
    assert "10:30 #26" in at_bats_text
    assert at_bats_text.index("10:05") < at_bats_text.index("10:30")


def test_review_rejects_correction_with_no_matching_event(tmp_path, monkeypatch):
    client, job, run_dir, at_bats_path = _make_review_client(tmp_path, monkeypatch)
    before = at_bats_path.read_text(encoding="utf-8")

    response = client.post(
        f"/jobs/{job.id}/corrections",
        data={
            "timestamp": "900",
            "event_type": "at_bat_start",
            "field": "label",
            "value": "Nope",
        },
    )
    assert response.status_code == 400
    assert "no event matched correction" in response.text
    assert not (run_dir / "corrections.csv").exists()  # file untouched
    assert at_bats_path.read_text(encoding="utf-8") == before


def test_review_preserves_hand_written_correction_rows(tmp_path, monkeypatch):
    client, job, run_dir, _ = _make_review_client(tmp_path, monkeypatch)
    (run_dir / "corrections.csv").write_text(
        "event_type,timestamp,field,value,reason\n"
        "at_bat_start,10:05,label,Maya R. (#28),hand-written\n",
        encoding="utf-8",
    )

    response = client.post(
        f"/jobs/{job.id}/corrections",
        data={"timestamp": "700", "event_type": "at_bat_start", "field": "delete"},
    )
    assert response.status_code == 200
    csv_text = (run_dir / "corrections.csv").read_text(encoding="utf-8")
    assert "Maya R. (#28)" in csv_text  # hand-written row survived the rewrite
    assert "hand-written" in csv_text
    assert "delete" in csv_text


def test_review_not_done_links_back_and_bad_ids_404(tmp_path, monkeypatch):
    client, store = _make_client()
    job = store.create(kind="single", url="https://youtu.be/abc123")
    store.update(job.id, status="running")

    response = client.get(f"/jobs/{job.id}/review")
    assert response.status_code == 200
    assert "not finished" in response.text
    assert f"/jobs/{job.id}" in response.text

    assert client.get("/jobs/deadbeef/review").status_code == 404

    done = store.create(kind="single", url="https://youtu.be/def456")
    store.update(done.id, status="done", result={"kind": "single", "run_dir": None})
    assert client.get(f"/jobs/{done.id}/review").status_code == 404  # no run dir
    assert client.get(f"/jobs/{done.id}/review?entry=5").status_code == 404


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
