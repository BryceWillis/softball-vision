"""Tests for item 57: rehydrating completed runs from runs/ at web startup."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("jinja2")
pytest.importorskip("multipart")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from sidelinehd_extractor.models import Event, EventType  # noqa: E402
from sidelinehd_extractor.processing import write_json, write_jsonl  # noqa: E402
from sidelinehd_extractor.webapp.app import create_app  # noqa: E402
from sidelinehd_extractor.webapp.history import rehydrate_jobs_from_runs  # noqa: E402
from sidelinehd_extractor.webapp.jobs import JobStore  # noqa: E402

CHAPTERS_TEXT = "00:00 Pregame\n10:00 Top 1 (0-0)\n"
AT_BATS_TEXT = "Top 1\n10:05 #12\n"


def _write_completed_run(
    runs_dir: Path,
    name: str = "fixture_game-20260701-120000",
    video_stem: str = "fixture_game",
    created_at: str = "2026-07-01T12:00:00+00:00",
    youtube_title: str | None = None,
    events: list | None = None,
) -> Path:
    """A run dir with the full modern artifact set the pages read."""

    run_dir = runs_dir / name
    run_dir.mkdir(parents=True)
    video_path = runs_dir.parent / "videos" / f"{video_stem}.mp4"
    manifest = {
        "created_at": created_at,
        "video": {"path": str(video_path)},
        "template": {"name": "sidelinehd active"},
        "tesseract_version": "5.3.0",
        "ocr_backend": "tesseract",
        "ocr_workers": 2,
        "sample_every_seconds": 5.0,
        "fields": ["batter_number"],
        "warnings": [],
        "export": {
            "include_chapter_intro": True,
            "chapter_intro_label": "Pregame",
            "include_inning_score": True,
            "include_at_bat_inning_headers": True,
            "output_prefix": None,
        },
        "health": {"event_count": 2, "no_scoreboard_detected": False, "message": None},
    }
    if youtube_title is not None:
        manifest["youtube"] = {"video_id": "vid123", "title": youtube_title}
    write_json(run_dir / "manifest.json", manifest)
    write_jsonl(
        run_dir / "events.jsonl",
        events
        if events is not None
        else [
            Event(EventType.HALF_INNING_START, 600, "Top 1"),
            Event(EventType.AT_BAT_START, 605, "#12", player_number="12"),
        ],
    )
    # Exports at the path a re-export would use: exports/<slug>/<slug>_*.txt
    # where the slug comes from the manifest video stem.
    export_dir = run_dir / "exports" / video_stem
    export_dir.mkdir(parents=True)
    (export_dir / f"{video_stem}_chapters.txt").write_text(CHAPTERS_TEXT, encoding="utf-8")
    (export_dir / f"{video_stem}_at_bats.txt").write_text(AT_BATS_TEXT, encoding="utf-8")
    return run_dir


def test_rehydrated_run_survives_restart_and_all_pages_load(tmp_path):
    runs_dir = tmp_path / "runs"
    _write_completed_run(runs_dir)

    # A fresh store models the post-restart process: no live jobs.
    store = JobStore()
    client = TestClient(create_app(store=store, runs_dir=runs_dir))

    jobs = store.list()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.status == "done"
    assert job.kind == "single"
    assert job.result["recovered"] is True
    assert job.result["event_count"] == 2
    assert job.result["title"] == "fixture_game"

    assert "fixture_game" in client.get("/").text
    for page in ("results", "game", "review", "feedback"):
        response = client.get(f"/jobs/{job.id}/{page}")
        assert response.status_code == 200, page


def test_incomplete_and_legacy_run_dirs_are_skipped(tmp_path):
    runs_dir = tmp_path / "runs"

    no_events = runs_dir / "no-events"
    no_events.mkdir(parents=True)
    write_json(no_events / "manifest.json", {"created_at": "2026-07-01T00:00:00+00:00"})

    _write_completed_run(runs_dir, name="empty-events", events=[])

    no_exports = _write_completed_run(runs_dir, name="no-exports")
    for export in (no_exports / "exports").rglob("*.txt"):
        export.unlink()

    corrupt_manifest = _write_completed_run(runs_dir, name="corrupt-manifest")
    (corrupt_manifest / "manifest.json").write_text("{not json", encoding="utf-8")

    legacy_events = _write_completed_run(runs_dir, name="legacy-events")
    (legacy_events / "events.jsonl").write_text('{"weird": "shape"}\n', encoding="utf-8")

    (runs_dir / "stray-file.txt").write_text("not a run dir", encoding="utf-8")

    store = JobStore()
    assert rehydrate_jobs_from_runs(store, runs_dir) == 0
    assert store.list() == []


def test_live_jobs_are_not_duplicated(tmp_path):
    runs_dir = tmp_path / "runs"
    run_dir = _write_completed_run(runs_dir)

    store = JobStore()
    live = store.create(kind="single", url="https://youtube.com/watch?v=abc")
    store.update(live.id, status="done", result={"kind": "single", "run_dir": str(run_dir)})

    assert rehydrate_jobs_from_runs(store, runs_dir) == 0
    assert [job.id for job in store.list()] == [live.id]


def test_recovered_runs_list_newest_first_with_manifest_dates(tmp_path):
    runs_dir = tmp_path / "runs"
    _write_completed_run(
        runs_dir, name="older-run", video_stem="older_game",
        created_at="2026-06-01T09:00:00+00:00",
    )
    _write_completed_run(
        runs_dir, name="newer-run", video_stem="newer_game",
        created_at="2026-07-01T09:00:00+00:00",
    )

    store = JobStore()
    assert rehydrate_jobs_from_runs(store, runs_dir) == 2
    urls = [job.url for job in store.list()]
    assert urls == [
        "newer_game (processed 2026-07-01)",
        "older_game (processed 2026-06-01)",
    ]


def test_label_prefers_manifest_youtube_title(tmp_path):
    runs_dir = tmp_path / "runs"
    _write_completed_run(runs_dir, youtube_title="Placeholder 12U vs Rival 12U 2026.05.31")

    store = JobStore()
    assert rehydrate_jobs_from_runs(store, runs_dir) == 1
    job = store.list()[0]
    assert job.url == "Placeholder 12U vs Rival 12U 2026.05.31 (processed 2026-07-01)"
    assert job.result["title"] == "Placeholder 12U vs Rival 12U 2026.05.31"


def test_missing_runs_dir_is_a_noop(tmp_path):
    store = JobStore()
    assert rehydrate_jobs_from_runs(store, tmp_path / "does-not-exist") == 0
    assert store.list() == []


def test_rehydrate_result_shape_matches_summarize_result_keys(tmp_path):
    """Item 47's pages read these keys; keep the recovered shape compatible."""

    runs_dir = tmp_path / "runs"
    run_dir = _write_completed_run(runs_dir)
    store = JobStore()
    rehydrate_jobs_from_runs(store, runs_dir)
    result = store.list()[0].result
    assert result["kind"] == "single"
    assert result["run_dir"] == str(run_dir)
    assert Path(result["chapters_path"]).read_text(encoding="utf-8") == CHAPTERS_TEXT
    assert Path(result["at_bats_path"]).read_text(encoding="utf-8") == AT_BATS_TEXT
    assert result["health_warning"] is None
    assert result["video_path"].endswith("fixture_game.mp4")
    # The manifest round-trips as JSON, so the result must too.
    json.dumps(result)
