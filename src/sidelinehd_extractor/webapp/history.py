"""Rehydrate completed runs from ``runs/`` into the in-memory job store.

Item 57: the ``JobStore`` is deliberately in-memory, so before this module a
server restart 404'd every finished run even though its artifacts were intact
on disk. ``runs/`` is the source of truth — at startup each completed run dir
is reconstructed as a done single job so the index lists it and the results/
game/review/feedback routes resolve.

Only runs with the complete modern artifact set are recovered: a parseable
``manifest.json``, a loadable non-empty ``events.jsonl``, and both text
exports at the paths the manifest's export section implies. In-flight,
partial, or legacy run dirs are skipped (hidden) rather than listed broken.

Like ``jobs.py`` this module has no FastAPI dependency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Set

from sidelinehd_extractor.events import load_events
from sidelinehd_extractor.naming import game_name_for_run
from sidelinehd_extractor.webapp.jobs import JobStore
from sidelinehd_extractor.workflow import export_paths, load_export_options

EVENTS_FILENAME = "events.jsonl"
MANIFEST_FILENAME = "manifest.json"


@dataclass
class RecoveredRun:
    """One completed run dir reconstructed into job-shaped data."""

    label: str
    result: dict
    created_at: datetime
    finished_at: datetime


def rehydrate_jobs_from_runs(store: JobStore, runs_dir: Path = Path("runs")) -> int:
    """Seed ``store`` with done jobs for completed run dirs under ``runs_dir``.

    Returns the number of runs recovered. Run dirs already referenced by a job
    in the store (live in-session jobs) are not duplicated. Recovery is
    best-effort per run dir: a corrupt or incomplete run is skipped, never
    fatal to startup.
    """

    if not runs_dir.is_dir():
        return 0
    known = _known_run_dirs(store)
    recovered: List[RecoveredRun] = []
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir() or _resolve_key(run_dir) in known:
            continue
        try:
            run = _recover_run(run_dir)
        except Exception:  # noqa: BLE001 - a bad run dir must not break startup
            continue
        if run is not None:
            recovered.append(run)

    # Insert oldest-first: JobStore.list() returns insertion order reversed,
    # so recovered history lands newest-first with live jobs above it.
    recovered.sort(key=lambda run: run.created_at)
    for run in recovered:
        job = store.create(kind="single", url=run.label)
        store.update(
            job.id,
            status="done",
            result=run.result,
            created_at=run.created_at,
            finished_at=run.finished_at,
        )
    return len(recovered)


def _known_run_dirs(store: JobStore) -> Set[str]:
    """Resolved run-dir paths already referenced by jobs in the store."""

    known: Set[str] = set()
    for job in store.list():
        result = job.result or {}
        entries = result.get("entries") if result.get("kind") == "playlist" else [result]
        for entry in entries or []:
            run_dir = entry.get("run_dir") if isinstance(entry, dict) else None
            if run_dir:
                known.add(_resolve_key(Path(run_dir)))
    return known


def _resolve_key(path: Path) -> str:
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _recover_run(run_dir: Path) -> Optional[RecoveredRun]:
    """Reconstruct one run dir, or return None if it is incomplete/legacy."""

    manifest_path = run_dir / MANIFEST_FILENAME
    events_path = run_dir / EVENTS_FILENAME
    if not manifest_path.is_file() or not events_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None

    # A legacy/hand-edited events file that the review page could not load is
    # as broken as a missing one; a 0-event run has nothing to show.
    try:
        events = load_events(events_path)
    except Exception:  # noqa: BLE001 - any unloadable shape means "legacy"
        return None
    if not events:
        return None

    # The results/game pages require both text exports at the paths a
    # re-export would use; their absence means the run never finished.
    _, output_prefix = load_export_options(manifest_path)
    chapters_path, at_bats_path = export_paths(run_dir, output_prefix)
    if not chapters_path.is_file() or not at_bats_path.is_file():
        return None

    created_at = _manifest_created_at(manifest, run_dir)
    title = _run_title(manifest, run_dir)
    health = manifest.get("health")
    health_warning = None
    if isinstance(health, dict) and health.get("no_scoreboard_detected"):
        health_warning = str(health.get("message") or "") or None
    video = manifest.get("video")
    video_path = video.get("path") if isinstance(video, dict) else None

    return RecoveredRun(
        label=f"{title} (processed {created_at:%Y-%m-%d})",
        result={
            "kind": "single",
            "recovered": True,
            "title": title,
            "run_dir": str(run_dir),
            "chapters_path": str(chapters_path),
            "at_bats_path": str(at_bats_path),
            "event_count": len(events),
            "health_warning": health_warning,
            "video_path": str(video_path) if video_path else None,
        },
        created_at=created_at,
        finished_at=created_at,
    )


def _manifest_created_at(manifest: dict, run_dir: Path) -> datetime:
    value = manifest.get("created_at")
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
    try:
        return datetime.fromtimestamp(run_dir.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return datetime.now(timezone.utc)


def _run_title(manifest: dict, run_dir: Path) -> str:
    """Display title: YouTube title if recorded, else the naming fallbacks."""

    youtube = manifest.get("youtube")
    if isinstance(youtube, dict) and youtube.get("title"):
        return str(youtube["title"]).strip()
    return game_name_for_run(run_dir)
