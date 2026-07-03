"""FastAPI application factory and routes for the local web UI.

Loopback-only, single-user, no auth: run it with ``sidelinehd-extractor serve``
which binds ``127.0.0.1`` by default. No route renders roster player names;
job results carry run/export paths and jersey numbers only. All assets are
vendored (``static/htmx.min.js``) so the app works fully offline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sidelinehd_extractor.publish import PUBLISH_KIT_COPY_SCRIPT, render_publish_kit_fragment
from sidelinehd_extractor.review_report import summarize_review_report_text
from sidelinehd_extractor.webapp.jobs import Job, JobRunner, JobStore

_PACKAGE_DIR = Path(__file__).resolve().parent

_VALID_KINDS = ("single", "playlist")

REVIEW_REPORT_FILENAME = "review_report.md"


def _validate_submission(url: str, kind: str) -> Optional[str]:
    """Return an error message for a bad submission, or None if valid."""

    if kind not in _VALID_KINDS:
        return f"Unknown job kind: {kind!r}."
    if not url:
        return "Enter a YouTube video or playlist URL."
    if not (url.startswith("http://") or url.startswith("https://")):
        return "The URL must start with http:// or https://."
    return None


def _error_block(label: str, error: str) -> dict:
    return {"kind": "error", "label": label, "error": error}


def _game_block(index: int, label: str, result: dict) -> dict:
    """Build one results-page game block from a per-game result summary.

    Pure view over the run-dir artifacts the pipeline already wrote (item 47):
    exports are read from the summarized paths and the flagged count / run
    warnings are parsed out of ``review_report.md`` — nothing is recomputed.
    """

    chapters_path = result.get("chapters_path")
    at_bats_path = result.get("at_bats_path")
    if not chapters_path or not at_bats_path:
        return _error_block(label, "Export paths are missing from the job result.")
    try:
        chapters_text = Path(chapters_path).read_text(encoding="utf-8")
        at_bats_text = Path(at_bats_path).read_text(encoding="utf-8")
    except OSError as exc:
        return _error_block(label, f"Could not read export files: {exc}")

    fragment = render_publish_kit_fragment(
        game_name=label,
        chapters_text=chapters_text,
        at_bats_text=at_bats_text,
        chapters_path=Path(chapters_path),
        at_bats_path=Path(at_bats_path),
        element_id_prefix=f"game-{index}-",
    )

    flagged_count = None
    warnings: list = []
    run_dir = result.get("run_dir")
    report_path = Path(run_dir) / REVIEW_REPORT_FILENAME if run_dir else None
    if report_path is not None and report_path.exists():
        try:
            summary = summarize_review_report_text(report_path.read_text(encoding="utf-8"))
        except OSError:
            summary = None
        if summary is not None:
            flagged_count = summary.flagged_count
            warnings = summary.warnings

    return {
        "kind": "game",
        "label": label,
        "fragment": fragment,
        "flagged_count": flagged_count,
        "warnings": warnings,
        "report_path": str(report_path) if report_path is not None else None,
    }


def build_result_blocks(job: Job) -> list:
    """Build the per-game blocks for a done job's results page, in batch order."""

    result = job.result or {}
    if job.kind == "playlist":
        blocks = []
        for index, entry in enumerate(result.get("entries") or []):
            label = entry.get("title") or entry.get("video_id") or f"Entry {index + 1}"
            label = f"{index + 1}. {label}"
            if entry.get("status") == "failed":
                blocks.append(_error_block(label, entry.get("error") or "Processing failed."))
            else:
                blocks.append(_game_block(index, label, entry))
        return blocks

    video_path = result.get("video_path")
    run_dir = result.get("run_dir")
    label = Path(video_path).name if video_path else Path(run_dir).name if run_dir else job.url
    return [_game_block(0, label, result)]


def create_app(store: Optional[JobStore] = None, runner: Optional[JobRunner] = None) -> FastAPI:
    """Build the web application. Zero-arg call works as a uvicorn factory."""

    store = store or JobStore()
    runner = runner or JobRunner(store)

    app = FastAPI(title="SidelineHD Extractor")
    app.state.store = store
    app.state.runner = runner
    app.mount("/static", StaticFiles(directory=str(_PACKAGE_DIR / "static")), name="static")
    templates = Jinja2Templates(directory=str(_PACKAGE_DIR / "templates"))

    def _get_job_or_404(job_id: str) -> Job:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown job id")
        return job

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html", {"jobs": store.list()})

    @app.post("/jobs", response_class=HTMLResponse)
    def submit_job(
        request: Request,
        url: str = Form(default=""),
        kind: str = Form(default="single"),
    ) -> HTMLResponse:
        cleaned_url = url.strip()
        error = _validate_submission(cleaned_url, kind)
        if error is not None:
            return templates.TemplateResponse(
                request, "_form_error.html", {"error": error}, status_code=400
            )
        job = store.create(kind=kind, url=cleaned_url)
        runner.submit(job)
        return templates.TemplateResponse(request, "_job_row.html", {"job": job})

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_detail(request: Request, job_id: str) -> HTMLResponse:
        job = _get_job_or_404(job_id)
        return templates.TemplateResponse(request, "job_detail.html", {"job": job})

    @app.get("/jobs/{job_id}/status", response_class=HTMLResponse)
    def job_status(request: Request, job_id: str) -> HTMLResponse:
        job = _get_job_or_404(job_id)
        return templates.TemplateResponse(request, "_job_status.html", {"job": job})

    @app.get("/jobs/{job_id}/results", response_class=HTMLResponse)
    def job_results(request: Request, job_id: str) -> HTMLResponse:
        job = _get_job_or_404(job_id)
        blocks = build_result_blocks(job) if job.status == "done" else []
        return templates.TemplateResponse(
            request,
            "results.html",
            {"job": job, "blocks": blocks, "copy_script": PUBLISH_KIT_COPY_SCRIPT},
        )

    return app
