"""In-memory job registry and single-worker background runner for the web app.

This module has no FastAPI dependency so it can be imported and tested without
the ``web`` extra installed.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Literal, Optional

from sidelinehd_extractor.batch import PlaylistBatchResult, run_playlist_batch
from sidelinehd_extractor.config import (
    load_overlay_template,
    load_project_config,
    load_roster,
    resolve_config_path,
)
from sidelinehd_extractor.events import DetectionConfig
from sidelinehd_extractor.ocr import create_ocr_backend
from sidelinehd_extractor.serialization import to_plain_data
from sidelinehd_extractor.workflow import RunYoutubeGameResult, run_youtube_game

JobKind = Literal["single", "playlist"]
JobStatus = Literal["queued", "running", "done", "error"]

WARNING_STAGE_PREFIX = "warning "


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Job:
    """One submitted extraction run and its observable progress."""

    id: str
    kind: JobKind
    url: str
    status: JobStatus = "queued"
    stages: List[str] = field(default_factory=list)
    current_stage: Optional[str] = None
    # Item 54 P3: frame-level progress for the long OCR "process" stage. For
    # playlist jobs these reset at the start of each video's process phase.
    frames_done: int = 0
    frames_total: int = 0
    warnings: List[str] = field(default_factory=list)
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=_utcnow)
    finished_at: Optional[datetime] = None

    @property
    def is_terminal(self) -> bool:
        return self.status in ("done", "error")


class JobStore:
    """Thread-safe in-memory ``id -> Job`` registry.

    Deliberately in-memory for phase 39a (single user, single process, jobs do
    not need to survive a restart). A later phase can swap in the item-39
    SQLite index behind this same interface without touching the routes.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Job] = {}

    def create(self, kind: JobKind, url: str) -> Job:
        job = Job(id=uuid.uuid4().hex, kind=kind, url=url)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> List[Job]:
        """Return all jobs, newest first."""

        with self._lock:
            return list(reversed(self._jobs.values()))

    def update(self, job_id: str, **changes: object) -> Job:
        with self._lock:
            job = self._jobs[job_id]
            for name, value in changes.items():
                if not hasattr(job, name):
                    raise AttributeError(f"Job has no field {name!r}")
                setattr(job, name, value)
            return job

    def record_stage(self, job_id: str, stage: str) -> None:
        """Append a pipeline stage string, routing warnings separately."""

        with self._lock:
            job = self._jobs[job_id]
            job.stages.append(stage)
            if stage.startswith(WARNING_STAGE_PREFIX):
                job.warnings.append(stage)
            else:
                job.current_stage = stage


def default_pipeline_kwargs(data_root: Optional[Path] = None) -> dict:
    """Build the shared pipeline arguments the CLI would use by default.

    Mirrors ``run-youtube``/``run-playlist`` defaults: ``sidelinehd.cfg``
    supplies template/roster/team name, and OCR is Tesseract. ``data_root``
    is the base ``sidelinehd.cfg`` resolves against — None means the process
    CWD (the CLI-served default); the desktop passes its data dir (70f).
    """

    config = load_project_config(cwd=data_root)
    template_path = resolve_config_path(config.template, data_root)
    roster_path = resolve_config_path(config.roster, data_root)
    template = load_overlay_template(template_path) if template_path else None
    roster = (
        load_roster(roster_path, team_name=config.team_name) if roster_path else None
    )
    return {
        "template": template,
        "roster": roster,
        "ocr": create_ocr_backend("tesseract"),
        "detection": DetectionConfig(auto_detect_batting_half=True),
    }


class JobRunner:
    """Runs jobs one at a time on a dedicated background worker.

    A single-worker ``ThreadPoolExecutor`` serializes the heavy download+OCR
    jobs instead of letting them contend on a laptop. FastAPI's
    ``BackgroundTasks`` is deliberately not used: it is tied to the request
    lifecycle and is the wrong tool for multi-minute jobs.
    """

    def __init__(
        self,
        store: JobStore,
        executor: Optional[object] = None,
        video_dir: Path = Path("videos"),
        output_dir: Path = Path("runs"),
        pipeline_kwargs: Callable[[], dict] = default_pipeline_kwargs,
    ) -> None:
        self._store = store
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="sidelinehd-job"
        )
        self._video_dir = video_dir
        self._output_dir = output_dir
        self._pipeline_kwargs = pipeline_kwargs

    @property
    def output_dir(self) -> Path:
        """Where this runner writes run dirs (item 57 rehydrates from here)."""

        return self._output_dir

    def submit(self, job: Job) -> None:
        self._executor.submit(self._run, job.id)

    def _run(self, job_id: str) -> None:
        # Never let the worker thread crash silently: every failure lands on
        # the job as status "error".
        try:
            job = self._store.update(job_id, status="running")

            def stage_progress(stage: str) -> None:
                self._store.record_stage(job_id, stage)

            def frame_progress(
                index: int, total: int, *args: object
            ) -> None:
                # process_video calls this once per sampled frame; the extra
                # positional args (timestamp, sample counts) are not stored.
                self._store.update(job_id, frames_done=index, frames_total=total)

            if job.kind == "playlist":
                raw = run_playlist_batch(
                    playlist_url=job.url,
                    video_dir=self._video_dir,
                    output_dir=self._output_dir,
                    stage_progress=stage_progress,
                    progress=frame_progress,
                    **self._pipeline_kwargs(),
                )
            else:
                raw = run_youtube_game(
                    url=job.url,
                    video_dir=self._video_dir,
                    output_dir=self._output_dir,
                    stage_progress=stage_progress,
                    progress=frame_progress,
                    **self._pipeline_kwargs(),
                )
            self._store.update(
                job_id,
                status="done",
                result=summarize_result(raw),
                finished_at=_utcnow(),
            )
        except Exception as exc:  # noqa: BLE001
            self._store.update(
                job_id,
                status="error",
                error=str(exc) or type(exc).__name__,
                finished_at=_utcnow(),
            )


def summarize_result(result: object) -> dict:
    """Reduce a pipeline result to a JSON-ready dict for ``Job.result``.

    Item 47 reads run dir(s) and export paths from here to render results
    pages, so keep those keys stable.
    """

    if isinstance(result, dict):
        return result
    if isinstance(result, RunYoutubeGameResult):
        run = result.run
        return to_plain_data(
            {
                "kind": "single",
                "run_dir": run.run_dir,
                "chapters_path": run.chapters_path,
                "at_bats_path": run.at_bats_path,
                "sample_count": run.sample_count,
                "state_count": run.state_count,
                "event_count": run.event_count,
                "health_warning": run.health_warning,
                "video_path": result.download.video_path,
            }
        )
    if isinstance(result, PlaylistBatchResult):
        return to_plain_data(
            {
                "kind": "playlist",
                "state_path": result.state_path,
                "summary_path": result.summary_path,
                "total": result.total,
                "processed": result.processed,
                "skipped": result.skipped,
                "failed": result.failed,
                "entries": [
                    {
                        "video_id": entry.video_id,
                        "title": entry.title,
                        "status": entry.status,
                        "run_dir": entry.run_dir,
                        "chapters_path": entry.chapters_path,
                        "at_bats_path": entry.at_bats_path,
                        "error": entry.error,
                    }
                    for entry in result.entries
                ],
            }
        )
    return {"value": to_plain_data(result)}
